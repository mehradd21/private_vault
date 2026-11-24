"""Encrypted vault storage: atomic import, verified export, deletion and temp files."""
from __future__ import annotations

import hashlib
import os
import secrets
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable

from .crypto import (
    CryptoError,
    NullWriter,
    decrypt_stream,
    encrypt_bytes,
    encrypt_stream,
    verify_encrypted_file,
)
from .database import VaultDatabase
from .media import (
    THUMB_AAD,
    make_image_thumbnail,
    video_duration_ms,
    video_metadata_uri,
    video_thumbnail,
)
from . import android_api
from ..utils.mime import UnsupportedFileError, validate
from ..utils.platform import is_android

MAX_PREVIEW_BYTES = 8 * 1024 * 1024
PROGRESS = Callable[[int, int], None]
CANCELLED = Callable[[], bool]


class VaultError(Exception):
    pass


@dataclass
class ImportResult:
    record: dict | None
    errors: list[str]


class _PrefixedSource:
    """Replays bytes already consumed for type detection back into the stream."""

    def __init__(self, prefix: bytes, source: BinaryIO) -> None:
        self.prefix = bytearray(prefix)
        self.source = source

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data = bytes(self.prefix) + self.source.read()
            self.prefix.clear()
            return data
        if not self.prefix:
            return self.source.read(size)
        take = min(size, len(self.prefix))
        data = bytes(self.prefix[:take])
        del self.prefix[:take]
        if take < size:
            data += self.source.read(size - take)
        return data


class _PreviewCollector:
    """Pass-through reader that keeps a bounded plaintext preview in memory."""

    def __init__(self, source: BinaryIO, limit: int = MAX_PREVIEW_BYTES) -> None:
        self.source = source
        self.limit = limit
        self.preview = bytearray()

    def read(self, size: int = -1) -> bytes:
        data = self.source.read(size)
        if data and len(self.preview) < self.limit:
            self.preview.extend(data[:self.limit - len(self.preview)])
        return data


class TempFileManager:
    """Tracks short-lived decrypted files used by 'open with' and the player."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.pending: dict[str, float] = {}

    def register(self, path: str | Path) -> None:
        self.pending[str(path)] = time.monotonic()

    def defer(self, path: str | Path) -> None:
        """Keep a file until the next cleanup if another app may still use it."""
        self.pending[str(path)] = time.monotonic() - 3600

    def cleanup(self, min_age_seconds: float = 0.5) -> int:
        removed = 0
        now = time.monotonic()
        for path, created in list(self.pending.items()):
            if now - created < min_age_seconds:
                continue
            try:
                os.unlink(path)
                removed += 1
            except OSError:
                pass
            self.pending.pop(path, None)
        return removed


class VaultRepository:
    def __init__(self, paths, database: VaultDatabase, session_provider) -> None:
        self.paths = paths
        self.db = database
        self._session_provider = session_provider
        self.temp_files = TempFileManager(paths.temp)

    def _key(self) -> bytes:
        session = self._session_provider()
        if session is None:
            raise VaultError("vault is locked")
        return session.key

    # ---------- import ----------
    def import_stream(
        self,
        source: BinaryIO,
        display_name: str,
        reported_mime: str | None,
        size: int,
        source_uri: str | None = None,
        progress: PROGRESS | None = None,
        cancelled: CANCELLED | None = None,
    ) -> ImportResult:
        """Encrypt, verify and atomically store a single media file."""
        key = self._key()
        header = source.read(64) or b""
        try:
            file_type = validate(display_name, reported_mime, header)
        except (UnsupportedFileError, ValueError) as exc:
            return ImportResult(record=None, errors=[str(exc)])
        if size <= 0:
            raise VaultError("file is empty or has an unknown size")

        collector = _PreviewCollector(_PrefixedSource(header, source))
        stored_name = secrets.token_hex(8) + ".enc"
        temp_path = self.paths.temp / (stored_name + ".part")
        final_path = self.paths.media_dir(file_type.kind) / stored_name
        thumb_name = None
        try:
            with open(temp_path, "wb") as encrypted:
                encrypt_stream(collector, encrypted, key, size, progress=progress, cancelled=cancelled)
            verify_encrypted_file(str(temp_path), key)
            digest = self._sha256(temp_path)
            duration = None
            if file_type.kind == "image":
                thumb = make_image_thumbnail(bytes(collector.preview))
            else:
                thumb, duration = None, None
                if is_android() and source_uri is not None:
                    thumb, duration = video_metadata_uri(source_uri)
                elif isinstance(getattr(source, "name", None), str):
                    thumb = video_thumbnail(source.name)
                    duration = video_duration_ms(source.name)
            if thumb:
                thumb_name = secrets.token_hex(8) + ".thumb.enc"
                with open(self.paths.thumbnails / thumb_name, "wb") as handle:
                    handle.write(encrypt_bytes(thumb, key, THUMB_AAD))
            os.replace(str(temp_path), str(final_path))
            if is_android():
                os.chmod(final_path, 0o600)
            record = {
                "display_name": display_name,
                "stored_name": stored_name,
                "kind": file_type.kind,
                "mime": file_type.mime,
                "original_ext": file_type.ext,
                "size": size,
                "imported_at": int(time.time()),
                "hidden": 0,
                "duration_ms": duration,
                "thumb_name": thumb_name,
                "source_uri": str(source_uri) if source_uri is not None else None,
                "integrity": digest,
            }
            record["id"] = self.db.add_file(record)
            return ImportResult(record=record, errors=[])
        except Exception as exc:
            if final_path.exists():
                final_path.unlink()
            if thumb_name and (self.paths.thumbnails / thumb_name).exists():
                (self.paths.thumbnails / thumb_name).unlink()
            if isinstance(exc, (CryptoError, ValueError)):
                return ImportResult(record=None, errors=[str(exc)])
            if cancelled and cancelled():
                return ImportResult(record=None, errors=["عملیات لغو شد"])
            raise
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def import_path(self, path: str | Path, progress: PROGRESS | None = None,
                    cancelled: CANCELLED | None = None) -> ImportResult:
        path = Path(path)
        with open(path, "rb") as source:
            return self.import_stream(
                source, path.name, None, path.stat().st_size, str(path), progress, cancelled
            )

    # ---------- export ----------
    def export_to_path(self, file_id: int, destination: str | Path,
                       progress: PROGRESS | None = None,
                       cancelled: CANCELLED | None = None) -> Path:
        record = self._record(file_id)
        destination = Path(destination)
        if destination.is_dir():
            destination = destination / f"{Path(record['display_name']).stem}{record['original_ext']}"
        with open(self._encrypted_path(record), "rb") as source, open(destination, "wb") as sink:
            decrypt_stream(source, sink, self._key(), progress=progress, cancelled=cancelled)
        return destination

    def export_to_sink(self, file_id: int, sink_factory: Callable[[str, str], BinaryIO],
                       progress: PROGRESS | None = None,
                       cancelled: CANCELLED | None = None) -> None:
        record = self._record(file_id)
        name = f"{Path(record['display_name']).stem}{record['original_ext']}"
        sink = sink_factory(name, record["mime"])
        try:
            with open(self._encrypted_path(record), "rb") as source:
                decrypt_stream(source, sink, self._key(), progress=progress, cancelled=cancelled)
        finally:
            sink.close()

    def export_to_saf_tree(self, file_id: int, tree_uri,
                           progress: PROGRESS | None = None,
                           cancelled: CANCELLED | None = None) -> None:
        record = self._record(file_id)
        name = f"{Path(record['display_name']).stem}{record['original_ext']}"
        uri = android_api.create_export_document(tree_uri, name, record["mime"])

        def factory(_name, _mime):
            return android_api.OutputStreamSink(uri)

        self.export_to_sink(file_id, factory, progress, cancelled)

    # ---------- viewing ----------
    def thumbnail_bytes(self, record: dict) -> bytes | None:
        if not record.get("thumb_name"):
            return None
        path = self.paths.thumbnails / record["thumb_name"]
        if not path.exists():
            return None
        try:
            from .crypto import decrypt_bytes

            return decrypt_bytes(path.read_bytes(), self._key(), THUMB_AAD)
        except CryptoError:
            return None

    def preview_bytes(self, record: dict, limit: int = 8 * 1024 * 1024) -> bytes | None:
        """Decrypt up to ``limit`` bytes for a full-size still image."""
        from .crypto import HEADER

        path = self._encrypted_path(record)
        with open(path, "rb") as source:
            header = source.read(HEADER.size)
            if len(header) < HEADER.size:
                return None
            source.seek(0)
            output = _LimitedWriter(limit)
            try:
                decrypt_stream(
                    source, output, self._key(),
                    cancelled=lambda: len(output.data) >= limit,
                )
            except CryptoError:
                pass
        return bytes(output.data)

    def decrypt_to_temp(self, file_id: int) -> Path:
        record = self._record(file_id)
        name = f"{file_id}_{secrets.token_hex(6)}{record['original_ext']}"
        destination = self.paths.temp / name
        with open(self._encrypted_path(record), "rb") as source, open(destination, "wb") as sink:
            decrypt_stream(source, sink, self._key())
        if is_android():
            os.chmod(destination, 0o600)
        self.temp_files.register(destination)
        return destination

    def open_with(self, file_id: int) -> bool:
        record = self._record(file_id)
        path = self.decrypt_to_temp(file_id)
        ok = android_api.share_file(path, record["mime"], record["display_name"])
        if ok:
            self.temp_files.defer(path)
        else:
            path.unlink(missing_ok=True)
        return ok

    # ---------- management ----------
    def rename(self, file_id: int, name: str) -> None:
        if not name.strip():
            raise VaultError("name cannot be empty")
        self.db.rename(file_id, name.strip())

    def set_hidden(self, file_id: int, hidden: bool) -> None:
        self.db.set_hidden(file_id, hidden)

    def delete(self, file_id: int) -> bool:
        record = self.db.get_file(file_id)
        if record is None:
            return False
        encrypted = self._encrypted_path(record)
        thumb = self.paths.thumbnails / record["thumb_name"] if record.get("thumb_name") else None
        self.db.delete_file(file_id)
        try:
            encrypted.unlink(missing_ok=True)
            if thumb:
                thumb.unlink(missing_ok=True)
            for path in self.paths.temp.glob(f"{file_id}_*"):
                path.unlink(missing_ok=True)
        except OSError:
            self.db.restore_file(record)
            raise
        return True

    def verify(self, file_id: int) -> bool:
        record = self._record(file_id)
        return verify_encrypted_file(str(self._encrypted_path(record)), self._key())

    def dispose(self) -> None:
        self.temp_files.cleanup(min_age_seconds=0)

    # ---------- helpers ----------
    def _record(self, file_id: int) -> dict:
        record = self.db.get_file(file_id)
        if record is None:
            raise VaultError("file record not found")
        return record

    def _encrypted_path(self, record: dict) -> Path:
        return self.paths.media_dir(record["kind"]) / record["stored_name"]

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class _LimitedWriter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()

    def write(self, data: bytes) -> int:
        if len(self.data) < self.limit:
            self.data.extend(data[:self.limit - len(self.data)])
        return len(data)
