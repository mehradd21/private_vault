from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conftest import png_bytes  # noqa: E402
from vaultapp.core.crypto import encrypt_stream  # noqa: E402
from vaultapp.core.auth import AuthenticationError, LockedOutError  # noqa: E402
from vaultapp.core.vault import VaultError  # noqa: E402
from vaultapp.utils.mime import UnsupportedFileError  # noqa: E402


def import_png(vault, name="test.png", data=None):
    data = data or png_bytes()
    return vault.import_stream(io.BytesIO(data), name, "image/png", len(data))


def test_setup_unlock_lock(vault, tmp_path):
    from vaultapp.utils.paths import VaultPaths
    from vaultapp.core.service import VaultService

    assert vault.is_unlocked
    vault.lock()
    assert not vault.is_unlocked
    with pytest.raises(VaultError):
        vault.repo._key()

    service = VaultService(VaultPaths(vault.paths.root))
    with pytest.raises(AuthenticationError):
        service.unlock("wrong password")
    service.unlock("StrongPass123")
    assert service.is_unlocked
    service.db.close()


def test_import_export_delete(vault, tmp_path):
    data = png_bytes()
    result = import_png(vault, data=data)
    assert result.record is not None and not result.errors
    record = result.record
    stored = vault.paths.images / record["stored_name"]
    assert stored.exists() and stored.stat().st_size > len(data)
    assert record["stored_name"].endswith(".enc")
    assert vault.db.get_file(record["id"])["display_name"] == "test.png"
    assert vault.thumbnail(record) is not None
    assert vault.verify(record["id"])

    destination = tmp_path / "exported.png"
    exported = vault.export_to_path(record["id"], destination)
    assert exported.read_bytes() == data

    with open(stored, "r+b") as handle:
        handle.seek(60)
        handle.write(b"\xff")
    with pytest.raises(Exception):  # tampering is detected
        vault.verify(record["id"])
    with pytest.raises(Exception):
        vault.export_to_path(record["id"], tmp_path / "bad.png")

    assert vault.delete(record["id"])
    assert not stored.exists()
    assert vault.db.get_file(record["id"]) is None
    assert vault.stats()["total"] == 0


def test_hidden_and_rename(vault):
    record = import_png(vault, "family.png").record
    assert vault.stats()["images"] == 1
    vault.set_hidden(record["id"], True)
    assert vault.list_files(hidden=True)[0]["id"] == record["id"]
    assert vault.list_files(hidden=False) == []
    vault.rename(record["id"], "new name")
    assert vault.db.get_file(record["id"])["display_name"] == "new name"
    vault.set_hidden(record["id"], False)
    assert len(vault.list_files(hidden=False)) == 1


def test_invalid_files_rejected(vault):
    result = vault.import_stream(io.BytesIO(b"not a media file" * 100), "virus.exe", None, 1600)
    assert result.record is None and result.errors
    assert vault.stats()["total"] == 0
    real_png = png_bytes()
    with pytest.raises(UnsupportedFileError):
        from vaultapp.utils.mime import validate
        validate("fake.png", "image/png", b"MZ\x90\x00")


def test_failed_attempts_lockout(tmp_path):
    from vaultapp.utils.paths import VaultPaths
    from vaultapp.core.service import VaultService

    service = VaultService(VaultPaths(tmp_path / "locked"))
    service.setup("StrongPass123", "StrongPass123")
    service.lock()
    locked_out = False
    for _ in range(7):
        try:
            service.unlock("bad password")
        except LockedOutError:
            locked_out = True
            break
        except AuthenticationError:
            continue
    assert locked_out
    service.db.close()


def test_temp_decryption_and_cleanup(vault):
    record = import_png(vault, "temp.png").record
    path = vault.decrypt_to_temp(record["id"])
    assert path.read_bytes() == png_bytes()
    assert path.parent == vault.paths.temp
    vault.repo.temp_files.cleanup(min_age_seconds=0)
    assert not path.exists()


def test_no_plaintext_in_public_storage(vault, tmp_path):
    record = import_png(vault).record
    assert str(vault.paths.images).startswith(str(vault.paths.root))
    plaintext = png_bytes()
    assert not any(plaintext[:64] == p.read_bytes()[:64]
                   for p in vault.paths.images.iterdir() if p.is_file())
