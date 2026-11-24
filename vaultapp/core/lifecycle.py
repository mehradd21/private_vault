"""Background/screen-off locking, FLAG_SECURE and neutral Recent Apps view."""
from __future__ import annotations

from typing import Callable

from ..utils.platform import is_android

_receiver = None  # keep a strong reference for the lifetime of the app
_lifecycle = None


def set_secure_flag() -> bool:
    """Block screenshots, screen recording and thumbnails in Recent Apps."""
    if not is_android():
        return False
    try:
        from jnius import autoclass

        window = autoclass("org.kivy.android.PythonActivity").mActivity.getWindow()
        params = autoclass("android.view.WindowManager$LayoutParams")
        window.addFlags(params.FLAG_SECURE)
        return True
    except Exception:
        return False


def neutralize_recents() -> bool:
    if not is_android():
        return False
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        description = autoclass("android.app.ActivityManager$TaskDescription")("App", None, 0x0B0B14)
        activity.setTaskDescription(description)
        return True
    except Exception:
        return False


def _install_screen_receiver(on_screen_off: Callable[[], None]) -> bool:
    global _receiver
    if not is_android():
        return False
    try:
        from jnius import PythonJavaClass, autoclass, java_method

        class ScreenReceiver(PythonJavaClass):
            __javainterfaces__ = ["android/content/BroadcastReceiver"]

            def __init__(self, callback):
                super().__init__()
                self.callback = callback

            @java_method("(Landroid/content/Context;Landroid/content/Intent;)V")
            def onReceive(self, context, intent):
                self.callback()

        intent_cls = autoclass("android.content.Intent")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        _receiver = ScreenReceiver(on_screen_off)
        activity.registerReceiver(_receiver, intent_cls(intent_cls.ACTION_SCREEN_OFF))
        return True
    except Exception:
        return False


def install(service, on_lock: Callable[[], None], on_return: Callable[[], None]) -> bool:
    """Wire all 'app went away' signals to an immediate lock."""
    global _lifecycle
    set_secure_flag()
    neutralize_recents()

    def lock_now(*args):
        service.lock()
        on_lock()

    def returning(*args):
        service.cleanup_temp_files()
        on_return()

    _install_screen_receiver(lock_now)

    if not is_android():
        return False
    try:
        from android import activity as android_activity

        if not hasattr(android_activity, "register_activity_lifecycle_callbacks"):
            return False
        _lifecycle = android_activity.register_activity_lifecycle_callbacks(
            onActivityPaused=lock_now,
            onActivityStopped=lock_now,
            onActivityResumed=returning,
        )
        return True
    except Exception:
        return False
