"""The AI Provider page of the Settings window: Built-in (the default, local), Ollama, or
Custom (any address, model and key; Claude is a preset). A Custom provider that is not on
this PC says plainly that dictated text is sent to that server."""
from urllib.parse import urlparse

from PySide6.QtWidgets import (QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton,
                               QWidget)

from zeroflow import credentials, settings

PROVIDERS = {"builtin": "Built-in (on this PC)", "ollama": "Ollama (on this PC)",
             "custom": "Custom"}
PRESETS = {"claude": ("https://api.anthropic.com", "Claude (Anthropic)")}


def sent_to_server_notice(provider: str, url: str) -> str | None:
    """The notice for a Custom provider on another computer; None when nothing leaves this PC."""
    if provider != "custom":
        return None
    host = urlparse(url.strip()).hostname
    if not host or settings.this_pc(host):
        return None
    server = credentials.address_of(url).split("://", 1)[1]
    return f"Your dictated text is sent to this server: {server}"


class ProviderPage(QWidget):
    def __init__(self):
        super().__init__()
        self.provider_box = QComboBox()
        for name, label in PROVIDERS.items():
            self.provider_box.addItem(label, name)
        self.ollama_model_box = QComboBox()
        self.ollama_model_box.setEditable(True)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://api.example.com/v1/chat/completions")
        self.model_edit = QLineEdit()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.clear_key_button = QPushButton("Remove saved key")
        self.clear_key_requested = False
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #b54708; font-weight: 600;")
        self.warning_label.setVisible(False)
        self.preset_buttons = {name: QPushButton(f"Use {label}")
                               for name, (_, label) in PRESETS.items()}

        form = QFormLayout(self)
        form.addRow("AI Provider", self.provider_box)
        form.addRow("Ollama model", self.ollama_model_box)
        self.rows = {"ollama": [self.ollama_model_box],
                     "custom": [self.url_edit, self.model_edit, self.key_edit,
                                self.clear_key_button, *self.preset_buttons.values()]}
        form.addRow("Address", self.url_edit)
        form.addRow("Model", self.model_edit)
        form.addRow("API key", self.key_edit)
        form.addRow("", self.clear_key_button)
        for button in self.preset_buttons.values():
            form.addRow("", button)
        form.addRow("", self.warning_label)
        self._form = form

        self.provider_box.currentIndexChanged.connect(self._refresh)
        self.url_edit.textChanged.connect(self._refresh)
        self.clear_key_button.clicked.connect(self._clear_key)
        for name, button in self.preset_buttons.items():
            button.clicked.connect(lambda _=False, n=name: self.choose_preset(n))
        self._refresh()

    # --------------------------------------------------------------- reading and setting
    def provider(self) -> str:
        return self.provider_box.currentData()

    def set_provider(self, name: str) -> None:
        self.provider_box.setCurrentIndex(self.provider_box.findData(name))
        self._refresh()

    def choose_preset(self, name: str) -> None:
        url, _ = PRESETS[name]
        self.set_provider("custom")
        self.url_edit.setText(url)

    def show_saved_key(self, saved: bool) -> None:
        """A saved key is never shown, and never put in the box: blank keeps it."""
        self.key_edit.clear()
        self.key_edit.setPlaceholderText("A key is saved. Leave blank to keep it." if saved
                                         else "Paste the key here")
        self.clear_key_button.setEnabled(saved)
        self.clear_key_requested = False

    def _clear_key(self) -> None:
        self.clear_key_requested = True
        self.key_edit.clear()
        self.key_edit.setPlaceholderText("The saved key will be removed when you save.")

    def problems(self) -> list[str]:
        found = []
        if self.provider() == "custom":
            if not self.url_edit.text().strip():
                found.append("Enter the address of the AI service.")
            elif settings.key_sent_in_the_clear(self.url_edit.text().strip(), self.key_edit.text()):
                found.append("This address is plain http, so the API key would be sent "
                             "unencrypted. Use an https:// address.")
        return found

    # ------------------------------------------------------------------------- showing
    def _refresh(self) -> None:
        provider = self.provider()
        for row_provider, widgets in self.rows.items():
            for widget in widgets:
                widget.setVisible(provider == row_provider)
                label = self._form.labelForField(widget)
                if label is not None:
                    label.setVisible(provider == row_provider)
        notice = sent_to_server_notice(provider, self.url_edit.text())
        self.warning_label.setText(notice or "")
        self.warning_label.setVisible(notice is not None)
