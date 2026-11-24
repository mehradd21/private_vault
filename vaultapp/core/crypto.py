"""AES-256-GCM streaming encryption, Argon2id KDF and key envelope handling.

Encrypted file format (``PVA1``)::

    header: magic(4) | version(1) | chunk_size(4) | plain_size(8)   [17 bytes]
    repeated: nonce(12) | ciphertext+tag(chunk_size + 16)

Every chunk is authenticated independently with the header and its index as
associated data, so truncation, reordering and tampering are detected. Files
are processed in bounded chunks: multi-gigabyte media never enters RAM whole.
"""
from __future__ import annotations

import hmac
import os
import secrets
import struct
from dataclasses import dataclass
from typing import BinaryIO, Callable, Optional

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"PVA1"
KEY_MAGIC = b"PVK1"
FORMAT_VERSION = 1
DEFAULT_CHUNK_SIZE = 256 * 1024
NONCE_SIZE = 12
TAG_SIZE = 16
KEY_SIZE = 32
HEADER = struct.Struct(">4sBQI")  # 17 bytes
KEY_HEADER = struct.Struct(">4sBBIBB")  # magic, version, flags, mem_cost, t_cost, parallelism
VERIFIER_AAD = b"private-vault-key-envelope-v1"


class CryptoError(Exception):
    """Base class for cryptography failures."""


class CorruptFileError(CryptoError):
    """Encrypted file is truncated, modified or uses an unknown format."""


class AuthenticationError(CryptoError):
    """Password/key did not authenticate."""


@dataclass(frozen=True)
class Argon2Params:
    """Argon2id parameters. Defaults are tuned for mid-range Android devices."""

    time_cost: int = 3
    memory_cost_kib: int = 32 * 1024
    parallelism: int = 2
    hash_len: int = KEY_SIZE

    def derive(self, password: str, salt: bytes) -> bytes:
        if len(salt) < 16:
            raise ValueError("salt must be at least 16 bytes")
        return hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=self.time_cost,
            memory_cost=self.memory_cost_kib,
            parallelism=self.parallelism,
            hash_len=self.hash_len,
            type=Type.ID,
        )

    def to_bytes(self) -> bytes:
        return struct.pack(">BIBB", self.time_cost, self.memory_cost_kib,
                           self.parallelism, self.hash_len)

    @classmethod
    def from_bytes(cls, blob: bytes) -> "Argon2Params":
        t, mem, par, length = struct.unpack(">BIBB", blob)
        if not (1 <= t <= 255 and 8192 <= mem <= 1024 * 1024 and 1 <= par <= 8 and length >= 16):
            raise CryptoError("invalid Argon2 parameters")
        return cls(t, mem, par, length)


def wipe(value: bytearray | bytes | None) -> None:
    """Best-effort in-memory wiping of sensitive material."""
    if isinstance(value, bytearray):
        for i in range(len(value)):
            value[i] = 0


def new_key() -> bytearray:
    return bytearray(secrets.token_bytes(KEY_SIZE))


def encrypt_bytes(data: bytes, key: bytes, aad: bytes = b"") -> bytes:
    """Return nonce || ciphertext||tag for small blobs (thumbnails, envelopes)."""
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def decrypt_bytes(blob: bytes, key: bytes, aad: bytes = b"") -> bytes:
    if len(blob) < NONCE_SIZE + TAG_SIZE:
        raise CorruptFileError("encrypted blob is too short")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_SIZE], blob[NONCE_SIZE:], aad)
    except InvalidTag as exc:
        raise AuthenticationError("blob authentication failed") from exc


def _read_exact(stream: BinaryIO, count: int, what: str) -> bytes:
    chunks = []
    remaining = count
    while remaining:
        piece = stream.read(remaining)
        if not piece:
            raise CorruptFileError(f"unexpected end of file while reading {what}")
        chunks.append(piece)
        remaining -= len(piece)
    return b"".join(chunks)


def encrypt_stream(
    source: BinaryIO,
    destination: BinaryIO,
    key: bytes,
    plain_size: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress: Optional[Callable[[int, int], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> int:
    """Stream-encrypt ``source`` into ``destination``; return bytes encrypted."""
    if plain_size < 0:
        raise ValueError("plain_size must be non-negative")
    if not (1024 <= chunk_size <= 16 * 1024 * 1024):
        raise ValueError("invalid chunk size")
    header = HEADER.pack(MAGIC, FORMAT_VERSION, chunk_size, plain_size)
    destination.write(header)
    aead = AESGCM(key)
    processed = 0
    index = 0
    while True:
        if cancelled and cancelled():
            raise CryptoError("operation cancelled")
        chunk = source.read(chunk_size)
        if not chunk:
            break
        nonce = os.urandom(NONCE_SIZE)
        aad = header + struct.pack(">Q", index)
        destination.write(nonce)
        destination.write(aead.encrypt(nonce, chunk, aad))
        processed += len(chunk)
        index += 1
        if progress:
            progress(processed, plain_size)
    if processed != plain_size:
        raise CorruptFileError("source size changed during encryption")
    return processed


class NullWriter:
    """Discards output; used to verify integrity without storing plaintext."""

    def write(self, data: bytes) -> int:
        return len(data)


def decrypt_stream(
    source: BinaryIO,
    destination: BinaryIO,
    key: bytes,
    progress: Optional[Callable[[int, int], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> int:
    """Verify and stream-decrypt a ``PVA1`` file; return plaintext byte count."""
    header = _read_exact(source, HEADER.size, "header")
    magic, version, chunk_size, plain_size = HEADER.unpack(header)
    if magic != MAGIC or version != FORMAT_VERSION:
        raise CorruptFileError("unknown encrypted file format")
    if not (1024 <= chunk_size <= 16 * 1024 * 1024):
        raise CorruptFileError("invalid chunk size")
    aead = AESGCM(key)
    written = 0
    index = 0
    while written < plain_size:
        if cancelled and cancelled():
            raise CryptoError("operation cancelled")
        nonce = _read_exact(source, NONCE_SIZE, "nonce")
        expected_plain = min(chunk_size, plain_size - written)
        ciphertext = _read_exact(source, expected_plain + TAG_SIZE, "ciphertext")
        aad = header + struct.pack(">Q", index)
        try:
            plain = aead.decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise CorruptFileError(f"authentication failed for chunk {index}") from exc
        destination.write(plain)
        written += len(plain)
        index += 1
        if progress:
            progress(written, plain_size)
    if written != plain_size:
        raise CorruptFileError("decrypted size does not match header")
    return written


def verify_encrypted_file(path: str, key: bytes) -> bool:
    with open(path, "rb") as source:
        decrypt_stream(source, NullWriter(), key)
    return True


class KeyEnvelope:
    """Password-derived key encrypts a random Vault Master Key (VMK).

    When Android Keystore is available, a second wrapped copy of the VMK is
    stored and checked during unlock. Changing the password only re-wraps the
    VMK; no media file needs to be re-encrypted.
    """

    def __init__(
        self,
        params: Argon2Params,
        salt: bytes,
        password_wrapped: bytes,
        keystore_wrapped: bytes | None = None,
    ) -> None:
        self.params = params
        self.salt = salt
        self.password_wrapped = password_wrapped
        self.keystore_wrapped = keystore_wrapped

    @classmethod
    def create(
        cls,
        vmk: bytes,
        password: str,
        params: Argon2Params | None = None,
        keystore=None,
    ) -> "KeyEnvelope":
        params = params or Argon2Params()
        salt = os.urandom(16)
        key = params.derive(password, salt)
        wrapped = encrypt_bytes(vmk, key, VERIFIER_AAD)
        wipe(bytearray(key))
        ks_wrapped = None
        if keystore is not None and keystore.available():
            nonce, ct = keystore.encrypt(vmk, VERIFIER_AAD)
            ks_wrapped = nonce + ct
        return cls(params, salt, wrapped, ks_wrapped)

    def to_bytes(self) -> bytes:
        flags = 1 if self.keystore_wrapped else 0
        out = bytearray(KEY_HEADER.pack(
            KEY_MAGIC, FORMAT_VERSION, flags,
            self.params.memory_cost_kib, self.params.time_cost,
            self.params.parallelism,
        ))
        out += self.salt
        out += self.password_wrapped
        if self.keystore_wrapped:
            out += self.keystore_wrapped
        return bytes(out)

    @classmethod
    def from_bytes(cls, blob: bytes) -> "KeyEnvelope":
        fixed = KEY_HEADER.size + 16 + NONCE_SIZE + KEY_SIZE + TAG_SIZE
        if len(blob) < fixed:
            raise CryptoError("key envelope is truncated")
        magic, version, flags, mem, t, par = KEY_HEADER.unpack_from(blob)
        if magic != KEY_MAGIC or version != FORMAT_VERSION:
            raise CryptoError("unknown key envelope format")
        params = Argon2Params.from_bytes(struct.pack(">BIBB", t, mem, par, KEY_SIZE))
        offset = KEY_HEADER.size
        salt = blob[offset:offset + 16]
        offset += 16
        pw_len = NONCE_SIZE + KEY_SIZE + TAG_SIZE
        password_wrapped = blob[offset:offset + pw_len]
        offset += pw_len
        ks_wrapped = None
        if flags & 1:
            ks_len = NONCE_SIZE + KEY_SIZE + TAG_SIZE
            ks_wrapped = blob[offset:offset + ks_len]
            if len(ks_wrapped) != ks_len:
                raise CryptoError("keystore wrapped key is truncated")
        return cls(params, salt, password_wrapped, ks_wrapped)

    def open(self, password: str, keystore=None) -> bytearray:
        key = self.params.derive(password, self.salt)
        try:
            vmk = decrypt_bytes(self.password_wrapped, key, VERIFIER_AAD)
        finally:
            wipe(bytearray(key))
        if self.keystore_wrapped:
            if keystore is None or not keystore.available():
                raise AuthenticationError("Android Keystore is unavailable; cannot unlock")
            ks_vmk = keystore.decrypt(
                self.keystore_wrapped[:NONCE_SIZE],
                self.keystore_wrapped[NONCE_SIZE:],
                VERIFIER_AAD,
            )
            if not hmac.compare_digest(vmk, ks_vmk):
                raise AuthenticationError("key envelope verification failed")
            wipe(bytearray(ks_vmk))
        result = bytearray(vmk)
        wipe(bytearray(vmk))
        return result

    def rewrap(self, new_password: str, vmk: bytes, keystore=None) -> "KeyEnvelope":
        return KeyEnvelope.create(vmk, new_password, self.params, keystore)
