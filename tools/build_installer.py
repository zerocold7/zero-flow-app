r"""Build one edition's installer (Phase 7), with the edition's own venv:

    venv\Scripts\python tools\build_installer.py gpu
    venv-cpu\Scripts\python tools\build_installer.py cpu      [--offline]

PyInstaller and the licence audit read the packages of the Python that runs them, so the
wrong venv is refused. Each step stops the build when it fails:

  1. dist\<edition> and build\<edition> emptied (a failed PyInstaller run leaves the old
     build in place, and check_build would pass it)
  2. PyInstaller with packaging\zeroflow.spec, stopping on its exit code
  3. the licence audit, which writes THIRD-PARTY-NOTICES.txt: it stops on any GPL part
     but the two ADR 0003 accepted, and on anything proprietary or of unknown licence
  4. LICENSE (as LICENSE.txt) and the notices copied into the program folder
  5. tools\check_build.py (which needs the two files of step 4)
  6. Inno Setup's ISCC: dist\installer\ZeroFlow-<version>-<edition>-setup.exe

ISCC is looked for at F:\Tools\Inno Setup 6 unless ZEROFLOW_ISCC names another, and
before step 1, so a missing Inno Setup does not cost a 10-minute build first.
--offline: the audit skips the model licences on the Hugging Face Hub.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, ROOT)
sys.path.insert(0, TOOLS)

import zeroflow  # noqa: E402

ISS = os.path.join(ROOT, "packaging", "zeroflow.iss")
SPEC = os.path.join(ROOT, "packaging", "zeroflow.spec")
VENVS = {"gpu": "venv", "cpu": "venv-cpu"}
ISCC = os.environ.get("ZEROFLOW_ISCC") or r"F:\Tools\Inno Setup 6\ISCC.exe"
ACCEPTED_GPL = {"phonemizer-fork", "espeak-ng"}           # ADR 0003


class Stop(Exception):
    """The build stops here; the message says why."""


def unexpected_gpl(names) -> list[str]:
    return [name for name in names if name not in ACCEPTED_GPL]


def audit_problems(names: dict) -> list[str]:
    """What in the audit's {licence class: [names]} stops the build."""
    from licence_audit import PROPRIETARY, STRONG, UNKNOWN
    found = [f"GPL that ADR 0003 did not accept: {n}" for n in unexpected_gpl(names.get(STRONG, []))]
    return found + [f"{cls}: {n}" for cls in (PROPRIETARY, UNKNOWN) for n in names.get(cls, [])]


def folders(edition: str, root: str = ROOT) -> tuple[str, str, str]:
    """(dist\\<edition>, build\\<edition>, the program folder dist\\<edition>\\ZeroFlow)."""
    dist, work = os.path.join(root, "dist", edition), os.path.join(root, "build", edition)
    return dist, work, os.path.join(dist, "ZeroFlow")


def iscc_command(edition: str, iscc: str = ISCC, root: str = ROOT) -> list[str]:
    return [iscc, f"/DAppVersion={zeroflow.__version__}", f"/DEdition={edition}",
            f"/DSourceDir={folders(edition, root)[2]}",
            f"/O{os.path.join(root, 'dist', 'installer')}", ISS]


def right_venv(edition: str, prefix: str = sys.prefix, root: str = ROOT) -> bool:
    wanted = os.path.join(root, VENVS[edition])
    return os.path.normcase(os.path.abspath(prefix)) == os.path.normcase(wanted)


def build(edition: str, iscc: str = ISCC, offline: bool = False, root: str = ROOT,
          prefix: str = sys.prefix, run=subprocess.call, audit=None) -> str:
    """Every step in order; returns the installer's path. `run` and `audit` are the
    tests' way in (a command → exit code; a workpath → {licence class: [names]})."""
    if edition not in VENVS:
        raise Stop(f"edition must be gpu or cpu, not {edition!r}")
    if not right_venv(edition, prefix, root):
        raise Stop(f"the {edition} edition is built with {VENVS[edition]}\\Scripts\\python")
    if not os.path.isfile(iscc):
        raise Stop(f"Inno Setup's ISCC.exe is not at {iscc} (or set ZEROFLOW_ISCC)")
    dist, work, program = folders(edition, root)

    for folder in (dist, work):
        shutil.rmtree(folder, ignore_errors=True)
        if os.path.exists(folder):
            raise Stop(f"{folder} could not be emptied (a file in use?)")

    if run([sys.executable, "-m", "PyInstaller", SPEC, "--noconfirm",
            "--distpath", dist, "--workpath", work]) != 0:
        raise Stop("PyInstaller failed")

    if audit is None:
        import licence_audit
        notices = licence_audit.NOTICES
        names = licence_audit.audit(os.path.join(work, "zeroflow"), offline)
    else:
        notices = os.path.join(root, "THIRD-PARTY-NOTICES.txt")
        names = audit(os.path.join(work, "zeroflow"))
    if found := audit_problems(names):
        raise Stop("licence audit: " + "; ".join(found))

    shutil.copyfile(os.path.join(root, "LICENSE"), os.path.join(program, "LICENSE.txt"))
    shutil.copyfile(notices, os.path.join(program, "THIRD-PARTY-NOTICES.txt"))

    if run([sys.executable, os.path.join(TOOLS, "check_build.py"), edition, program]) != 0:
        raise Stop("check_build found problems (listed above)")
    if run(iscc_command(edition, iscc, root)) != 0:
        raise Stop("Inno Setup failed")
    return os.path.join(root, "dist", "installer",
                        f"ZeroFlow-{zeroflow.__version__}-{edition}-setup.exe")


def main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    try:
        made = build(args[0] if args else "", offline="--offline" in argv)
    except Stop as e:
        print(f"STOPPED: {e}")
        return 1
    print(f"Installer: {made} ({os.path.getsize(made) / 2**30:.2f} GB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
