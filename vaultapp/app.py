"""Kivy application: screen navigation, Android intents and lifecycle wiring."""
from __future__ import annotations

import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from . import APP_NAME
from .core import android_api, lifecycle
from .core.service import VaultService
from .ui.screens.auth import SetupScreen, UnlockScreen
from .ui.screens.gallery import GalleryScreen
from .ui.screens.home import HomeScreen
from .ui.screens.import_review import ImportReviewScreen
from .ui.screens.settings import SettingsScreen
from .ui.screens.video import VideoPlayerScreen
from .ui.screens.viewer import ImageViewerScreen
from .ui.widgets import InputDialog, MessageDialog
from .utils.platform import is_android
from .utils.strings import t


class VaultApp(App):
    title = APP_NAME

    def build(self):
        self.service = VaultService()
        self.viewer_records: list[dict] = []
        self.viewer_index = 0
        self.playing_record = None
        self._pending_export: list[dict] = []
        self._pending_import_items: list[dict] = []
        self._ignore_next_return = False

        manager = ScreenManager(transition=FadeTransition(duration=0.18))
        for screen in (
            SetupScreen(),
            UnlockScreen(),
            HomeScreen(),
            ImportReviewScreen(),
            GalleryScreen(mode="gallery"),
            GalleryScreen(mode="hidden"),
            ImageViewerScreen(),
            VideoPlayerScreen(),
            SettingsScreen(),
        ):
            manager.add_widget(screen)
        self.root = manager

        android_api.bind_activity_result(self._on_activity_result)
        lifecycle.install(self.service, self.lock_app, self._returning)
        Clock.schedule_interval(self._check_auto_lock, 1)
        Clock.schedule_once(lambda dt: self._route_initial(), 0)
        return manager

    # ---------- navigation ----------
    def _route_initial(self, *_):
        self.root.current = "setup" if not self.service.is_setup else "unlock"

    def show_home(self):
        # If the app was locked while a file selection was pending, restore
        # the review screen after the user unlocks instead of losing it.
        if self._pending_import_items and self.service.is_unlocked:
            self._show_import_review(self._pending_import_items)
            return
        self.root.get_screen("home").refresh()
        self.root.current = "home"

    def clear_pending_import(self):
        self._pending_import_items = []

    def lock_app(self, *_):
        self.service.lock()
        self.root.current = "unlock"
        unlock = self.root.get_screen("unlock")
        if hasattr(unlock, "password"):
            unlock.password.text = ""
            unlock.refresh_attempts()

    def _returning(self, *_):
        # The result callback itself navigates to the next relevant screen.
        if self._ignore_next_return:
            self._ignore_next_return = False
            self.service.cleanup_temp_files()
            return
        # Never auto-unlock on resume; the unlock screen is always shown.
        self.root.current = "unlock"
        self.service.cleanup_temp_files()

    def _check_auto_lock(self, *_):
        if self.service.is_unlocked and self.service.check_auto_lock():
            self.lock_app()

    def on_stop(self):
        self.service.lock()
        self.service.db.close()

    # ---------- import ----------
    def pick_files(self):
        if is_android():
            android_api.open_documents()
            return
        InputDialog("مسیر فایلها را وارد کنید (با کاما جدا شوند)", "",
                    self._desktop_files).open()

    def _desktop_files(self, value: str):
        from pathlib import Path

        items = []
        for raw in value.split(","):
            path = Path(raw.strip().strip('"'))
            if path.is_file():
                items.append({
                    "name": path.name, "size": path.stat().st_size, "mime": None,
                    "uri": None, "path": str(path),
                })
        if not items:
            MessageDialog(t("empty_selection")).open()
            return
        self._show_import_review(items)

    def _on_activity_result(self, request_code, result_code, intent):
        self._ignore_next_return = True
        # Give other apps a moment to finish reading temporary shared files.
        Clock.schedule_once(
            lambda dt: self.service.repo.temp_files.cleanup(min_age_seconds=1), 1
        )
        if result_code != -1:  # Activity.RESULT_OK
            return
        if request_code == android_api.REQUEST_IMPORT:
            items = []
            for uri in android_api.result_uris(intent, request_code):
                name, size, mime = android_api.uri_metadata(uri)
                android_api.persist_read_permission(uri)
                items.append({
                    "name": name, "size": size, "mime": mime,
                    "uri": uri, "path": None,
                })
            if items:
                self._show_import_review(items)
        elif request_code == android_api.REQUEST_EXPORT_DIR and intent is not None:
            tree_uri = intent.getData()
            android_api.persist_write_permission(tree_uri)
            records = self._pending_export or getattr(
                self.root.get_screen("gallery"), "_pending_export", []
            )
            self.export_records(records, tree_uri)

    def _show_import_review(self, items):
        self._pending_import_items = list(items)
        screen = self.root.get_screen("import_review")
        screen.items = items
        screen.refresh()
        self.root.current = "import_review"

    # ---------- export ----------
    def export_single(self, record):
        self._pending_export = [record]
        if is_android():
            android_api.open_document_tree()
        else:
            InputDialog(t("save_as"), str(self.service.paths.root / "exported"),
                        lambda destination: self.export_records([record], destination)).open()

    def export_records(self, records, destination):
        if not records:
            return
        from .utils.platform import is_android

        def worker():
            failures = []
            for record in records:
                try:
                    if is_android():
                        self.service.export_to_saf_tree(record["id"], destination)
                    else:
                        from pathlib import Path

                        path = Path(destination)
                        path.mkdir(parents=True, exist_ok=True)
                        self.service.export_to_path(record["id"], path)
                except Exception as exc:
                    failures.append(f"{record['display_name']}: {exc}")
            Clock.schedule_once(lambda dt: self._export_finished(failures), 0)

        threading.Thread(target=worker, daemon=True).start()
        self._pending_export = []

    def _export_finished(self, failures):
        MessageDialog(t("success") if not failures else t("error") + "\n" + "\n".join(failures[:5])).open()

    # ---------- media ----------
    def play_video(self, record):
        self.playing_record = record
        self.root.current = "video_player"
