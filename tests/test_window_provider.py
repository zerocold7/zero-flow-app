"""AI Provider page (zeroflow/provider_form.py), and where the API key goes
(zeroflow/key_saving.py). A Custom provider that is not on this PC says "your dictated
text is sent to this server"; the key goes to Credential Manager and nowhere else."""
import json
import logging

import pytest
from PySide6.QtWidgets import QLineEdit

from zeroflow import credentials, storage
from zeroflow.key_saving import KeyNotSaved, save_provider
from zeroflow.provider_form import ProviderPage, sent_to_server_notice

SECRET = "sk-test-0123456789-SECRET"


# ------------------------------------------------------------------ the warning
@pytest.mark.parametrize("url", ["https://api.example.com/v1/chat/completions",
                                 "https://api.anthropic.com",
                                 "http://192.168.1.5:8000/v1/chat/completions"])
def test_a_custom_provider_on_another_computer_warns(url):
    notice = sent_to_server_notice("custom", url)
    assert "sent to this server" in notice
    assert credentials.address_of(url).split("://")[1] in notice      # names the server


@pytest.mark.parametrize("url", ["http://127.0.0.1:1234/v1/chat/completions",
                                 "http://localhost:8080/v1", "http://[::1]:8080/v1"])
def test_a_custom_provider_on_this_pc_does_not(url):
    assert sent_to_server_notice("custom", url) is None


@pytest.mark.parametrize("provider", ["builtin", "ollama"])
def test_local_providers_never_warn(provider):
    assert sent_to_server_notice(provider, "http://127.0.0.1:11434/api/generate") is None
    # an address left over from an earlier Custom choice is not where their text goes
    assert sent_to_server_notice(provider, "https://api.example.com/v1") is None


def test_the_page_shows_and_hides_the_warning_as_the_address_changes(qtbot):
    page = ProviderPage()
    qtbot.addWidget(page)
    page.set_provider("custom")
    page.url_edit.setText("https://api.example.com/v1")
    assert page.warning_label.isVisibleTo(page)
    assert "sent to this server" in page.warning_label.text()
    page.url_edit.setText("http://localhost:1234/v1")
    assert not page.warning_label.isVisibleTo(page)
    page.set_provider("builtin")
    page.url_edit.setText("https://api.example.com/v1")
    assert not page.warning_label.isVisibleTo(page)         # only Custom sends it away


def test_the_claude_preset_fills_the_address_and_warns(qtbot):
    page = ProviderPage()
    qtbot.addWidget(page)
    page.choose_preset("claude")
    assert page.provider() == "custom"
    assert page.url_edit.text().startswith("https://api.anthropic.com")
    assert page.warning_label.isVisibleTo(page)


def test_the_key_box_hides_what_is_typed_and_never_shows_a_saved_key(qtbot):
    page = ProviderPage()
    qtbot.addWidget(page)
    assert page.key_edit.echoMode() == QLineEdit.Password
    page.show_saved_key(True)
    assert SECRET not in page.key_edit.text()
    assert page.key_edit.text() == ""                       # blank = keep the saved one
    assert page.key_edit.placeholderText()                  # says a key is saved


def test_a_key_for_a_remote_http_address_is_not_saved(qtbot):
    page = ProviderPage()
    qtbot.addWidget(page)
    page.set_provider("custom")
    page.url_edit.setText("http://example.com/v1")
    page.key_edit.setText(SECRET)
    assert page.problems()                                  # the window refuses plain http


# ------------------------------------------------------------------ the key
@pytest.fixture
def where(tmp_path):
    path = tmp_path / "settings.json"
    storage.save(str(path), {"AI_PROVIDER": "builtin", "AI_URL": "", "AI_MODEL": ""})
    return str(path), credentials.MemoryStore()


URL = "https://api.example.com/v1/chat/completions"


def test_the_key_goes_to_credential_manager_under_the_address(where):
    path, store = where
    save_provider(path, store, provider="custom", url=URL, model="m", key=SECRET)
    assert store.get("https://api.example.com") == SECRET


def test_the_key_is_in_no_part_of_the_settings_file(where):
    path, store = where
    save_provider(path, store, provider="custom", url=URL, model="m", key=SECRET)
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    assert SECRET not in raw
    assert "AI_API_KEY" not in json.loads(raw)
    assert json.loads(raw)["AI_PROVIDER"] == "custom"
    assert json.loads(raw)["AI_URL"] == URL


def test_a_blank_key_keeps_the_saved_one(where):
    path, store = where
    save_provider(path, store, provider="custom", url=URL, model="m", key=SECRET)
    save_provider(path, store, provider="custom", url=URL, model="m2", key="")
    assert store.get("https://api.example.com") == SECRET


def test_clearing_the_key_deletes_it(where):
    path, store = where
    save_provider(path, store, provider="custom", url=URL, model="m", key=SECRET)
    save_provider(path, store, provider="custom", url=URL, model="m", key=None, clear_key=True)
    assert store.get("https://api.example.com") is None


def test_a_new_address_gets_its_own_entry_and_leaves_the_old_one(where):
    path, store = where
    save_provider(path, store, provider="custom", url=URL, model="m", key=SECRET)
    save_provider(path, store, provider="custom", url="https://other.example.org/v1",
                  model="m", key="another")
    assert store.get("https://api.example.com") == SECRET
    assert store.get("https://other.example.org") == "another"


def test_the_key_is_never_logged(where, caplog):
    path, store = where
    with caplog.at_level(logging.DEBUG):
        save_provider(path, store, provider="custom", url=URL, model="m", key=SECRET)
    assert SECRET not in caplog.text


class BrokenStore(credentials.MemoryStore):
    def set(self, address, key):
        raise OSError(1312, "Credential Manager could not save a key (error 1312)")


def test_when_credential_manager_fails_nothing_is_written_and_the_key_is_not_in_the_error(where):
    path, _ = where
    with open(path, encoding="utf-8") as f:
        before = f.read()
    with pytest.raises(KeyNotSaved) as raised:
        save_provider(path, BrokenStore(), provider="custom", url=URL, model="m", key=SECRET)
    assert SECRET not in str(raised.value)
    with open(path, encoding="utf-8") as f:
        assert f.read() == before                   # no settings that point at a key not saved


def test_a_provider_that_takes_no_key_stores_none(where):
    path, store = where
    save_provider(path, store, provider="builtin", url="", model="", key=SECRET)
    assert store._keys == {}


# ------------------------------------------------------------------ the provider names
def test_the_old_provider_names_are_read_as_custom():
    from zeroflow import settings
    assert settings.normalise_provider("openai", URL) == ("custom", URL)
    assert settings.normalise_provider("Claude", "x") == ("custom", "https://api.anthropic.com")
    assert settings.normalise_provider("ollama", URL) == ("ollama", URL)
    assert settings.normalise_provider("builtin", URL) == ("builtin", URL)


def test_a_custom_provider_gets_the_clipboard_only_when_it_is_on_this_pc():
    from zeroflow import settings
    sent = settings.clipboard_context_sent
    assert sent("auto", "custom", "http://127.0.0.1:8080/v1", "") is True
    assert sent("auto", "custom", "https://api.anthropic.com", "") is False


def test_migrating_an_env_with_the_claude_provider_stores_custom_and_the_key_by_address(tmp_path):
    (tmp_path / ".env").write_text("AI_PROVIDER=claude\nAI_API_KEY=" + SECRET + "\n", encoding="utf-8")
    store = credentials.MemoryStore()
    target = tmp_path / "data" / "settings.json"
    storage.migrate(str(tmp_path), str(tmp_path / "data"), store, {}, str(target))
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["AI_PROVIDER"] == "custom" and saved["AI_URL"] == "https://api.anthropic.com"
    assert store.get("https://api.anthropic.com") == SECRET
    assert SECRET not in target.read_text(encoding="utf-8")
