"""Phase 7: the update check (zeroflow/updates.py). Opt-in: with "Check for updates"
off (the default) nothing is ever sent. On, it asks GitHub Releases once at start and
tells the user when a newer version is out; it never downloads or installs anything.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zeroflow import settings, updates


def release(tag="v2.0.1", url="https://github.com/o/r/releases/tag/v2.0.1", **extra):
    return {"tag_name": tag, "html_url": url, "draft": False, "prerelease": False, **extra}


def test_it_is_off_by_default():
    values, _ = settings.resolve({})
    assert values["CHECK_FOR_UPDATES"] is False


def test_off_means_no_request_at_all():
    asked = []
    assert updates.check(False, "2.0.0", fetch=lambda url: asked.append(url)) is None
    assert asked == []


def test_it_asks_github_releases_over_https():
    asked = []
    updates.check(True, "2.0.0", fetch=lambda url: asked.append(url) or release())
    assert len(asked) == 1
    assert asked[0].startswith("https://api.github.com/repos/") and asked[0].endswith(
        "/releases/latest")


def test_a_newer_release_is_reported_with_its_page():
    found = updates.check(True, "2.0.0", fetch=lambda url: release())
    assert found == updates.Update("2.0.1", "https://github.com/o/r/releases/tag/v2.0.1")


@pytest.mark.parametrize("tag", ["v2.0.0", "2.0.0", "v1.9.9", "v2.0.0-alpha.9"])
def test_the_same_or_an_older_release_is_not_reported(tag):
    assert updates.check(True, "2.0.0", fetch=lambda url: release(tag)) is None


@pytest.mark.parametrize("latest, current, newer", [
    ("2.0.0", "2.0.0-alpha.9", True),          # the release beats every alpha
    ("2.0.0-alpha.10", "2.0.0-alpha.9", True),  # numbers, not text: 10 > 9
    ("2.0.0-beta.1", "2.0.0-alpha.9", True),
    ("2.0.0-alpha.9", "2.0.0", False),
    ("2.1.0", "2.0.9", True),
    ("2.0.10", "2.0.9", True),
    ("10.0.0", "9.9.9", True),
])
def test_versions_compare_as_versions(latest, current, newer):
    assert updates.is_newer(latest, current) is newer


@pytest.mark.parametrize("answer", [
    release(draft=True), release(prerelease=True), {}, {"tag_name": "not a version"},
    "not json", None,
])
def test_a_draft_a_prerelease_or_a_strange_answer_reports_nothing(answer):
    assert updates.check(True, "2.0.0", fetch=lambda url: answer) is None


def test_no_network_reports_nothing_and_does_not_raise():
    def offline(url):
        raise OSError("no network")
    assert updates.check(True, "2.0.0", fetch=offline) is None


def test_a_link_that_is_not_github_is_not_shown():
    """The page link is opened in the browser, so only a GitHub page is accepted."""
    answer = release(url="https://evil.example.com/download")
    assert updates.check(True, "2.0.0", fetch=lambda url: answer) is None


def test_the_request_has_a_short_timeout_and_names_no_user():
    """Sent only when the user allowed it, with a generic client name and nothing else."""
    request = updates.build_request(updates.RELEASES_URL, "2.0.0")
    assert request.headers["User-agent"] == "ZeroFlow/2.0.0"
    assert updates.TIMEOUT <= 10


def test_a_plain_http_link_is_not_shown():
    answer = release(url="http://github.com/o/r/releases/tag/v2.0.1")
    assert updates.check(True, "2.0.0", fetch=lambda url: answer) is None


def test_the_real_fetch_uses_the_timeout_and_the_client_name(monkeypatch):
    import io
    import zeroflow
    used = {}

    def urlopen(request, timeout):
        used.update(agent=request.headers["User-agent"], timeout=timeout)
        return io.BytesIO(b'{"tag_name": "v2.0.1"}')
    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    assert updates.fetch_json(updates.RELEASES_URL) == {"tag_name": "v2.0.1"}
    assert used == {"agent": f"ZeroFlow/{zeroflow.__version__}", "timeout": updates.TIMEOUT}


# ---------------------------------------------------------------- the Engine's side
@pytest.mark.parametrize("language, text", [
    ("en", "Version 99.0.0 is out. Click to open its page."),
    ("ar", "صدر الإصدار 99.0.0. انقر لفتح صفحته."),
])
def test_a_newer_release_becomes_a_notification_with_its_page(monkeypatch, language, text):
    from zeroflow import app, i18n
    shown = []
    monkeypatch.setattr(app.ui, "show_toast", lambda *a, **k: shown.append((a, k)))
    i18n.choose(language)
    try:
        app.check_for_updates(True, fetch=lambda url: release("v99.0.0"))
    finally:
        i18n.choose("en")
    (title, body, _), extra = shown[0]
    assert body == text
    assert extra["link"] == "https://github.com/o/r/releases/tag/v2.0.1"


def test_the_engine_checks_once_after_it_has_booted_with_the_setting(monkeypatch):
    import threading
    from types import SimpleNamespace
    from zeroflow import app
    asked, done = [], threading.Event()
    monkeypatch.setattr(app, "check_for_updates", lambda on: asked.append(on) or done.set())
    monkeypatch.setattr(app.settings, "CHECK_FOR_UPDATES", "the setting's value")
    fake = SimpleNamespace(_refresh_tray=lambda: None,
                           halves=SimpleNamespace(state="paused",
                                                  state_changed=SimpleNamespace(
                                                      emit=lambda state: None)))
    app.EngineApp._booted(fake)
    assert done.wait(2) and asked == ["the setting's value"]


def test_a_click_on_the_notification_opens_the_link(monkeypatch):
    import threading
    import types
    from zeroflow import ui
    seen, done = {}, threading.Event()
    fake = types.ModuleType("win11toast")
    fake.toast = lambda *a, **k: seen.update(k) or done.set()
    monkeypatch.setitem(sys.modules, "win11toast", fake)
    ui.show_toast("t", "b", True, link="https://github.com/o/r/releases/tag/v2")
    assert done.wait(2) and seen["on_click"] == "https://github.com/o/r/releases/tag/v2"
