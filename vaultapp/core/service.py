"""High-level facade used by the UI. All sensitive state lives behind this object."""
from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, Callable

from .auth import AuthManager, VaultSession
from .database import VaultDatabase
from .keystore import get_keystore
from .vault import ImportResult, VaultRepository
from ..utils.paths import VaultPaths
from ..utils.platform import is_android


class VaultService:
    def __init__(self, paths: VaultPaths | None = None) -> None:
        self.paths = paths or VaultPaths()
        self.paths.create()
        self.keystore = get_keystore(self.paths.database_dir)
        self.db = VaultDatabase(self.paths.db_file)
        self.auth = AuthManager(self.paths, self.db, self.keystore)
        self.repo = VaultRepository(self.paths, self.db, lambda: self.auth.session)
        self.paths.cleanup_temp()

    # ---------- auth ----------
    @property
    def is_setup(self) -> bool:
        return self.auth.is_setup

    @property
    def is_unlocked(self) -> bool:
        return self.auth.is_unlocked

    def setup(self, password: str, confirmation: str) -> VaultSession:
        return self.auth.setup(password, confirmation)

    def unlock(self, password: str) -> VaultSession:
        return self.auth.unlock(password)

    def change_password(self, old: str, new: str, confirmation: str) -> None:
        self.auth.change_password(old, new, confirmation)

    def lock(self) -> None:
        self.auth.lock()
        self.repo.dispose()

    def touch(self) -> None:
        self.auth.touch()

    def check_auto_lock(self) -> bool:
        locked = self.auth.check_auto_lock()
        if locked:
            self.repo.dispose()
        return locked

    # ---------- files ----------
    def list_files(self, kind: str | None = None, hidden: bool | None = None,
                   query: str = "", sort: str = "newest") -> list[dict]:
        return self.db.list_files(kind, hidden, query, sort)

    def stats(self) -> dict:
        return self.db.count_files()

    def import_stream(self, source: BinaryIO, name: str, mime: str | None, size: int,
                      uri=None, progress=None, cancelled=None) -> ImportResult:
        return self.repo.import_stream(source, name, mime, size, uri, progress, cancelled)

    def import_path(self, path: str | Path, progress=None, cancelled=None) -> ImportResult:
        return self.repo.import_path(path, progress, cancelled)

    def remove_originals(self, items: list[dict]) -> list[str]:
        """Explicit user-confirmed deletion of source files; returns failures."""
        failures = []
        for item in items:
            try:
                if is_android() and item.get("uri"):
                    from . import android_api

                    if not android_api.delete_document(item["uri"]):
                        failures.append(item["name"])
                elif item.get("path"):
                    Path(item["path"]).unlink(missing_ok=True)
            except Exception:
                failures.append(item["name"])
        return failures

    def export_to_path(self, file_id: int, destination: str | Path, progress=None,
                       cancelled=None) -> Path:
        return self.repo.export_to_path(file_id, destination, progress, cancelled)

    def export_to_saf_tree(self, file_id: int, tree_uri, progress=None, cancelled=None) -> None:
        self.repo.export_to_saf_tree(file_id, tree_uri, progress, cancelled)

    def thumbnail(self, record: dict) -> bytes | None:
        return self.repo.thumbnail_bytes(record)

    def preview(self, record: dict, limit: int = 8 * 1024 * 1024) -> bytes | None:
        return self.repo.preview_bytes(record, limit)

    def decrypt_to_temp(self, file_id: int) -> Path:
        return self.repo.decrypt_to_temp(file_id)

    def open_with(self, file_id: int) -> bool:
        return self.repo.open_with(file_id)

    def rename(self, file_id: int, name: str) -> None:
        self.repo.rename(file_id, name)

    def set_hidden(self, file_id: int, hidden: bool) -> None:
        self.repo.set_hidden(file_id, hidden)

    def delete(self, file_id: int) -> bool:
        return self.repo.delete(file_id)

    def verify(self, file_id: int) -> bool:
        return self.repo.verify(file_id)

    def cleanup_temp_files(self) -> None:
        self.repo.temp_files.cleanup()
