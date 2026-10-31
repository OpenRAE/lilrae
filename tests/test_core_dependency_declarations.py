"""Guard: a plain install provides every module that shipped code imports at load.

``aptl.core.host_keys`` imports ``asyncssh`` at module level, and every
``lilrae`` command loads it, but ``asyncssh`` was declared only in the ``web``
extra. raes 7.0.0 happened to require it, so a plain ``pip install lilrae``
worked; raes 8 does not, and ``lilrae lab init`` failed with
``ModuleNotFoundError: No module named 'asyncssh'``.

A transitive or extra-only dependency is not a declaration. These tests
resolve each unconditional module-level import in the shipped packages to the
installed distribution that provides it, and require that distribution in
``[project].dependencies``. The web API and the workbench need the ``web``
extra, so they are out of scope.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from functools import cache
from importlib.metadata import distribution, packages_distributions
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"


@cache
def _pyproject() -> dict:
    """Return the parsed ``pyproject.toml``."""
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _shipped_packages() -> list[Path]:
    """Return the source packages the wheel ships."""
    packages = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    return [REPO_ROOT / package for package in packages]


def _core_dependencies() -> frozenset[str]:
    """Return the canonical names of the distributions every install receives."""
    return frozenset(
        canonicalize_name(Requirement(spec).name)
        for spec in _pyproject()["project"]["dependencies"]
    )


def _core_python_files() -> list[Path]:
    """Return the shipped sources that do not need the ``web`` extra."""
    web_only = (SRC / "aptl" / "api", SRC / "aptl" / "workbench")
    return [
        path
        for package in _shipped_packages()
        for path in sorted(package.rglob("*.py"))
        if not any(path.is_relative_to(web) for web in web_only)
    ]


def _module_level_imports(path: Path) -> set[str]:
    """Return the absolute modules a file imports unconditionally at load."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def _is_third_party(module: str) -> bool:
    """Return whether ``module`` is neither standard library nor shipped here."""
    top = module.partition(".")[0]
    first_party = {package.name for package in _shipped_packages()}
    return top not in sys.stdlib_module_names and top not in first_party


@cache
def _providers() -> dict[str, list[str]]:
    """Return the installed distributions for each top-level import name."""
    return packages_distributions()


@cache
def _distribution_files(name: str) -> tuple[str, ...] | None:
    """Return the files distribution ``name`` installed, or None if unrecorded."""
    files = distribution(name).files
    return None if files is None else tuple(str(file) for file in files)


@cache
def _owning_distributions(module: str) -> frozenset[str]:
    """Return the installed distributions whose files provide ``module``.

    Matching the module path, not only its top-level name, keeps a namespace
    package such as ``opentelemetry`` attributed to the distribution that
    installs the imported submodule.
    """
    prefixes = (module.replace(".", "/") + "/", module.replace(".", "/") + ".")
    owners = set()
    for name in _providers().get(module.partition(".")[0], ()):
        files = _distribution_files(name)
        if files is None or any(file.startswith(prefixes) for file in files):
            owners.add(canonicalize_name(name))
    return frozenset(owners)


def test_module_level_third_party_imports_are_core_dependencies() -> None:
    """Every module-level third-party import comes from a declared core dependency."""
    declared = _core_dependencies()
    undeclared = sorted(
        f"{path.relative_to(REPO_ROOT)}: {module}"
        for path in _core_python_files()
        for module in _module_level_imports(path)
        if _is_third_party(module) and not _owning_distributions(module) & declared
    )
    assert not undeclared, (
        "these module-level imports do not come from a distribution in "
        "[project].dependencies (a transitive or extra-only dependency is not "
        "enough): " + ", ".join(undeclared)
    )


def test_the_scan_covers_the_host_key_import_every_command_loads() -> None:
    """The guard reads ``host_keys`` and resolves its ``asyncssh`` import."""
    host_keys = SRC / "aptl" / "core" / "host_keys.py"
    assert host_keys in _core_python_files()
    assert "asyncssh" in _module_level_imports(host_keys)
    assert _owning_distributions("asyncssh") == {"asyncssh"}
