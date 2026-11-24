"""First-run setup and unlock screens."""
from __future__ import annotations

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput

from ..widgets import Card, MessageDialog, PersianLabel, VaultButton
from ...utils.strings import t


class _AuthScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = (0.035, 0.043, 0.094, 1)

    @property
    def app(self):
        return App.get_running_app()

    @staticmethod
    def password_input(hint: str) -> TextInput:
        return TextInput(
            password=True, multiline=False, font_size="17sp", hint_text=hint,
            size_hint_y=None, height=dp(48), background_color=(0.11, 0.12, 0.23, 1),
            foreground_color=(0.93, 0.94, 0.98, 1), hint_text_color=(0.55, 0.58, 0.72, 1),
            padding=[dp(12), dp(12), dp(12), dp(12)],
        )

    def error(self, message: str) -> None:
        MessageDialog(message).open()


class SetupScreen(_AuthScreen):
    def __init__(self, **kwargs):
        super().__init__(name="setup", **kwargs)
        layout = BoxLayout(orientation="vertical", padding=dp(28), spacing=dp(16))
        layout.add_widget(PersianLabel(text=t("setup_title"), font_size="28sp", size_hint_y=0.12))
        layout.add_widget(PersianLabel(text=t("setup_hint"), font_size="15sp", size_hint_y=0.10))

        card = Card(orientation="vertical", padding=dp(18), spacing=dp(12), size_hint_y=0.42)
        self.password = self.password_input(t("password"))
        self.confirm = self.password_input(t("confirm_password"))
        card.add_widget(self.password)
        card.add_widget(self.confirm)
        layout.add_widget(card)

        button = VaultButton(text=t("create"), size_hint_y=0.10, on_press=self._create)
        layout.add_widget(button)
        self.add_widget(layout)

    def on_enter(self):
        self.password.text = ""
        self.confirm.text = ""

    def _create(self, *_):
        try:
            self.app.service.setup(self.password.text, self.confirm.text)
        except (ValueError, RuntimeError) as exc:
            self.error(str(exc))
            return
        self.password.text = ""
        self.confirm.text = ""
        self.app.show_home()


class UnlockScreen(_AuthScreen):
    def __init__(self, **kwargs):
        super().__init__(name="unlock", **kwargs)
        layout = BoxLayout(orientation="vertical", padding=dp(28), spacing=dp(16))
        layout.add_widget(PersianLabel(text=t("unlock_title"), font_size="28sp", size_hint_y=0.14))
        layout.add_widget(PersianLabel(text=t("unlock_hint"), font_size="15sp", size_hint_y=0.08))

        card = Card(orientation="vertical", padding=dp(18), spacing=dp(12), size_hint_y=0.40)
        self.password = self.password_input(t("password"))
        card.add_widget(self.password)
        self.attempts = PersianLabel(text="", font_size="14sp", size_hint_y=0.25)
        card.add_widget(self.attempts)
        layout.add_widget(card)

        layout.add_widget(VaultButton(text=t("unlock"), size_hint_y=0.10, on_press=self._unlock))
        self.add_widget(layout)

    def on_enter(self):
        self.password.text = ""
        self.refresh_attempts()

    def refresh_attempts(self):
        from ...core.auth import MAX_ATTEMPTS

        failed = self.app.service.db.get_int("failed_attempts", 0)
        if failed:
            self.attempts.text = t("attempts_left", n=max(0, MAX_ATTEMPTS - failed))
        else:
            self.attempts.text = ""

    def _unlock(self, *_):
        from ...core.auth import AuthenticationError, LockedOutError

        try:
            self.app.service.unlock(self.password.text)
        except LockedOutError as exc:
            self.error(t("locked_for", n=exc.seconds))
        except (AuthenticationError, RuntimeError) as exc:
            self.error(t("wrong_password") if "invalid password" in str(exc) else str(exc))
            self.password.text = ""
            self.refresh_attempts()
            return
        self.password.text = ""
        self.app.show_home()
