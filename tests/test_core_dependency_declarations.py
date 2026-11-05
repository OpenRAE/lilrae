"""Guard: a plain install provides every module that shipped code imports at load.

``aptl.core.host_keys`` imports ``asyncssh`` at module level, and every
``lilrae`` command loads it, but ``asyncssh`` was declared only in the ``web``
extra. raes 7.0.0 happened to require it, so a plain ``pip install lilrae``
worked; raes 8 does not, and ``lilrae lab init`` failed with
``ModuleNotFoundError: No module named 'asyncssh'``.

A transitive or extra-only dependency is not a declaration. These tests
resolve each module-level import in the shipped packages to the installed
distribution that provides it, and require that distribution in
``[project].dependencies``.

The web API (``aptl.api``) and the workbench (``aptl.workbench``) need the
``web`` extra, so they are not scan roots. A module in them is still in scope
when other shipped code loads it through module-level imports, because a plain
install then loads it too.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterator, Mapping
from functools import cache
from importlib.metadata import distribution, packages_distributions
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
WEB_ONLY_PACKAGES = ("aptl.api", "aptl.workbench")

# A ``try`` block that catches one of these makes its imports optional.
_IMPORT_FAILURE_HANDLERS = frozenset(
    {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
)


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


def _source_modules(packages: list[Path]) -> dict[str, Path]:
    """Map each dotted module name in ``packages`` to its source file."""
    modules: dict[str, Path] = {}
    for package in packages:
        for path in sorted(package.rglob("*.py")):
            parts = path.relative_to(package.parent).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            modules[".".join(parts)] = path
    return modules


def _is_type_checking(test: ast.expr) -> bool:
    """Return whether an ``if`` test is ``TYPE_CHECKING``."""
    return ast.unparse(test) in {"TYPE_CHECKING", "typing.TYPE_CHECKING"}


def _catches_import_failure(node: ast.Try) -> bool:
    """Return whether a ``try`` block handles a failed import."""
    for handler in node.handlers:
        if handler.type is None:
            return True
        caught = (
            handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        )
        if any(ast.unparse(name) in _IMPORT_FAILURE_HANDLERS for name in caught):
            return True
    return False


def _load_time_imports(
    statements: list[ast.stmt],
) -> Iterator[ast.Import | ast.ImportFrom]:
    """Yield the import statements that run when the module loads.

    The walk enters top-level ``if``, ``with``, and ``try`` blocks. It skips
    ``if TYPE_CHECKING`` bodies, the body of a ``try`` that handles a failed
    import, and exception handlers. Function and class bodies do not run at
    load, so the walk does not enter them.
    """
    for node in statements:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, ast.If):
            if not _is_type_checking(node.test):
                yield from _load_time_imports(node.body)
            yield from _load_time_imports(node.orelse)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            yield from _load_time_imports(node.body)
        elif isinstance(node, (ast.Try, ast.TryStar)):
            if not _catches_import_failure(node):
                yield from _load_time_imports(node.body)
            yield from _load_time_imports(node.orelse)
            yield from _load_time_imports(node.finalbody)


def _parse(path: Path) -> ast.Module:
    """Return the syntax tree of ``path``."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_level_imports(path: Path) -> set[str]:
    """Return the absolute modules a file imports when it loads."""
    modules: set[str] = set()
    for node in _load_time_imports(_parse(path).body):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def _absolute_base(node: ast.ImportFrom, module: str, is_package: bool) -> str:
    """Return the absolute module that a ``from`` import names."""
    if node.level == 0:
        return node.module or ""
    parts = module.split(".")
    anchor = parts if is_package else parts[:-1]
    anchor = anchor[: len(anchor) - (node.level - 1)]
    return ".".join([*anchor, node.module] if node.module else anchor)


def _first_party_loads(
    module: str, path: Path, modules: Mapping[str, Path]
) -> set[str]:
    """Return the shipped modules that loading ``module`` also loads."""
    loaded: set[str] = set()
    is_package = path.name == "__init__.py"
    for node in _load_time_imports(_parse(path).body):
        if isinstance(node, ast.Import):
            loaded.update(alias.name for alias in node.names)
            continue
        base = _absolute_base(node, module, is_package)
        loaded.add(base)
        loaded.update(f"{base}.{alias.name}" for alias in node.names)
    return {name for name in loaded if name in modules}


def _parent_packages(module: str) -> Iterator[str]:
    """Yield the packages Python loads before ``module``."""
    parts = module.split(".")
    for end in range(1, len(parts)):
        yield ".".join(parts[:end])


def _modules_loaded_without_web(
    modules: Mapping[str, Path], web_only: tuple[str, ...]
) -> set[str]:
    """Return the modules a plain install loads.

    The roots are every module outside ``web_only``. The result adds each
    module the roots load, directly or through other modules, at load time.
    """

    def in_web_only(name: str) -> bool:
        return any(name == web or name.startswith(f"{web}.") for web in web_only)

    pending = [name for name in modules if not in_web_only(name)]
    loaded: set[str] = set()
    while pending:
        name = pending.pop()
        if name in loaded:
            continue
        loaded.add(name)
        pending.extend(p for p in _parent_packages(name) if p in modules)
        pending.extend(_first_party_loads(name, modules[name], modules))
    return loaded


def _core_python_files() -> list[Path]:
    """Return the shipped sources that a plain install loads."""
    modules = _source_modules(_shipped_packages())
    loaded = _modules_loaded_without_web(modules, WEB_ONLY_PACKAGES)
    return sorted(modules[name] for name in loaded)


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


def test_the_scan_follows_core_imports_into_web_only_packages(tmp_path: Path) -> None:
    """A web-only module that core code loads is in scope; an unloaded one is not."""
    package = tmp_path / "pkg"
    (package / "web").mkdir(parents=True)
    (package / "cli").mkdir()
    sources = {
        "__init__.py": "",
        "cli/__init__.py": "",
        "cli/main.py": "from pkg.cli import serve\n",
        "cli/serve.py": "from pkg.web.deps import resolve\n",
        "web/__init__.py": "",
        "web/deps.py": "import fastapi\nfrom . import paths\n",
        "web/paths.py": "",
        "web/app.py": "import uvicorn\n",
    }
    for relative, text in sources.items():
        (package / relative).write_text(text, encoding="utf-8")

    loaded = _modules_loaded_without_web(_source_modules([package]), ("pkg.web",))

    assert {"pkg.web", "pkg.web.deps", "pkg.web.paths"} <= loaded
    assert "pkg.web.app" not in loaded


def test_load_time_imports_enter_blocks_that_run_at_load(tmp_path: Path) -> None:
    """Imports in top-level blocks count unless they are optional or type-only."""
    source = tmp_path / "module.py"
    source.write_text(
        "import sys\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    import typed_only\n"
        "if sys.platform:\n"
        "    import platform_branch\n"
        "else:\n"
        "    import other_branch\n"
        "try:\n"
        "    import optional_extra\n"
        "except ImportError:\n"
        "    import optional_fallback\n"
        "try:\n"
        "    import required_in_try\n"
        "except ValueError:\n"
        "    pass\n"
        "else:\n"
        "    import try_else\n"
        "finally:\n"
        "    import try_finally\n"
        "with open(__file__):\n"
        "    import inside_with\n"
        "def lazy():\n"
        "    import function_local\n",
        encoding="utf-8",
    )

    assert _module_level_imports(source) == {
        "sys",
        "typing",
        "platform_branch",
        "other_branch",
        "required_in_try",
        "try_else",
        "try_finally",
        "inside_with",
    }
