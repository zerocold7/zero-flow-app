"""What the engine installs is exactly what it uses.

requirements.txt listed soundfile, which only the bench tools use, and anthropic,
which only AI_PROVIDER="claude" uses — so every install carried them and what they
pull in. These tests keep the lists honest in both directions: every package the
engine imports is installed by requirements.txt, every line there is used, and
constraints.txt pins exactly what a fresh install pulls in (plus the optional Claude
package's own set), so no install takes "whatever is newest that day".

Reads the installed packages' own metadata, so it runs in the engine's venv.
"""
import ast
import functools
import os
import re
import sys
import unittest
from importlib.metadata import PackageNotFoundError, packages_distributions, requires
from importlib.metadata import distribution

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = ["zeroflow", "reader", "zero_flow.py", "local_flow.py", "check_hardware.py",
          os.path.join("tools", "get_llama.py")]
OWN = {"zeroflow", "reader", "check_hardware", "presets"}
# Installed for the engine but never imported by name — each with why.
NOT_IMPORTED = {
    "nvidia-cublas-cu12": "CUDA libraries Whisper loads as DLLs on the graphics card",
    "nvidia-cudnn-cu12": "CUDA libraries Whisper loads as DLLs on the graphics card",
    "en-core-web-sm": "the English model kokoro's pronunciation loads by name",
}
# Imported only when its optional feature is chosen; installed by hand for it.
OPTIONAL = {"anthropic": "AI_PROVIDER=claude (llm/claude.py)"}


def engine_files():
    for entry in ENGINE:
        path = os.path.join(ROOT, entry)
        if os.path.isfile(path):
            yield path
        for folder, _, names in os.walk(path):
            yield from (os.path.join(folder, n) for n in names if n.endswith(".py"))


def third_party_imports() -> set[str]:
    found = set()
    for path in engine_files():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            else:
                continue
            found |= {n.split(".")[0] for n in names}
    return {n for n in found if n not in sys.stdlib_module_names and n not in OWN}


def requirement_lines(name="requirements.txt") -> list[Requirement]:
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        lines = [line.split("#")[0].strip() for line in f]
    return [Requirement(line) for line in lines if re.match(r"^[A-Za-z]", line)]


def pulled_in(requirements) -> set[str]:
    """Every installed distribution these requirements bring, extras followed."""
    seen, todo = set(), list(requirements)
    walked = set()
    while todo:
        req = todo.pop()
        key = (canonicalize_name(req.name), tuple(sorted(req.extras)))
        if key in walked:
            continue
        walked.add(key)
        try:
            dependencies = requires(req.name) or []
        except PackageNotFoundError:
            continue                              # a marker excluded it on this PC
        seen.add(key[0])
        envs = [{"extra": e} for e in (req.extras or {""})]
        for line in dependencies:
            dep = Requirement(line)
            if dep.marker is None or any(dep.marker.evaluate(env) for env in envs):
                todo.append(dep)
    return seen


def pinned() -> set[str]:
    with open(os.path.join(ROOT, "constraints.txt"), encoding="utf-8") as f:
        return {canonicalize_name(line.split("==")[0]) for line in f
                if "==" in line and not line.startswith("#")}


@functools.cache
def _distributions() -> dict:
    return packages_distributions()              # reads every installed package: once


def provider_of(module: str) -> set[str]:
    return {canonicalize_name(d) for d in _distributions().get(module, [])}


class TestRequirements(unittest.TestCase):
    def test_every_import_is_installed_by_requirements(self):
        installed = pulled_in(requirement_lines())
        for module in third_party_imports():
            providers = provider_of(module)
            self.assertTrue(providers, f"{module}: no installed package provides it")
            if providers & set(OPTIONAL):
                continue
            self.assertTrue(providers & installed,
                            f"the engine imports {module} ({providers}), "
                            f"but requirements.txt does not install it")

    def test_every_requirement_is_used(self):
        imported = set().union(*(provider_of(m) for m in third_party_imports()))
        for req in requirement_lines():
            name = canonicalize_name(req.name)
            self.assertTrue(name in imported or name in NOT_IMPORTED,
                            f"requirements.txt installs {req.name}, which the engine "
                            f"never imports")

    def test_optional_packages_are_not_in_the_main_install(self):
        names = {canonicalize_name(r.name) for r in requirement_lines()}
        self.assertFalse(names & set(OPTIONAL), "an optional package is installed for all")

    def test_constraints_pin_exactly_what_an_install_pulls_in(self):
        main = pulled_in(requirement_lines())
        optional = pulled_in(Requirement(name) for name in OPTIONAL)
        url_pinned = {canonicalize_name(r.name) for r in requirement_lines() if r.url}
        self.assertEqual(main - pinned() - url_pinned, set(), "pulled in but not pinned")
        self.assertEqual(pinned() - main - optional, set(), "pinned but never installed")

    def test_the_optional_package_is_pinned_for_its_own_install(self):
        for name in OPTIONAL:
            distribution(name)                    # installed here, for the tests
            self.assertIn(canonicalize_name(name), pinned())


if __name__ == "__main__":
    unittest.main()
