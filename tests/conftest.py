from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vaultapp.core.service import VaultService  # noqa: E402
from vaultapp.utils.paths import VaultPaths  # noqa: E402


def png_bytes(color=(90, 120, 200), size=(640, 480)) -> bytes:
    image = Image.new("RGB", size, color)
    for x in range(0, size[0], 40):
        for y in range(0, size[1], 40):
            image.putpixel((min(x + 20, size[0] - 1), min(y + 20, size[1] - 1)), (240, 30, 90))
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def vault(tmp_path):
    service = VaultService(VaultPaths(tmp_path / "private"))
    service.setup("StrongPass123", "StrongPass123")
    yield service
    service.auth.lock()
    service.db.close()
