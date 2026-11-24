"""Full-screen image viewer with zoom and swipe navigation."""
from __future__ import annotations

import io

from kivy.app import App
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.screenmanager import Screen
from kivy.uix.scatterlayout import ScatterLayout

from ..widgets import ConfirmDialog, InputDialog, MessageDialog, PersianLabel, SecondaryButton
from ...utils.strings import t
from .home import human_size


class ImageViewerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="image_viewer", **kwargs)
        self._core = None
        self.index = 0
        self.records: list[dict] = []
        root = BoxLayout(orientation="vertical")

        self.scatter = ScatterLayout(do_rotation=False, do_scale=True, scale_min=1, scale_max=6)
        self.image = Image(allow_stretch=True)
        self.scatter.add_widget(self.image)
        root.add_widget(self.scatter)

        self.info = PersianLabel(text="", font_size="12sp", size_hint_y=0.09)
        root.add_widget(self.info)

        actions = BoxLayout(size_hint_y=0.10, spacing=dp(4), padding=dp(4))
        for text, callback in (
            ("قبلی", self._previous),
            ("بعدی", self._next),
            (t("open_with"), self._open_with),
            (t("export"), self._export),
            (t("hide"), self._hide),
            (t("delete"), self._delete),
        ):
            actions.add_widget(SecondaryButton(text=text, on_press=callback))
        root.add_widget(actions)
        back = SecondaryButton(text="بازگشت", size_hint_y=0.08, on_press=lambda *_: self._back())
        root.add_widget(back)
        self.add_widget(root)
        self.bind(size=self._bind_scatter)

    def _bind_scatter(self, *args):
        self.scatter.size = self.size

    def on_enter(self):
        self.index = getattr(App.get_running_app(), "viewer_index", 0)
        self.records = list(getattr(App.get_running_app(), "viewer_records", []))
        self.show()

    def on_touch_move(self, touch):
        if super().on_touch_move(touch):
            return True
        if abs(touch.dx) > dp(80) and abs(touch.dx) > abs(touch.dy):
            self._next() if touch.dx < 0 else self._previous()
            return True
        return False

    def show(self):
        if not self.records:
            self._back()
            return
        self.index %= len(self.records)
        record = self.records[self.index]
        data = App.get_running_app().service.preview(record)
        extension = record.get("original_ext", ".jpg").lstrip(".") or "jpg"
        self._core = CoreImage(io.BytesIO(data), ext=extension) if data else None
        self.image.texture = self._core.texture if self._core else None
        self.scatter.scale = 1
        self.scatter.pos = (0, 0)
        self.info.text = (
            f"{record['display_name']} | {human_size(record['size'])} | "
            f"{self.index + 1}/{len(self.records)}"
        )

    def record(self) -> dict:
        return self.records[self.index]

    def _previous(self, *_):
        self.index = (self.index - 1) % max(1, len(self.records))
        self.show()

    def _next(self, *_):
        self.index = (self.index + 1) % max(1, len(self.records))
        self.show()

    def _back(self, *_):
        App.get_running_app().root.current = "gallery"

    def _open_with(self, *_):
        if not App.get_running_app().service.open_with(self.record()["id"]):
            MessageDialog("این قابلیت فقط در اندروید در دسترس است").open()

    def _export(self, *_):
        App.get_running_app().export_single(self.record())

    def _hide(self, *_):
        app = App.get_running_app()
        app.service.set_hidden(self.record()["id"], True)
        MessageDialog("فایل به فایلهای مخفی منتقل شد").open()
        self._back()

    def _delete(self, *_):
        ConfirmDialog(t("delete_confirm"), on_confirm=self._do_delete, confirm_text=t("delete")).open()

    def _do_delete(self):
        file_id = self.record()["id"]
        App.get_running_app().service.delete(file_id)
        self.records = [r for r in self.records if r["id"] != file_id]
        if self.records:
            self.index = min(self.index, len(self.records) - 1)
            self.show()
        else:
            self._back()
