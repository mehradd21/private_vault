"""In-app video playback with native codecs via ffpyplayer."""
from __future__ import annotations

import os

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen
from kivy.uix.slider import Slider
from kivy.uix.video import Video

from ..widgets import MessageDialog, PersianLabel, SecondaryButton
from ...utils.strings import t


class VideoPlayerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="video_player", **kwargs)
        self.record = None
        self.temp_path = None
        root = BoxLayout(orientation="vertical")
        self.video = Video(state="stop", options={"eos": "pause"})
        root.add_widget(self.video)

        self.seek = Slider(min=0, max=1, value=0)
        self.seek.bind(value=self._on_seek)
        root.add_widget(self.seek)

        controls = BoxLayout(size_hint_y=0.12, spacing=dp(6), padding=dp(6))
        self.play_button = Button(text=t("pause"), on_press=self._toggle_play)
        controls.add_widget(self.play_button)
        controls.add_widget(SecondaryButton(text="10s ←", on_press=lambda *_: self._jump(-10)))
        controls.add_widget(SecondaryButton(text="10s →", on_press=lambda *_: self._jump(10)))
        controls.add_widget(SecondaryButton(text=t("video_fullscreen"), on_press=self._fullscreen))
        root.add_widget(controls)

        volume_row = BoxLayout(size_hint_y=0.08, padding=dp(8))
        volume_row.add_widget(PersianLabel(text="صدا", font_size="13sp", size_hint_x=0.2))
        volume = Slider(min=0, max=1, value=1)
        volume.bind(value=self._on_volume)
        volume_row.add_widget(volume)
        root.add_widget(volume_row)

        root.add_widget(SecondaryButton(text="بازگشت", size_hint_y=0.08,
                                        on_press=lambda *_: self._back()))
        self.add_widget(root)

    def on_enter(self):
        app = App.get_running_app()
        self.record = getattr(app, "playing_record", None)
        if not self.record:
            self._back()
            return
        try:
            self.temp_path = app.service.decrypt_to_temp(self.record["id"])
            self.video.source = str(self.temp_path)
            self.video.state = "play"
            self.seek.max = max(1, self.video.duration or 1)
        except Exception as exc:
            MessageDialog(str(exc)).open()
            self._back()

    def on_leave(self):
        self.video.state = "stop"
        self.video.source = ""
        if self.temp_path and os.path.exists(self.temp_path):
            App.get_running_app().service.repo.temp_files.defer(self.temp_path)
        self.temp_path = None

    def _toggle_play(self, *_):
        self.video.state = "pause" if self.video.state == "play" else "play"
        self.play_button.text = t("play") if self.video.state == "pause" else t("pause")

    def _jump(self, seconds: int):
        self.video.position = max(0, min(self.video.duration, self.video.position + seconds))

    def _on_seek(self, instance, value):
        if self.video.state == "play" and value < self.video.duration:
            self.video.position = value

    def _on_volume(self, instance, value):
        self.video.volume = value

    def _fullscreen(self, *_):
        from kivy.core.window import Window

        Window.fullscreen = not Window.fullscreen

    def _back(self, *_):
        App.get_running_app().root.current = "gallery"
