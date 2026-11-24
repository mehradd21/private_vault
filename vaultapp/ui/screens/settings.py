"""Settings: password change, auto-lock and security information."""
from __future__ import annotations

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from ..widgets import Card, MessageDialog, PersianLabel, SecondaryButton, VaultButton
from ...utils.strings import t
from ...utils.platform import is_android


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="settings", **kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))
        root.add_widget(PersianLabel(text=t("settings"), font_size="26sp", size_hint_y=0.08))

        card = Card(orientation="vertical", padding=dp(16), spacing=dp(8), size_hint_y=0.42)
        card.add_widget(PersianLabel(text=t("change_password"), font_size="18sp"))
        self.old = self._password_input(t("current_password"))
        self.new = self._password_input(t("new_password"))
        self.confirm = self._password_input(t("confirm_password"))
        for widget in (self.old, self.new, self.confirm):
            card.add_widget(widget)
        card.add_widget(VaultButton(text=t("change_password"), size_hint_y=0.22,
                                    on_press=self._change_password))
        root.add_widget(card)

        lock_card = Card(orientation="vertical", padding=dp(16), spacing=dp(8), size_hint_y=0.16)
        lock_card.add_widget(PersianLabel(text=t("auto_lock"), font_size="16sp"))
        self.auto_lock = Spinner(
            text="60", values=("0", "15", "30", "60", "300"),
            background_color=(0.16, 0.17, 0.30, 1), size_hint_y=0.55,
        )
        self.auto_lock.bind(text=self._set_auto_lock)
        lock_card.add_widget(self.auto_lock)
        root.add_widget(lock_card)

        info = (
            "AES-256-GCM | Argon2id | Android Keystore\n"
            + ("FLAG_SECURE: active" if is_android() else "حالت تست دسکتاپ")
        )
        root.add_widget(PersianLabel(text=info, font_size="13sp", size_hint_y=0.10))

        root.add_widget(SecondaryButton(text=t("lock_now"), size_hint_y=0.08,
                                        on_press=lambda *_: App.get_running_app().lock_app()))
        root.add_widget(SecondaryButton(text=t("exit"), size_hint_y=0.08,
                                        on_press=lambda *_: self._exit()))
        self.add_widget(root)

    @staticmethod
    def _password_input(hint):
        return TextInput(
            password=True, multiline=False, font_size="15sp", hint_text=hint,
            size_hint_y=0.19, background_color=(0.11, 0.12, 0.23, 1),
            foreground_color=(0.93, 0.94, 0.98, 1),
        )

    def on_enter(self):
        app = App.get_running_app()
        self.auto_lock.text = str(app.service.db.get_int("auto_lock_seconds", 60))

    def _set_auto_lock(self, spinner, value):
        try:
            App.get_running_app().service.auth.set_auto_lock_seconds(int(value))
        except ValueError:
            pass

    def _change_password(self, *_):
        app = App.get_running_app()
        try:
            app.service.change_password(self.old.text, self.new.text, self.confirm.text)
        except Exception as exc:
            MessageDialog(str(exc)).open()
            return
        self.old.text = self.new.text = self.confirm.text = ""
        MessageDialog("رمز عبور با موفقیت تغییر یافت").open()

    def _exit(self):
        App.get_running_app().lock_app()
        App.get_running_app().stop()
