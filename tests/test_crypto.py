from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vaultapp.core.crypto import (  # noqa: E402
    Argon2Params,
    AuthenticationError,
    CorruptFileError,
    KeyEnvelope,
    decrypt_bytes,
    decrypt_stream,
    encrypt_bytes,
    encrypt_stream,
    verify_encrypted_file,
)
from vaultapp.core.keystore import FileKeystore  # noqa: E402


FAST_PARAMS = Argon2Params(time_cost=1, memory_cost_kib=8192, parallelism=1)


def test_stream_roundtrip_and_chunking():
    payload = os.urandom(1024 * 1024 + 37)
    key = os.urandom(32)
    encrypted = io.BytesIO()
    encrypt_stream(io.BytesIO(payload), encrypted, key, len(payload), chunk_size=4096)
    blob = encrypted.getvalue()
    assert len(blob) > len(payload)
    assert blob[:4] == b"PVA1"
    output = io.BytesIO()
    assert decrypt_stream(io.BytesIO(blob), output, key) == len(payload)
    assert output.getvalue() == payload


def test_tampering_and_truncation_are_rejected():
    payload = os.urandom(20000)
    key = os.urandom(32)
    encrypted = io.BytesIO()
    encrypt_stream(io.BytesIO(payload), encrypted, key, len(payload), chunk_size=4096)
    blob = bytearray(encrypted.getvalue())
    blob[100] ^= 0x40
    with pytest.raises(CorruptFileError):
        decrypt_stream(io.BytesIO(bytes(blob)), io.BytesIO(), key)
    with pytest.raises(CorruptFileError):
        decrypt_stream(io.BytesIO(bytes(blob[:-7])), io.BytesIO(), key)


def test_wrong_key_fails():
    encrypted = io.BytesIO()
    encrypt_stream(io.BytesIO(b"hello world" * 100), encrypted, b"k" * 32, 1100)
    with pytest.raises(CorruptFileError):
        decrypt_stream(io.BytesIO(encrypted.getvalue()), io.BytesIO(), b"x" * 32)


def test_blob_crypto():
    key = os.urandom(32)
    blob = encrypt_bytes(b"secret", key, b"aad")
    assert decrypt_bytes(blob, key, b"aad") == b"secret"
    with pytest.raises(AuthenticationError):
        decrypt_bytes(blob, key, b"wrong")


def test_key_envelope_password_change_keeps_vmk(tmp_path):
    keystore = FileKeystore(tmp_path / "wrapping.key")
    vmk = os.urandom(32)
    envelope = KeyEnvelope.create(vmk, "first password", FAST_PARAMS, keystore)
    parsed = KeyEnvelope.from_bytes(envelope.to_bytes())
    assert bytes(parsed.open("first password", keystore)) == vmk
    with pytest.raises(AuthenticationError):
        parsed.open("wrong password", keystore)
    rewrapped = parsed.rewrap("second password", bytes(parsed.open("first password", keystore)), keystore)
    assert bytes(KeyEnvelope.from_bytes(rewrapped.to_bytes()).open("second password", keystore)) == vmk
    keystore.close()


def test_verify_helper(tmp_path):
    path = tmp_path / "file.enc"
    key = os.urandom(32)
    with open(path, "wb") as handle:
        encrypt_stream(io.BytesIO(b"payload" * 500), handle, key, 3500)
    assert verify_encrypted_file(str(path), key)
    with open(path, "r+b") as handle:
        handle.seek(50)
        handle.write(b"\x00")
    with pytest.raises(CorruptFileError):
        verify_encrypted_file(str(path), key)
