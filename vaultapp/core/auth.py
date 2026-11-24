"""Password setup, unlock, change and in-memory session/lock management."""
from __future__ import annotations

import os
import time
from pathlib import Path

from .crypto import (
    Argon2Params,
    AuthenticationError,
    CryptoError,
    KeyEnvelope,
    new_key,
    wipe,
)
from .keystore import FileKeystore

MAX_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 8
DEFAULT_AUTO_LOCK_SECONDS = 60


class LockedOutError(PermissionError):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"locked for {seconds} seconds")
        self.seconds = seconds


class VaultSession:
    """Holds the decrypted master key only while the app is unlocked."""

    def __init__(self, vmk: bytearray, auto_lock_seconds: int = DEFAULT_AUTO_LOCK_SECONDS) -> None:
        self._vmk = vmk
        self.auto_lock_seconds = auto_lock_seconds
        self.unlocked_at = time.monotonic()
        self.last_activity = self.unlocked_at
        self.locked = False

    @property
    def key(self) -> bytes:
        """A short-lived copy for a single crypto operation."""
        if self.locked:
            raise AuthenticationError("vault is locked")
        return bytes(self._vmk)

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def should_auto_lock(self, now: float | None = None) -> bool:
        if self.locked or self.auto_lock_seconds <= 0:
            return False
        return (now or time.monotonic()) - self.last_activity >= self.auto_lock_seconds

    def lock(self) -> None:
        if not self.locked:
            wipe(self._vmk)
            self.locked = True


class AuthManager:
    def __init__(self, paths, database, keystore=None) -> None:
        self.paths = paths
        self.db = database
        self.keystore = keystore
        self._session: VaultSession | None = None

    # ---------- state ----------
    @property
    def is_setup(self) -> bool:
        return self.paths.keys_file.exists() and self.paths.keys_file.stat().st_size > 0

    @property
    def is_unlocked(self) -> bool:
        return self._session is not None and not self._session.locked

    @property
    def session(self) -> VaultSession | None:
        return self._session if self.is_unlocked else None

    def auto_lock_seconds(self) -> int:
        return max(0, self.db.get_int("auto_lock_seconds", DEFAULT_AUTO_LOCK_SECONDS))

    def set_auto_lock_seconds(self, seconds: int) -> None:
        self.db.set_setting("auto_lock_seconds", str(max(0, int(seconds))))

    # ---------- password lifecycle ----------
    @staticmethod
    def validate_password(password: str) -> None:
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    def setup(self, password: str, confirmation: str) -> VaultSession:
        self.validate_password(password)
        if password != confirmation:
            raise ValueError("passwords do not match")
        if self.is_setup:
            raise RuntimeError("vault is already set up")
        vmk = new_key()
        try:
            envelope = KeyEnvelope.create(bytes(vmk), password, keystore=self.keystore)
            self._write_envelope(envelope)
        finally:
            wipe(vmk)
        self.db.delete_setting("failed_attempts")
        self.db.delete_setting("locked_until")
        self._session = VaultSession(self._load_vmk(password), self.auto_lock_seconds())
        return self._session

    def unlock(self, password: str) -> VaultSession:
        self._check_lockout()
        if not self.is_setup:
            raise RuntimeError("vault has not been set up")
        try:
            envelope = KeyEnvelope.from_bytes(self.paths.keys_file.read_bytes())
            vmk = envelope.open(password, self.keystore)
        except (CryptoError, ValueError, OSError):
            self._record_failure()
            raise AuthenticationError("invalid password")
        self.db.delete_setting("failed_attempts")
        self.db.delete_setting("locked_until")
        self._session = VaultSession(vmk, self.auto_lock_seconds())
        return self._session

    def change_password(self, old_password: str, new_password: str, confirmation: str) -> None:
        self.validate_password(new_password)
        if new_password != confirmation:
            raise ValueError("passwords do not match")
        if not self.is_unlocked or self._session is None:
            raise AuthenticationError("vault is locked")
        envelope = KeyEnvelope.from_bytes(self.paths.keys_file.read_bytes())
        # Verify the current password without disturbing the active session.
        vmk = envelope.open(old_password, self.keystore)
        try:
            new_envelope = envelope.rewrap(new_password, bytes(vmk), self.keystore)
        finally:
            wipe(vmk)
        self._write_envelope(new_envelope)

    def lock(self) -> None:
        if self._session is not None:
            self._session.lock()
        self._session = None

    def touch(self) -> None:
        if self._session:
            self._session.touch()

    def check_auto_lock(self) -> bool:
        if self._session and self._session.should_auto_lock():
            self.lock()
            return True
        return False

    # ---------- internals ----------
    def _load_vmk(self, password: str) -> bytearray:
        envelope = KeyEnvelope.from_bytes(self.paths.keys_file.read_bytes())
        return envelope.open(password, self.keystore)

    def _write_envelope(self, envelope: KeyEnvelope) -> None:
        tmp = self.paths.database_dir / "master.key.enc.tmp"
        tmp.write_bytes(envelope.to_bytes())
        os.replace(str(tmp), str(self.paths.keys_file))
        try:
            os.chmod(self.paths.keys_file, 0o600)
        except OSError:
            pass

    def _check_lockout(self) -> None:
        until = self.db.get_float("locked_until", 0.0)
        if until and time.time() < until:
            raise LockedOutError(max(1, int(until - time.time())))
        if until:
            self.db.delete_setting("locked_until")

    def _record_failure(self) -> None:
        count = self.db.get_int("failed_attempts", 0) + 1
        self.db.set_setting("failed_attempts", str(count))
        if count >= MAX_ATTEMPTS:
            delay = min(30 * (2 ** (count - MAX_ATTEMPTS)), 86400)
            self.db.set_setting("locked_until", str(time.time() + delay))
            raise LockedOutError(delay)
