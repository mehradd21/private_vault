"""Internal gallery: tabs, search, sorting, multi-select and file actions."""
from __future__ import annotations

import io
import threading

from kivy.app import App
from kivy.core.image import Image as CoreImage
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from ..widgets import (
    ConfirmDialog,
    InputDialog,
    MessageDialog,
    PersianLabel,
    SecondaryButton,
    SelectionTile,
    VaultButton,
)
from ...utils.strings import t
from .home import human_size


class GalleryScreen(Screen):
    def __init__(self, mode: str = "gallery", **kwargs):
        super().__init__(name=mode, **kwargs)
        self.mode = mode
        self.records: list[dict] = []
        self.selected: set[int] = set()
        self._textures: dict[int, CoreImage] = {}
        self._generation = 0

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        tabs = BoxLayout(size_hint_y=0.08, spacing=dp(6))
        for text, kind in ((t("images"), "image"), (t("videos"), "video")):
            tabs.add_widget(SecondaryButton(text=text, on_press=lambda *_,
                                                                   kind=kind: self._filter(kind)))
        tabs.add_widget(VaultButton(text="همه", size_hint_x=0.7,
                                    on_press=lambda *_: self._filter(None)))
        root.add_widget(tabs)

        controls = BoxLayout(size_hint_y=0.07, spacing=dp(6))
        self.search = TextInput(hint_text=t("search"), multiline=False, font_size="14sp",
                                background_color=(0.11, 0.12, 0.23, 1),
                                foreground_color=(0.93, 0.94, 0.98, 1))
        self.search.bind(text=lambda *_: self.load())
        controls.add_widget(self.search)
        self.sort = Spinner(text=t("sort_newest"),
                            values=(t("sort_newest"), t("sort_oldest"), t("sort_name"), t("sort_size")),
                            size_hint_x=0.4, background_color=(0.16, 0.17, 0.30, 1))
        self.sort.bind(text=lambda *_: self.load())
        controls.add_widget(self.sort)
        root.add_widget(controls)

        self.count = PersianLabel(font_size="14sp", size_hint_y=0.05)
        root.add_widget(self.count)

        self.scroll = ScrollView(size_hint_y=0.57)
        self.grid = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, pad=dp(4))
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.scroll.add_widget(self.grid)
        root.add_widget(self.scroll)

        actions = BoxLayout(size_hint_y=0.11, spacing=dp(6))
        for text, callback in (
            (t("details"), self._open_selected),
            (t("hide") if self.mode != "hidden" else t("unhide"), self._toggle_hidden),
            (t("export"), self._export_selected),
            (t("rename"), self._rename_selected),
            (t("delete"), self._delete_selected),
        ):
            actions.add_widget(SecondaryButton(text=text, on_press=callback))
        more = BoxLayout(size_hint_y=0.07, spacing=dp(6))
        more.add_widget(SecondaryButton(text=t("open_with"), on_press=self._open_with))
        more.add_widget(SecondaryButton(text=t("select_all"), on_press=self._select_all))
        root.add_widget(actions)
        root.add_widget(more)
        self.add_widget(root)

    # ---------- loading ----------
    def on_enter(self):
        App.get_running_app().service.touch()
        self.load()

    def on_leave(self):
        self._generation += 1

    def _filter(self, kind):
        self.kind_filter = kind
        self.load()

    kind_filter = None

    def load(self):
        app = App.get_running_app()
        sort_map = {
            t("sort_newest"): "newest",
            t("sort_oldest"): "oldest",
            t("sort_name"): "name",
            t("sort_size"): "size",
        }
        hidden = self.mode == "hidden"
        kind = getattr(self, "kind_filter", None)
        self.records = app.service.list_files(
            kind=kind if kind in ("image", "video") else None,
            hidden=hidden,
            query=self.search.text.strip(),
            sort=sort_map.get(self.sort.text, "newest"),
        )
        self.selected.clear()
        self._generation += 1
        generation = self._generation
        self.grid.clear_widgets()
        self._textures.clear()
        total = sum(record["size"] for record in self.records)
        self.count.text = f"{len(self.records)} | {human_size(total)}"
        threading.Thread(target=self._load_thumbnails, args=(generation,), daemon=True).start()

    def _load_thumbnails(self, generation: int):
        app = App.get_running_app()
        for record in list(self.records):
            if generation != self._generation:
                return
            data = app.service.thumbnail(record)
            Clock.schedule_once(
                lambda dt, r=record, d=data, g=generation: self._add_tile(r, d, g), 0
            )

    def _add_tile(self, record, data, generation):
        if generation != self._generation:
            return
        texture = None
        if data:
            try:
                image = CoreImage(io.BytesIO(data), ext="jpg")
                self._textures[record["id"]] = image
                texture = image.texture
            except Exception:
                texture = None
        label = record["display_name"]
        if record["kind"] == "video" and record.get("duration_ms"):
            label += f"\n{record['duration_ms'] // 1000}s"
        tile = SelectionTile(texture=texture, label=label, file_id=record["id"])
        tile.bind(on_touch_down=self._tile_touched)
        self.grid.add_widget(tile)

    def _tile_touched(self, tile, touch):
        if not tile.collide_point(*touch.pos):
            return False
        file_id = tile.file_id
        if file_id in self.selected:
            self.selected.remove(file_id)
        else:
            self.selected.add(file_id)
        tile.selected = file_id in self.selected
        return True

    # ---------- actions ----------
    def _selected_records(self) -> list[dict]:
        return [record for record in self.records if record["id"] in self.selected]

    def _select_all(self, *_):
        self.selected = {record["id"] for record in self.records}
        for tile in self.grid.children:
            tile.selected = tile.file_id in self.selected

    def _open_selected(self, *_):
        records = self._selected_records()
        if not records:
            MessageDialog(t("empty_selection")).open()
            return
        if len(records) == 1 and records[0]["kind"] == "image":
            app = App.get_running_app()
            app.viewer_records = [r for r in self.records if r["kind"] == "image"]
            app.viewer_index = next(i for i, r in enumerate(app.viewer_records)
                                    if r["id"] == records[0]["id"])
            app.root.current = "image_viewer"
        elif len(records) == 1 and records[0]["kind"] == "video":
            App.get_running_app().play_video(records[0])
        else:
            details = "\n".join(
                f"{r['display_name']} | {human_size(r['size'])} | {t('imported_at')}: {r['imported_at']}"
                for r in records
            )
            MessageDialog(details).open()

    def _toggle_hidden(self, *_):
        records = self._selected_records()
        if not records:
            MessageDialog(t("empty_selection")).open()
            return
        app = App.get_running_app()
        for record in records:
            app.service.set_hidden(record["id"], self.mode != "hidden")
        self.load()

    def _delete_selected(self, *_):
        records = self._selected_records()
        if not records:
            MessageDialog(t("empty_selection")).open()
            return
        ConfirmDialog(t("delete_confirm"), on_confirm=self._do_delete, confirm_text=t("delete")).open()

    def _do_delete(self):
        app = App.get_running_app()
        for record in self._selected_records():
            app.service.delete(record["id"])
        self.load()

    def _rename_selected(self, *_):
        records = self._selected_records()
        if len(records) != 1:
            MessageDialog(t("empty_selection")).open()
            return
        record = records[0]
        InputDialog(t("rename"), record["display_name"],
                    lambda name: self._apply_rename(record, name)).open()

    def _apply_rename(self, record, name):
        if not name.strip():
            return
        App.get_running_app().service.rename(record["id"], name)
        self.load()

    def _export_selected(self, *_):
        records = self._selected_records()
        if not records:
            MessageDialog(t("empty_selection")).open()
            return
        self._pending_export = records
        from ...utils.platform import is_android

        if is_android():
            from ...core import android_api

            android_api.open_document_tree()
        else:
            InputDialog(t("save_as"), str(App.get_running_app().service.paths.root / "exported"),
                        self._export_desktop).open()

    def export_to_tree(self, tree_uri):
        records = getattr(self, "_pending_export", [])
        App.get_running_app().export_records(records, tree_uri)

    def _export_desktop(self, destination):
        from pathlib import Path

        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        records = getattr(self, "_pending_export", [])
        App.get_running_app().export_records(records, path)

    def _open_with(self, *_):
        records = self._selected_records()
        if len(records) != 1:
            MessageDialog(t("empty_selection")).open()
            return
        if not App.get_running_app().service.open_with(records[0]["id"]):
            MessageDialog("این قابلیت فقط در اندروید در دسترس است").open()
