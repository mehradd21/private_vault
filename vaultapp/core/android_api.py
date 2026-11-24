"""Android native bridge: Storage Access Framework, intents and FileProvider.

All Android calls are isolated here. On desktop these helpers raise
``AndroidUnavailable`` so core logic can be unit-tested with plain files.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from ..utils.mime import SAF_MIME_TYPES
from ..utils.platform import is_android

REQUEST_IMPORT = 4101
REQUEST_EXPORT_DIR = 4102
FILEPROVIDER_AUTHORITY = "org.mehrad.privatevault.fileprovider"


class AndroidUnavailable(RuntimeError):
    pass


def _jnius():
    if not is_android():
        raise AndroidUnavailable("Android API is only available on a device")
    from jnius import autoclass

    return autoclass


def activity():
    autoclass = _jnius()
    return autoclass("org.kivy.android.PythonActivity").mActivity


def bind_activity_result(callback: Callable[[int, int, object], None]) -> bool:
    """Subscribe to Activity.onActivityResult through python-for-android."""
    if not is_android():
        return False
    try:
        from android import activity as android_activity

        android_activity.bind(on_activity_result=callback)
        return True
    except Exception:
        return False


def open_documents() -> bool:
    """Launch the system file picker for multiple images/videos."""
    autoclass = _jnius()
    intent_cls = autoclass("android.content.Intent")
    intent = intent_cls(intent_cls.ACTION_OPEN_DOCUMENT)
    intent.setType("*/*")
    intent.putExtra(intent_cls.EXTRA_MIME_TYPES, list(SAF_MIME_TYPES))
    intent.putExtra(intent_cls.EXTRA_ALLOW_MULTIPLE, True)
    intent.addCategory(intent_cls.CATEGORY_OPENABLE)
    intent.addFlags(
        intent_cls.FLAG_GRANT_READ_URI_PERMISSION
        | intent_cls.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
    )
    activity().startActivityForResult(intent, REQUEST_IMPORT)
    return True


def open_document_tree() -> bool:
    """Launch the system folder picker used by Export."""
    autoclass = _jnius()
    intent_cls = autoclass("android.content.Intent")
    intent = intent_cls(intent_cls.ACTION_OPEN_DOCUMENT_TREE)
    intent.addFlags(
        intent_cls.FLAG_GRANT_READ_URI_PERMISSION
        | intent_cls.FLAG_GRANT_WRITE_URI_PERMISSION
        | intent_cls.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
    )
    activity().startActivityForResult(intent, REQUEST_EXPORT_DIR)
    return True


def result_uris(intent, request_code: int) -> list[object]:
    """Extract selected content Uris from an ACTION_OPEN_DOCUMENT result."""
    if intent is None:
        return []
    clip = intent.getClipData()
    uris = []
    if clip is not None:
        for i in range(clip.getItemCount()):
            uris.append(clip.getItemAt(i).getUri())
    elif intent.getData() is not None:
        uris.append(intent.getData())
    return uris


def persist_read_permission(uri) -> None:
    autoclass = _jnius()
    intent_cls = autoclass("android.content.Intent")
    try:
        activity().getContentResolver().takePersistableUriPermission(
            uri, intent_cls.FLAG_GRANT_READ_URI_PERMISSION
        )
    except Exception:
        pass  # Some providers do not allow persisting; in-memory grant still works.


def persist_write_permission(uri) -> None:
    autoclass = _jnius()
    intent_cls = autoclass("android.content.Intent")
    try:
        activity().getContentResolver().takePersistableUriPermission(
            uri, intent_cls.FLAG_GRANT_WRITE_URI_PERMISSION
        )
    except Exception:
        pass


def uri_metadata(uri) -> tuple[str, int | None, str | None]:
    """Return (display_name, size, mime) reported by the documents provider."""
    autoclass = _jnius()
    openable = autoclass("android.provider.OpenableColumns")
    resolver = activity().getContentResolver()
    name, size, mime = "unknown", None, None
    cursor = resolver.query(
        uri,
        [openable.DISPLAY_NAME, openable.SIZE],
        None,
        None,
        None,
    )
    if cursor is not None:
        try:
            if cursor.moveToFirst():
                name_index = cursor.getColumnIndex(openable.DISPLAY_NAME)
                size_index = cursor.getColumnIndex(openable.SIZE)
                if name_index >= 0:
                    value = cursor.getString(name_index)
                    name = value or name
                if size_index >= 0:
                    value = cursor.getString(size_index)
                    size = int(value) if value and value.isdigit() else None
        finally:
            cursor.close()
    try:
        mime = resolver.getType(uri)
    except Exception:
        mime = None
    return name, size, mime


class ContentStream:
    """Sequential file-like reader over an Android content:// Uri."""

    def __init__(self, uri) -> None:
        autoclass = _jnius()
        self.uri = uri
        self._stream = activity().getContentResolver().openInputStream(uri)
        if self._stream is None:
            raise OSError("cannot open the selected file")
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("stream is closed")
        if size is None or size < 0:
            chunks = []
            while True:
                part = self.read(256 * 1024)
                if not part:
                    break
                chunks.append(part)
            return b"".join(chunks)
        # pyjnius converts bytearray <-> Java byte[] and copies reads back.
        buffer = bytearray(min(size, 1024 * 1024))
        count = self._stream.read(buffer)
        if count <= 0:
            return b""
        return bytes(buffer[:count])

    def close(self) -> None:
        if not self.closed:
            try:
                self._stream.close()
            finally:
                self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class OutputStreamSink:
    """Write-only sink over a content:// Uri (SAF export)."""

    def __init__(self, uri) -> None:
        autoclass = _jnius()
        self._stream = activity().getContentResolver().openOutputStream(uri, "w")
        if self._stream is None:
            raise OSError("cannot open output stream for destination")

    def write(self, data: bytes) -> int:
        self._stream.write(bytearray(data))
        return len(data)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._stream.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def create_export_document(tree_uri, filename: str, mime: str):
    """Create a document inside a chosen SAF tree and return its Uri."""
    autoclass = _jnius()
    documents = autoclass("android.provider.DocumentsContract")
    document_id = documents.getTreeDocumentId(tree_uri)
    parent_uri = documents.buildDocumentUriUsingTree(tree_uri, document_id)
    return documents.createDocument(
        activity().getContentResolver(), parent_uri, mime, filename
    )


def delete_document(uri) -> bool:
    """Delete an original file through SAF; returns False when not permitted."""
    try:
        autoclass = _jnius()
        documents = autoclass("android.provider.DocumentsContract")
        documents.deleteDocument(activity().getContentResolver(), uri)
        return True
    except Exception:
        return False


def share_file(path: str | Path, mime: str, display_name: str | None = None) -> bool:
    """Share a decrypted temp file read-only through Android FileProvider."""
    autoclass = _jnius()
    File = autoclass("java.io.File")
    intent_cls = autoclass("android.content.Intent")
    context = activity()
    java_file = File(str(path))
    uri = None
    for provider in ("androidx.core.content.FileProvider", "android.support.v4.content.FileProvider"):
        try:
            uri = autoclass(provider).getUriForFile(context, FILEPROVIDER_AUTHORITY, java_file)
            break
        except Exception:
            continue
    if uri is None:
        return False
    intent = intent_cls(intent_cls.ACTION_VIEW)
    intent.setDataAndType(uri, mime or "application/octet-stream")
    intent.addFlags(intent_cls.FLAG_GRANT_READ_URI_PERMISSION)
    if display_name:
        intent.putExtra(intent_cls.EXTRA_TITLE, display_name)
    chooser = intent_cls.createChooser(intent, "باز کردن با")
    context.startActivity(chooser)
    return True
