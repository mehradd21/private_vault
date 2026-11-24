"""Key wrapping backends.

Android Keystore holds a non-exportable AES-256 key used to wrap the random
Vault Master Key. The desktop fallback exists only for tests; it stores a
random wrapping key in a private file (never in SQLite, never in public
storage) so the same unit tests can run without an Android device.
"""
from __future__ import annotations

import os
from pathlib import Path

from .crypto import encrypt_bytes, decrypt_bytes, new_key, wipe
from ..utils.platform import is_android


class KeystoreUnavailable(RuntimeError):
    pass


class AndroidKeystore:
    """AES/GCM/NoPadding key stored in AndroidKeyStore (API 23+)."""

    ALIAS = "private_vault_wrapping_v1"

    def __init__(self) -> None:
        from jnius import autoclass

        self._autoclass = autoclass
        self.KeyStore = autoclass("java.security.KeyStore")
        self.Cipher = autoclass("javax.crypto.Cipher")
        self.KeyProperties = autoclass("android.security.keystore.KeyProperties")
        self.Builder = autoclass("android.security.keystore.KeyGenParameterSpec$Builder")
        self.KeyPairGenerator = autoclass("java.security.KeyPairGenerator")
        self.GCMParameterSpec = autoclass("javax.crypto.spec.GCMParameterSpec")
        self.ks = self.KeyStore.getInstance("AndroidKeyStore")
        self.ks.load(None)
        if not self.ks.containsAlias(self.ALIAS):
            spec = (
                self.Builder(
                    self.ALIAS,
                    self.KeyProperties.PURPOSE_ENCRYPT | self.KeyProperties.PURPOSE_DECRYPT,
                )
                .setBlockModes(self.KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(self.KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setUserAuthenticationRequired(False)
                .build()
            )
            generator = self.KeyPairGenerator.getInstance(
                self.KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore"
            )
            generator.initialize(spec)
            generator.generateKey()
        self.key = self.ks.getKey(self.ALIAS, None)

    def available(self) -> bool:
        return self.key is not None

    def _cipher(self, mode: int, nonce: bytes | None):
        cipher = self.Cipher.getInstance("AES/GCM/NoPadding")
        if mode == self.Cipher.ENCRYPT_MODE:
            cipher.init(mode, self.key)
        else:
            cipher.init(mode, self.key, self.GCMParameterSpec(128, bytearray(nonce)))
        return cipher

    def encrypt(self, data: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
        cipher = self._cipher(self.Cipher.ENCRYPT_MODE, None)
        if aad:
            cipher.updateAAD(bytearray(aad))
        nonce = bytes(bytearray(cipher.getIV()))
        ciphertext = bytes(bytearray(cipher.doFinal(bytearray(data))))
        return nonce, ciphertext

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
        cipher = self._cipher(self.Cipher.DECRYPT_MODE, nonce)
        if aad:
            cipher.updateAAD(bytearray(aad))
        return bytes(bytearray(cipher.doFinal(bytearray(ciphertext))))


class FileKeystore:
    """Non-Android test backend: random wrapping key in a 0600 private file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            key = new_key()
            blob = encrypt_bytes(bytes(key), _FILE_KEY)
            self.path.write_bytes(blob)
            wipe(key)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        encrypted = self.path.read_bytes()
        self.key = bytearray(decrypt_bytes(encrypted, _FILE_KEY))

    def available(self) -> bool:
        return True

    def encrypt(self, data: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
        blob = encrypt_bytes(data, bytes(self.key), aad)
        return blob[:12], blob[12:]

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
        from .crypto import AuthenticationError, CorruptFileError
        from cryptography.exceptions import InvalidTag

        try:
            return decrypt_bytes(nonce + ciphertext, bytes(self.key), aad)
        except (InvalidTag, AuthenticationError, CorruptFileError) as exc:
            raise RuntimeError("wrapped key authentication failed") from exc

    def close(self) -> None:
        wipe(self.key)


# A fixed local key used *only* to protect the test backend's wrapping key file.
# It is not used to encrypt any user media and is never shipped on Android.
_FILE_KEY = bytes.fromhex(
    "3f7c1b42d6e08a5f9c2d47b6a1e38f05c9b2d7a6418fe03b5d20c8a7f619b4e3"
)


def get_keystore(path: str | Path):
    """Return the strongest available wrapping backend."""
    if is_android():
        try:
            return AndroidKeystore()
        except Exception:
            # API < 23 or a broken keystore: app-private file fallback.
            return FileKeystore(Path(path) / "wrapping.key")
    return FileKeystore(Path(path) / "wrapping.key")
