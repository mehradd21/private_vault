"""Review selected files, run streaming import and confirm original deletion."""
from __future__ import annotations

import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

from ..widgets import Card, ConfirmDialog, MessageDialog, PersianLabel, SecondaryButton, VaultButton
from ...utils.strings import t
from .home import human_size


class ImportReviewScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="import_review", **kwargs)
        self.items: list[dict] = []
        self.cancelled = False
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))

        root.add_widget(PersianLabel(text=t("import_review"), font_size="24sp", size_hint_y=0.08))
        self.summary = PersianLabel(font_size="15sp", size_hint_y=0.07)
        root.add_widget(self.summary)

        scroll = ScrollView(size_hint_y=0.55)
        self.list_layout = GridLayout(cols=1, spacing=dp(8), size_hint_y=None, pad=dp(4))
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        self.progress = ProgressBar(max=100, value=0, size_hint_y=0.05)
        root.add_widget(self.progress)
        self.status = PersianLabel(font_size="14sp", size_hint_y=0.06)
        root.add_widget(self.status)

        buttons = BoxLayout(size_hint_y=0.10, spacing=dp(10))
        buttons.add_widget(VaultButton(text=t("start_import"), on_press=self._start))
        buttons.add_widget(SecondaryButton(text=t("cancel"), on_press=lambda *_: self._cancel()))
        root.add_widget(buttons)
        self.start_button = buttons.children[-1]
        self.add_widget(root)

    def on_enter(self):
        self.cancelled = False
        self.progress.value = 0
        self.status.text = ""
        self.refresh()

    def refresh(self):
        self.list_layout.clear_widgets()
        total = sum(item.get("size") or 0 for item in self.items)
        self.summary.text = f"{len(self.items)} | {human_size(total)}"
        for item in self.items:
            row = Card(size_hint_y=None, height=dp(52), padding=dp(10))
            row.add_widget(PersianLabel(
                text=f"{item['name']}   ({human_size(item.get('size') or 0)})", font_size="14sp"
            ))
            self.list_layout.add_widget(row)

    def _cancel(self):
        self.cancelled = True
        self.status.text = "در حال لغو..."
        App.get_running_app().clear_pending_import()
        App.get_running_app().show_home()

    def _start(self, *_):
        if not self.items:
            MessageDialog(t("empty_selection")).open()
            return
        self.cancelled = False
        self.start_button.disabled = True
        self.status.text = t("importing")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        from ...core import android_api
        from ...utils.platform import is_android

        service = App.get_running_app().service
        succeeded = []
        errors = []
        for index, item in enumerate(self.items):
            if self.cancelled:
                break
            try:
                if is_android() and item.get("uri"):
                    android_api.persist_read_permission(item["uri"])
                    source = android_api.ContentStream(item["uri"])
                elif item.get("path"):
                    source = open(item["path"], "rb")
                else:
                    raise OSError("source is unavailable")

                def progress(done, total, i=index):
                    fraction = (i + (done / max(1, total))) / max(1, len(self.items)) * 100
                    Clock.schedule_once(lambda dt, f=fraction: setattr(self.progress, "value", f), 0)

                def cancelled():
                    return self.cancelled

                result = service.import_stream(
                    source, item["name"], item.get("mime"), item.get("size") or 0,
                    uri=item.get("uri") if item.get("uri") else item.get("path"),
                    progress=progress, cancelled=cancelled,
                )
                source.close()
                if result.record:
                    succeeded.append(item)
                errors.extend(result.errors)
            except Exception as exc:
                errors.append(f"{item['name']}: {exc}")
            Clock.schedule_once(
                lambda dt, i=index: setattr(self.progress, "value", (i + 1) / len(self.items) * 100), 0
            )
        Clock.schedule_once(lambda dt: self._finish(succeeded, errors), 0)

    def _finish(self, succeeded, errors):
        App.get_running_app().clear_pending_import()
        self.start_button.disabled = False
        message = t("import_done") if succeeded and not errors else (
            t("import_errors") + (("\n" + "\n".join(errors[:5])) if errors else "")
        )
        if succeeded:
            ConfirmDialog(
                t("delete_originals_question"),
                on_confirm=lambda: self._delete_originals(succeeded, errors),
                confirm_text=t("delete"),
            ).open()
        else:
            MessageDialog(message).open()
        self.status.text = message

    def _delete_originals(self, items, errors):
        failed = App.get_running_app().service.remove_originals(items)
        if failed:
            MessageDialog(t("delete_originals_failed") + "\n" + "\n".join(failed)).open()
        else:
            MessageDialog(t("success")).open()
