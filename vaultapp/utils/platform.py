"""Platform detection without importing Kivy or pyjnius at import time."""
from __future__ import annotations

import os
import sys


def is_android() -> bool:
    return sys.platform == "android" or "ANDROID_ROOT" in os.environ


def is_desktop() -> bool:
    return not is_android()
