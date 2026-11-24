"""Reusable Kivy widgets and dialogs for the vault UI."""
from __future__ import annotations

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView

Builder.load_string("""
<VaultButton>:
    background_normal: ''
    background_down: ''
    background_disabled_normal: ''
    background_color: 0, 0, 0, 0
    color: 1, 1, 1, 1
    bold: True
    font_size: '16sp'
    canvas.before:
        Color:
            rgba: (0.28, 0.29, 0.40, 1) if self.disabled else ((0.33,0.22,0.76,1) if self.state == 'down' else (0.45,0.32,0.92,1))
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

<SecondaryButton>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    color: 0.88, 0.90, 0.98, 1
    font_size: '15sp'
    canvas.before:
        Color:
            rgba: 0.30, 0.33, 0.48, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

<Card>:
    canvas.before:
        Color:
            rgba: 0.075, 0.086, 0.17, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]

<PersianLabel>:
    halign: 'right'
    valign: 'middle'
    color: 0.93, 0.94, 0.98, 1
    text_size: self.width - dp(8), None

<DialogBase>:
    size_hint: 0.88, None
    height: dp(260)
    auto_dismiss: False
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: 0.075, 0.086, 0.17, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(20)]
""")


class VaultButton(Button):
    pass


class SecondaryButton(Button):
    pass


class Card(BoxLayout):
    pass


class PersianLabel(Label):
    pass


class DialogBase(ModalView):
    message = StringProperty("")

    def __init__(self, message="", **kwargs):
        super().__init__(**kwargs)
        self.message = message
        layout = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        title = PersianLabel(text=message, font_size="17sp", size_hint_y=0.62)
        layout.add_widget(title)
        buttons = BoxLayout(size_hint_y=0.28, spacing=dp(10))
        buttons.add_widget(VaultButton(text="بستن", on_press=lambda *_: self.dismiss()))
        layout.add_widget(buttons)
        self.add_widget(layout)
        self.message_label = title
        self.buttons = buttons

    def set_message(self, text: str) -> None:
        self.message = text
        self.message_label.text = text


class InputDialog(DialogBase):
    """Modal text input used for display-name renaming."""

    def __init__(self, message="", initial="", on_confirm=None, **kwargs):
        super().__init__(message, **kwargs)
        from kivy.uix.textinput import TextInput

        self.height = dp(320)
        self.remove_widget(self.children[0])
        layout = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        layout.add_widget(PersianLabel(text=message, font_size="17sp", size_hint_y=0.22))
        self.input = TextInput(text=initial, multiline=False, font_size="16sp",
                               size_hint_y=0.28, background_color=(0.11, 0.12, 0.23, 1),
                               foreground_color=(0.93, 0.94, 0.98, 1))
        layout.add_widget(self.input)
        action_row = BoxLayout(size_hint_y=0.28, spacing=dp(10))
        action_row.add_widget(VaultButton(text="تأیید", on_press=self._confirmed))
        action_row.add_widget(SecondaryButton(text="لغو", on_press=lambda *_: self.dismiss()))
        layout.add_widget(action_row)
        self.add_widget(layout)
        self.on_confirm = on_confirm

    def _confirmed(self, *_):
        value = self.input.text
        self.dismiss()
        if self.on_confirm:
            self.on_confirm(value)


class ConfirmDialog(DialogBase):
    """Yes/No dialog used for irreversible operations."""

    def __init__(self, message="", on_confirm=None, confirm_text="تأیید", **kwargs):
        super().__init__(message, **kwargs)
        self.buttons.clear_widgets()
        self.buttons.add_widget(VaultButton(text=confirm_text, on_press=self._confirmed))
        self.buttons.add_widget(SecondaryButton(text="لغو", on_press=lambda *_: self.dismiss()))
        self.on_confirm = on_confirm

    def _confirmed(self, *_):
        self.dismiss()
        if self.on_confirm:
            self.on_confirm()


class MessageDialog(DialogBase):
    def __init__(self, message="", on_close=None, **kwargs):
        super().__init__(message, **kwargs)
        self.on_close = on_close

    def dismiss(self, *args, **kwargs):
        result = super().dismiss(*args, **kwargs)
        if self.on_close:
            self.on_close()
        return result


class SelectionTile(BoxLayout):
    """Gallery thumbnail tile with a multi-select indicator."""

    texture = ObjectProperty(None, allownone=True)
    label = StringProperty("")
    selected = BooleanProperty(False)
    badge = StringProperty("")
    file_id = ObjectProperty(None)
    colors = ListProperty([0.075, 0.086, 0.17, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from kivy.uix.image import Image
        from kivy.uix.checkbox import CheckBox

        self.orientation = "vertical"
        self.size_hint = (None, None)
        self.size = (dp(116), dp(132))
        self.padding = dp(4)
        self.spacing = dp(2)
        self._image = Image(texture=self.texture, size_hint_y=0.78, allow_stretch=True)
        self.add_widget(self._image)
        caption = PersianLabel(text=self.label, font_size="11sp", size_hint_y=0.16)
        caption.bind(text_size=lambda *_: None)
        self.add_widget(caption)
        self._check = CheckBox(active=self.selected, size_hint_y=0.1)
        self._check.disabled = True
        self.add_widget(self._check)
        self.bind(texture=self._update_texture, selected=self._update_selected)

    def _update_texture(self, instance, value):
        self._image.texture = value

    def _update_selected(self, instance, value):
        self._check.active = value
        self.colors = (0.35, 0.25, 0.75, 1) if value else (0.075, 0.086, 0.17, 1)
        self.canvas.before.clear()
        with self.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*self.colors)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])

    def on_pos(self, *args):
        self._update_selected(self, self.selected)

    def on_size(self, *args):
        self._update_selected(self, self.selected)
