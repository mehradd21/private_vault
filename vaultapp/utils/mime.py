"""File type detection: extension + reported MIME + magic bytes (never extension alone)."""
from __future__ import annotations

import os
from dataclasses import dataclass

IMAGE_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "image/gif", "image/bmp", "image/x-ms-bmp", "image/heic", "image/heif",
}
VIDEO_MIMES = {
    "video/mp4", "video/x-matroska", "video/webm", "video/quicktime",
    "video/x-msvideo", "video/3gpp", "video/3gpp2", "video/x-m4v",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".3gp", ".3g2", ".m4v"}
SAF_MIME_TYPES = sorted(IMAGE_MIMES | VIDEO_MIMES)


class UnsupportedFileError(ValueError):
    pass


@dataclass(frozen=True)
class FileType:
    kind: str  # "image" or "video"
    mime: str
    ext: str


def sniff(header: bytes) -> tuple[str, str] | None:
    """Return (kind, canonical mime) from magic bytes, or None when unknown."""
    if not header:
        return None
    if header.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image", "image/gif"
    if header.startswith(b"BM"):
        return "image", "image/bmp"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image", "image/webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}:
            return "image", "image/heic"
        if brand in {b"qt  ", b"M4V ", b"mp42", b"mp41", b"isom", b"avc1", b"mp4v"}:
            return "video", "video/mp4"
        if brand.startswith(b"3gp"):
            return "video", "video/3gpp"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        window = header[:96].lower()
        if b"webm" in window:
            return "video", "video/webm"
        if b"matroska" in window:
            return "video", "video/x-matroska"
        return "video", "video/x-matroska"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "video", "video/x-msvideo"
    return None


def validate(name: str, reported_mime: str | None, header: bytes) -> FileType:
    """Validate a candidate file using all three signals.

    A file is accepted only when its content signature identifies a supported
    image/video and the extension or the reported MIME agrees with it.
    """
    detected = sniff(header)
    if detected is None:
        raise UnsupportedFileError("content signature is not a supported image or video")
    kind, mime = detected
    ext = os.path.splitext(name or "")[1].lower()
    declared = (reported_mime or "").lower().split(";")[0].strip()
    ext_ok = ext in (IMAGE_EXTS if kind == "image" else VIDEO_EXTS)
    mime_ok = declared in (IMAGE_MIMES if kind == "image" else VIDEO_MIMES)
    if not ext_ok and not mime_ok:
        raise UnsupportedFileError("extension and MIME do not match the file content")
    return FileType(kind=kind, mime=mime, ext=ext or (".jpg" if kind == "image" else ".mp4"))
