"""The update check, opt-in: "Check for updates" (CHECK_FOR_UPDATES) is off by default.

On, the Engine asks GitHub Releases once at start for the latest release, and the user
gets a notification with the release page when it is newer than this copy. Nothing is
downloaded or installed, and only a github.com page is ever offered. Off, nothing is sent.
The request carries a generic client name (ZeroFlow/<version>) and nothing about the user.
"""
import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from zeroflow import __version__

# Phase 8 creates the public repository; until then this name answers 404 (no update).
REPOSITORY = "zerocold7/zero-flow-app"
RELEASES_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
TIMEOUT = 5                                          # seconds; at start, on a worker thread
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?")
_STAGES = {"alpha": 0, "beta": 1, "rc": 2}
_RELEASE = (3, 0)                                    # a release beats every alpha/beta/rc


@dataclass(frozen=True)
class Update:
    version: str
    page: str                                        # the release page on github.com


def _order(version: str) -> tuple | None:
    """A version as numbers to compare (2.0.0-alpha.10 after alpha.9); None if it is none."""
    found = _VERSION.fullmatch(version.strip())
    if not found:
        return None
    major, minor, patch, stage, n = found.groups()
    pre = (_STAGES[stage], int(n)) if stage else _RELEASE
    return int(major), int(minor), int(patch), *pre


def is_newer(latest: str, current: str) -> bool:
    a, b = _order(latest), _order(current)
    return a is not None and b is not None and a > b


def build_request(url: str, version: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": f"ZeroFlow/{version}",
                                                "Accept": "application/vnd.github+json"})


def fetch_json(url: str):
    with urllib.request.urlopen(build_request(url, __version__), timeout=TIMEOUT) as answer:
        return json.load(answer)


def _on_github(page: str) -> bool:
    address = urlparse(page)
    return address.scheme == "https" and address.hostname == "github.com"


def check(enabled: bool, current: str, fetch=fetch_json) -> Update | None:
    """The newer release, or None: off, offline, nothing newer, or a strange answer."""
    if not enabled:
        return None
    try:
        answer = fetch(RELEASES_URL)
    except (OSError, ValueError) as e:              # offline, timeout, HTTP error, bad JSON
        logging.info(f"Update check: no answer ({e}).")
        return None
    if not isinstance(answer, dict) or answer.get("draft") or answer.get("prerelease"):
        return None
    tag, page = answer.get("tag_name"), answer.get("html_url")
    if not (isinstance(tag, str) and isinstance(page, str) and _on_github(page)):
        return None
    version = tag.removeprefix("v")
    if not is_newer(version, current):
        return None
    return Update(version, page)
