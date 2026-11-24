"""Entry point: python main.py (desktop test) / buildozer android debug (APK)."""
from __future__ import annotations

from vaultapp.app import VaultApp


if __name__ == "__main__":
    VaultApp().run()
