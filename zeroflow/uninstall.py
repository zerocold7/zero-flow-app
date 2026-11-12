"""What the uninstaller removes. Inno Setup asks first, "No" being the default, then runs

    ZeroFlow.exe --remove-startup     No:  only the Start-with-Windows entry
    ZeroFlow.exe --remove-data        Yes: also %APPDATA%\\ZeroFlow, %LOCALAPPDATA%\\ZeroFlow
                                           and every "ZeroFlow:*" API key

The Run key goes either way: one pointing at a deleted program fails at every sign-in.
Only Zero- Flow's own two folders are deleted, never their parents. A models folder the
user chose outside them (MODELS_DIR = F:\\HuggingFace, shared with other programs) is
never touched, only reported as kept.

This runs before the supervisor and imports neither Qt nor zeroflow.settings (whose
import reads, and can migrate, the settings file).
"""
import os
import shutil
from dataclasses import dataclass, field

from zeroflow import credentials, paths, storage

FOLDER = "ZeroFlow"
FLAGS = ("--remove-startup", "--remove-data")


@dataclass
class Report:
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        return ([f"Removed: {p}" for p in self.removed] + [f"Kept: {p}" for p in self.kept]
                + [f"Could not remove: {p}" for p in self.failed])


def remove_startup(run_key) -> None:
    run_key.set(False)


def _folder(environ, variable: str) -> str | None:
    """%<variable>%\\ZeroFlow, or None when the variable is missing or not a full path:
    a relative one would point into whatever folder the uninstaller runs in."""
    base = environ.get(variable)
    if not base or not os.path.isabs(base):
        return None
    return os.path.join(base, FOLDER)


def _inside(path: str, folder: str) -> bool:
    path, folder = (os.path.normcase(os.path.abspath(p)) for p in (path, folder))
    return path == folder or path.startswith(folder + os.sep)


def models_dir(environ) -> str:
    """MODELS_DIR from the settings file; where the models go by default without one."""
    roaming = _folder(environ, "APPDATA")
    try:
        chosen = storage.load(os.path.join(roaming, paths.SETTINGS_NAME)).get("MODELS_DIR")
    except (OSError, ValueError, TypeError):
        chosen = None
    return chosen if isinstance(chosen, str) and chosen else storage.default_models_dir(environ)


def remove_data(environ, values: dict, store, run_key) -> Report:
    report = Report()
    try:
        remove_startup(run_key)
    except OSError:
        report.failed.append("Start with Windows")
    try:
        for address in store.addresses():
            try:
                store.delete(address)
            except OSError:
                report.failed.append(credentials.PREFIX + address)
    except OSError:
        report.failed.append("API keys in Credential Manager")

    folders = [f for f in (_folder(environ, "APPDATA"), _folder(environ, "LOCALAPPDATA")) if f]
    models = values.get("MODELS_DIR")
    if models and not any(_inside(models, f) for f in folders):
        report.kept.append(models)
    for folder in dict.fromkeys(folders):              # once, if both variables agree
        if not os.path.lexists(folder):
            continue
        try:
            shutil.rmtree(folder)
            report.removed.append(folder)
        except OSError:                                # a file in use, a link: say so
            report.failed.append(folder)
    return report


def run(argv: list[str], environ=None, store=None, run_key=None) -> int | None:
    """The exit code when `argv` asks for an uninstall step, otherwise None (the Engine
    starts). 1 when something could not be removed."""
    flag = argv[1] if len(argv) > 1 else None
    if flag not in FLAGS:
        return None
    if run_key is None:
        from zeroflow.startup import StartupKey
        run_key = StartupKey("")
    if flag == "--remove-startup":
        try:
            remove_startup(run_key)
        except OSError:
            return 1
        return 0
    environ = os.environ if environ is None else environ
    report = remove_data(environ, {"MODELS_DIR": models_dir(environ)},
                         store or credentials.WindowsStore(), run_key)
    for line in report.lines():
        print(line)
    return 1 if report.failed else 0
