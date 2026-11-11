"""The settings file, and the one-time move of the old files into %APPDATA%\\ZeroFlow.

ADR 0002: one settings file is the only source. The migration runs only when there is
no settings file. It reads .env with the same checks the engine uses, copies
flow_vocabulary.txt and flow_history.md, and never changes any of the three. AI_API_KEY
goes to Windows Credential Manager under the provider's address, never into the file.

The settings file is written last, in one step (a temporary file, then a rename): if
anything before it fails, there is still no settings file and the next start tries again.

Only the standard library is imported here at load time, so check_hardware.py can use
it from any Python.
"""
import json
import os
import re
import shutil
from dataclasses import dataclass, field

from zeroflow import credentials, paths

SETTINGS_NAME = paths.SETTINGS_NAME
# Old name in the program folder → new name in the data folder.
DATA_NAMES = {"flow_vocabulary.txt": paths.VOCABULARY_NAME, "flow_history.md": paths.HISTORY_NAME}
KEY_NAME = "AI_API_KEY"
MODELS_NAME = "MODELS_DIR"
_KEY_LINE = re.compile(rb"^(?:\xef\xbb\xbf)?\s*(?:export\s+)?AI_API_KEY\s*=")


@dataclass
class Migration:
    ran: bool = False                   # False: a settings file was there already
    problems: list = field(default_factory=list)
    key_moved: bool = False             # AI_API_KEY is now in Credential Manager
    key_left_in_env: bool = False       # ...and the old .env still holds it


def default_models_dir(environ) -> str:
    """Where the models go: HF_HOME when this PC already keeps them there, otherwise
    %LOCALAPPDATA%\\ZeroFlow\\models."""
    return environ.get("HF_HOME") or os.path.join(
        environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ZeroFlow", "models")


def apply_models_dir(values: dict, environ) -> None:
    """Point Hugging Face at the models folder. Must run before huggingface_hub is
    imported: it reads HF_HOME once, at import."""
    if values.get(MODELS_NAME):
        environ["HF_HOME"] = values[MODELS_NAME]


# ---------------------------------------------------------------- the old .env
def read_env(env_path: str) -> dict[str, str]:
    """NAME → text, as written in .env; {} when there is none."""
    if not os.path.exists(env_path):
        return {}
    from dotenv import dotenv_values
    return {name: value for name, value in dotenv_values(env_path).items() if value is not None}


def env_names(env_path: str) -> list[str]:
    return list(read_env(env_path))


def read_from_env(env_path: str, name: str):
    """The value the engine takes for `name` from this .env: same checks, same default."""
    from zeroflow import settings
    return settings.resolve(read_env(env_path))[0][name]


def remove_key_line(env_path: str) -> bool:
    """**Remove it**: delete the AI_API_KEY line from the old .env, and nothing else.
    Every other byte stays as it was, line endings included. False if there was none."""
    with open(env_path, "rb") as f:
        lines = f.read().splitlines(keepends=True)
    kept = [line for line in lines if not _KEY_LINE.match(line)]
    if len(kept) == len(lines):
        return False
    _write_bytes(env_path, b"".join(kept))
    return True


# ---------------------------------------------------------------- the settings file
def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        values = json.load(f)
    if not isinstance(values, dict):
        raise ValueError("it does not hold a list of settings")
    return values


def save(path: str, values: dict) -> None:
    """Write the settings file in one step. An API key never goes in it."""
    if KEY_NAME in values:
        raise ValueError(f"{KEY_NAME} belongs in Credential Manager, not in {SETTINGS_NAME}")
    text = json.dumps(values, indent=2, ensure_ascii=False) + "\n"
    _write_bytes(path, text.encode("utf-8"))


def update(path: str, changes: dict) -> None:
    """Change some settings in an existing settings file and keep the rest."""
    values = load(path)
    values.update(changes)
    save(path, values)


def _write_bytes(path: str, data: bytes) -> None:
    temporary = path + ".tmp"
    with open(temporary, "wb") as f:
        f.write(data)
    os.replace(temporary, path)


def _copy(source: str, target: str) -> None:
    temporary = target + ".tmp"
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


# ---------------------------------------------------------------- the migration
def migrate(old_dir: str, data_dir: str, keys, environ, settings_path: str | None = None) -> Migration:
    """Fill a new settings file from the old files in `old_dir`. Does nothing at all when
    the settings file exists. `keys` is where the API key goes (credentials.WindowsStore)."""
    target = settings_path or os.path.join(data_dir, SETTINGS_NAME)
    result = Migration()
    if os.path.exists(target):
        return result
    os.makedirs(data_dir, exist_ok=True)

    from zeroflow import settings
    raw = read_env(os.path.join(old_dir, ".env"))
    values, result.problems = settings.resolve(raw)
    if MODELS_NAME not in raw:
        values[MODELS_NAME] = default_models_dir(environ)
    key = values.pop(KEY_NAME, "")

    for old, new in DATA_NAMES.items():
        source = os.path.join(old_dir, old)
        if os.path.exists(source):
            _copy(source, os.path.join(data_dir, new))

    if key:
        result.key_left_in_env = True
        address = credentials.provider_address(values["AI_PROVIDER"].lower(), values["AI_URL"])
        if address is None:
            result.problems.append(f'{KEY_NAME} in .env was not moved: AI_PROVIDER="'
                                   f'{values["AI_PROVIDER"]}" takes no key.')
        else:
            keys.set(address, key)
            result.key_moved = True

    save(target, values)                # last: see the module's docstring
    result.ran = True
    return result
