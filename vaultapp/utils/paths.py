"""All private storage paths live under the app's internal storage."""
from __future__ import annotations

import os
from pathlib import Path

from ..utils.platform import is_android


class VaultPaths:
    """Directory layout.

    On Android the root is ``Context.getFilesDir()`` (Internal App Storage),
    never ``Android/data`` and never public/shared storage. On desktop a
    directory inside the user's home is used so the same code can be tested.
    """

    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self.root = Path(root) if root is not None else Path(self._default_root())
        self.vault = self.root / "vault"
        self.images = self.vault / "images"
        self.videos = self.vault / "videos"
        self.thumbnails = self.vault / "thumbnails"
        self.database_dir = self.vault / "database"
        self.temp = self.vault / "temp"
        self.db_file = self.database_dir / "vault.db"
        self.keys_file = self.database_dir / "master.key.enc"
        self.keystore_file = self.database_dir / "wrapping.key"
        self.settings_file = self.database_dir / "settings.json"

    @staticmethod
    def _default_root() -> str:
        if is_android():
            # python-for-android exports ANDROID_APP_PATH == Context.getFilesDir().
            env_root = os.environ.get("ANDROID_APP_PATH")
            if env_root:
                return env_root
            try:
                from jnius import autoclass

                activity = autoclass("org.kivy.android.PythonActivity").mActivity
                return activity.getFilesDir().getAbsolutePath()
            except Exception:
                # Last resort: Kivy's user data dir is still app-private.
                from kivy.app import App

                return App.get_running_app().user_data_dir
        return os.path.join(os.path.expanduser("~"), ".private_vault_desktop")

    def create(self) -> None:
        for directory in (
            self.images,
            self.videos,
            self.thumbnails,
            self.database_dir,
            self.temp,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if is_android():
            try:
                os.chmod(self.temp, 0o700)
            except OSError:
                pass

    def media_dir(self, kind: str) -> Path:
        return self.images if kind == "image" else self.videos

    def cleanup_temp(self, max_age_seconds: int = 86400) -> int:
        """Remove abandoned temporary plaintext files."""
        import time

        removed = 0
        now = time.time()
        for path in self.temp.iterdir():
            try:
                if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed
