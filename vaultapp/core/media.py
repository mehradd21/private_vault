"""Encrypted thumbnail creation and media metadata extraction."""
from __future__ import annotations

import io
from pathlib import Path

from ..utils.platform import is_android

THUMB_MAX_SIDE = 320
THUMB_AAD = b"private-vault-thumbnail-v1"


def make_image_thumbnail(data: bytes, max_side: int = THUMB_MAX_SIDE) -> bytes | None:
    """Create a small JPEG from decrypted image bytes (never written to disk)."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        image.thumbnail((max_side, max_side), Image.LANCZOS)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=78, optimize=True)
        return output.getvalue()
    except Exception:
        return None


def video_thumbnail(path: str | Path, max_side: int = THUMB_MAX_SIDE) -> bytes | None:
    """Extract a video preview frame with Android's MediaMetadataRetriever."""
    if not is_android():
        return None
    try:
        from jnius import autoclass

        retriever = autoclass("android.media.MediaMetadataRetriever")()
        retriever.setDataSource(str(path))
        bitmap = retriever.getFrameAtTime(1_000_000)  # 1 second
        retriever.release()
        if bitmap is None:
            return None
        Bitmap = autoclass("android.graphics.Bitmap")
        CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
        stream = autoclass("java.io.ByteArrayOutputStream")()
        bitmap.compress(CompressFormat.JPEG, 78, stream)
        result = bytes(bytearray(stream.toByteArray()))
        stream.close()
        bitmap.recycle()
        if len(result) > max_side * max_side:
            return make_image_thumbnail(result, max_side)
        return result
    except Exception:
        return None


def video_metadata_uri(uri, max_side: int = THUMB_MAX_SIDE) -> tuple[bytes | None, int | None]:
    """Read a preview frame and duration directly from a SAF content Uri."""
    if not is_android():
        return None, None
    try:
        from jnius import autoclass

        retriever_cls = autoclass("android.media.MediaMetadataRetriever")
        retriever = retriever_cls()
        context = autoclass("org.kivy.android.PythonActivity").mActivity
        retriever.setDataSource(context, uri)
        value = retriever.extractMetadata(retriever_cls.METADATA_KEY_DURATION)
        duration = int(value) if value and value.isdigit() else None
        bitmap = retriever.getFrameAtTime(1_000_000)
        thumb = _bitmap_to_jpeg(bitmap, max_side) if bitmap is not None else None
        retriever.release()
        return thumb, duration
    except Exception:
        return None, None


def _bitmap_to_jpeg(bitmap, max_side: int) -> bytes | None:
    try:
        from jnius import autoclass

        CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
        stream = autoclass("java.io.ByteArrayOutputStream")()
        bitmap.compress(CompressFormat.JPEG, 78, stream)
        result = bytes(bytearray(stream.toByteArray()))
        stream.close()
        bitmap.recycle()
        if len(result) > max_side * max_side:
            return make_image_thumbnail(result, max_side)
        return result
    except Exception:
        return None


def video_duration_ms(path: str | Path) -> int | None:
    if is_android():
        try:
            from jnius import autoclass

            retriever = autoclass("android.media.MediaMetadataRetriever")()
            retriever.setDataSource(str(path))
            value = retriever.extractMetadata(
                autoclass("android.media.MediaMetadataRetriever").METADATA_KEY_DURATION
            )
            retriever.release()
            return int(value) if value and value.isdigit() else None
        except Exception:
            return None
    try:
        from ffpyplayer.player import MediaPlayer

        player = MediaPlayer(str(path))
        duration = player.get_metadata().get("duration")
        player.close_player()
        return int(duration * 1000) if duration else None
    except Exception:
        return None
