"""Home dashboard with statistics and navigation."""
from __future__ import annotations

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import Screen

from ..widgets import Card, PersianLabel, SecondaryButton, VaultButton
from ...utils.strings import t


def human_size(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="home", **kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))

        header = PersianLabel(text=t("app_title"), font_size="26sp", size_hint_y=0.09)
        root.add_widget(header)

        stats = GridLayout(cols=3, spacing=dp(10), size_hint_y=0.18)
        self.image_count = PersianLabel(font_size="18sp")
        self.video_count = PersianLabel(font_size="18sp")
        self.used_space = PersianLabel(font_size="18sp")
        for widget in (self.image_count, self.video_count, self.used_space):
            card = Card(padding=dp(10))
            card.add_widget(widget)
            stats.add_widget(card)
        root.add_widget(stats)

        labels = GridLayout(cols=3, spacing=dp(10), size_hint_y=0.06)
        for text in (t("images"), t("videos"), t("used_space")):
            labels.add_widget(PersianLabel(text=text, font_size="13sp", halign="center"))
        root.add_widget(labels)

        root.add_widget(VaultButton(text=t("add_file"), size_hint_y=0.11,
                                    on_press=lambda *_: App.get_running_app().pick_files()))
        root.add_widget(VaultButton(text=t("gallery"), size_hint_y=0.10,
                                    on_press=lambda *_: self._go("gallery")))
        root.add_widget(SecondaryButton(text=t("hidden"), size_hint_y=0.09,
                                        on_press=lambda *_: self._go("hidden")))
        root.add_widget(SecondaryButton(text=t("settings"), size_hint_y=0.09,
                                        on_press=lambda *_: self._go("settings")))
        root.add_widget(BoxLayout(size_hint_y=0.22))
        self.add_widget(root)

    def on_enter(self):
        App.get_running_app().service.touch()
        self.refresh()

    def refresh(self):
        stats = App.get_running_app().service.stats()
        self.image_count.text = str(stats["images"])
        self.video_count.text = str(stats["videos"])
        self.used_space.text = human_size(stats["bytes"])

    def _go(self, name: str) -> None:
        screen = App.get_running_app().root.get_screen(name)
        if hasattr(screen, "load"):
            screen.load()
        App.get_running_app().root.current = name
