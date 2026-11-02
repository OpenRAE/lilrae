#!/usr/bin/env python3
"""Check enrolled code against the ADR-064 layers and code conventions.

``[tool.lilrae.architecture]`` in ``pyproject.toml`` holds the layer map and
the list of enrolled packages and modules. The check first validates the map:
each entry names a module, and each module has exactly one layer. Then it
checks the enrolled code for:

* an import of a layer that the importer's layer may not use, directly or
  through other modules, including imports in functions, in ``TYPE_CHECKING``
  blocks, and through package initializers;
* an import cycle through an enrolled module, and a cycle between the
  children of a package whose modules are all enrolled;
* an import of a private name, or of an internal module from outside its
  package;
* a Typer parameter that does not use the ``Annotated`` style;
* a finding of the Ruff rules in ``ruff-select``.

grimp builds the import graph from the source text. The check imports no
project code, and it reports module names, paths, lines, and rules only.

Usage: ``python tools/check_architecture.py [--root PATH]``
"""

import argparse
import ast
import importlib
import subprocess
import sys
import tomllib
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import grimp

LAYERS = ("entry", "application", "adapters", "core", "foundation", "plugins")
_MAY_IMPORT = {
    "entry": frozenset({"entry", "application", "adapters", "core", "foundation"}),
    "application": frozenset({"application", "core", "foundation"}),
    "adapters": frozenset({"core", "foundation"}),
    "core": frozenset({"core", "foundation"}),
    "foundation": frozenset({"foundation"}),
    "plugins": frozenset(),
}
_SETTINGS = frozenset({"enrolled", "extension-api", "layers", "ruff-select", "ruff-ignore"})
_TYPER_PARAMETERS = frozenset({"Argument", "Option"})


class ConfigError(Exception):
    """The layer map or the enrolled list is not valid."""


@dataclass(frozen=True)
class Slot:
    """The layer of a module, with its adapter or plugin in a grouped layer."""

    layer: str
    group: str | None = None

    def __str__(self) -> str:
        return f"{self.layer}:{self.group}" if self.group else self.layer


@dataclass(frozen=True)
class Settings:
    """The validated ``[tool.lilrae.architecture]`` table."""

    members: Mapping[str, Slot]
    enrolled: tuple[str, ...]
    extension_api: tuple[str, ...]
    ruff_select: tuple[str, ...]
    ruff_ignore: tuple[str, ...]

    @property
    def roots(self) -> tuple[str, ...]:
        return tuple(sorted({member.split(".")[0] for member in self.members}))


def load_settings(root: Path) -> Settings:
    """Read and type-check the architecture table of ``root/pyproject.toml``."""
    try:
        with (root / "pyproject.toml").open("rb") as handle:
            table = tomllib.load(handle)["tool"]["lilrae"]["architecture"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as error:
        raise ConfigError(f"cannot read [tool.lilrae.architecture]: {error!r}") from error
    unknown, missing = set(table) - _SETTINGS, _SETTINGS - set(table)
    if unknown or missing:
        raise ConfigError(f"unknown keys {sorted(unknown)}, missing keys {sorted(missing)}")
    return Settings(
        members=_members(table["layers"]),
        enrolled=_names(table, "enrolled"),
        extension_api=_names(table, "extension-api"),
        ruff_select=_names(table, "ruff-select"),
        ruff_ignore=_names(table, "ruff-ignore"),
    )


def _names(table: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{key} must be a list of names")
    if len(set(value)) != len(value):
        raise ConfigError(f"{key} names an entry twice")
    return tuple(value)


def _members(layers: object) -> dict[str, Slot]:
    if not isinstance(layers, dict) or set(layers) != set(LAYERS):
        raise ConfigError(f"layers must have exactly the keys {list(LAYERS)}")
    adapters = layers["adapters"]
    if not isinstance(adapters, dict):
        raise ConfigError("layers.adapters must map each adapter to its modules")
    entries = [(name, Slot("adapters", group)) for group in adapters for name in _names(adapters, group)]
    entries += [(name, Slot("plugins", name)) for name in _names(layers, "plugins")]
    for layer in ("entry", "application", "core", "foundation"):
        entries += [(name, Slot(layer)) for name in _names(layers, layer)]
    members = dict(entries)
    if len(members) != len(entries):
        raise ConfigError("the layer map names a module twice")
    return members


def build_graph(root: Path, roots: Iterable[str]) -> grimp.ImportGraph:
    """Build the static import graph of ``roots`` from ``root/src``."""
    source = str(root / "src")
    sys.path.insert(0, source)
    importlib.invalidate_caches()
    try:
        return grimp.build_graph(*roots, cache_dir=None)
    finally:
        sys.path.remove(source)
        importlib.invalidate_caches()


def assign_slots(graph: grimp.ImportGraph, settings: Settings) -> dict[str, Slot]:
    """Give each module the slot of its most specific layer map entry."""
    for name in (*settings.members, *settings.enrolled, *settings.extension_api):
        if name not in graph.modules:
            raise ConfigError(f"{name} is not a module")
    slots: dict[str, Slot] = {}
    for module in sorted(graph.modules):
        slot = _most_specific(module, settings.members)
        if slot is not None:
            slots[module] = slot
        elif module not in settings.roots:
            raise ConfigError(f"{module} has no layer")
    for name in settings.extension_api:
        if slots[name].layer != "core":
            raise ConfigError(f"extension API module {name} is not in the core layer")
    for name in settings.enrolled:
        spread = sorted({str(slots[module]) for module in _subtree(graph, name)})
        if len(spread) != 1:
            raise ConfigError(f"enrolled entry {name} spans {spread}")
    return slots


def _most_specific(module: str, members: Mapping[str, Slot]) -> Slot | None:
    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        slot = members.get(".".join(parts[:end]))
        if slot is not None:
            return slot
    return None


def _subtree(graph: grimp.ImportGraph, name: str) -> set[str]:
    return {name} | graph.find_descendants(name)


def enrolled_modules(graph: grimp.ImportGraph, settings: Settings) -> set[str]:
    """Return every module inside an enrolled entry."""
    return set().union(*(_subtree(graph, name) for name in settings.enrolled))


def may_import(origin: Slot, target: Slot | None, module: str, extension_api: Iterable[str]) -> bool:
    """Return whether code in ``origin`` may import ``module`` (ADR-064)."""
    if target is None:
        return True
    if origin.group is not None and origin.group == target.group:
        return True
    if origin.layer == "plugins":
        return any(module == api or module.startswith(f"{api}.") for api in extension_api)
    return target.layer in _MAY_IMPORT[origin.layer]


def _dependencies(graph: grimp.ImportGraph, module: str) -> set[str]:
    """Return the modules that loading ``module`` runs first.

    Python runs each enclosing package initializer before the module itself.
    """
    parts = module.split(".")
    packages = {".".join(parts[:end]) for end in range(1, len(parts))}
    return graph.find_modules_directly_imported_by(module) | (packages & graph.modules)


def layer_findings(
    graph: grimp.ImportGraph, slots: Mapping[str, Slot], sources: Iterable[str], extension_api: Iterable[str]
) -> Iterator[str]:
    """Report each import that breaks a layer rule in the import closure of enrolled code.

    The importer's own layer decides each import, so a plugin can use the
    extension API, and the API can use the rest of core.
    """
    api = tuple(extension_api)
    crossings: dict[tuple[str, str], list[list[str]]] = {}
    for source in sorted(sources):
        for chain in _forbidden_chains(graph, slots, source, api):
            crossings.setdefault((chain[-2], chain[-1]), []).append(chain)
    for (importer, imported), chains in sorted(crossings.items()):
        yield (
            f"{slots[importer]} code must not import {slots[imported]}: {importer} -> {imported}, "
            f"reached from {len(chains)} enrolled module(s), for example {render(graph, chains[0])}"
        )


def _forbidden_chains(
    graph: grimp.ImportGraph, slots: Mapping[str, Slot], source: str, api: tuple[str, ...]
) -> Iterator[list[str]]:
    parents: dict[str, str] = {}
    queue = deque([source])
    while queue:
        current = queue.popleft()
        origin = slots.get(current)
        for target in sorted(_dependencies(graph, current)):
            # Check every import, even of a module that another path already
            # reached; the visited set only limits which modules expand.
            if origin is not None and not may_import(origin, slots.get(target), target, api):
                yield [*_chain(parents, source, current), target]
            elif target != source and target not in parents:
                parents[target] = current
                queue.append(target)


@dataclass
class _Tarjan:
    """Strongly connected components of the explicit import graph."""

    graph: grimp.ImportGraph
    index: dict[str, int] = field(default_factory=dict)
    lowlink: dict[str, int] = field(default_factory=dict)
    stack: list[str] = field(default_factory=list)
    components: list[frozenset[str]] = field(default_factory=list)

    def run(self) -> list[frozenset[str]]:
        for module in sorted(self.graph.modules):
            if module not in self.index:
                self._visit(module)
        return self.components

    def _enter(self, module: str) -> Iterator[str]:
        self.index[module] = self.lowlink[module] = len(self.index)
        self.stack.append(module)
        return iter(sorted(self.graph.find_modules_directly_imported_by(module)))

    def _visit(self, start: str) -> None:
        work = [(start, self._enter(start))]
        while work:
            module, targets = work[-1]
            target = next(targets, None)
            if target is None:
                work.pop()
                if work:
                    parent = work[-1][0]
                    self.lowlink[parent] = min(self.lowlink[parent], self.lowlink[module])
                if self.lowlink[module] == self.index[module]:
                    self._close(module)
            elif target not in self.index:
                work.append((target, self._enter(target)))
            elif target in self.stack:
                self.lowlink[module] = min(self.lowlink[module], self.index[target])

    def _close(self, module: str) -> None:
        position = self.stack.index(module)
        component = frozenset(self.stack[position:])
        del self.stack[position:]
        if len(component) > 1:
            self.components.append(component)


def module_cycle_findings(graph: grimp.ImportGraph, sources: set[str]) -> Iterator[str]:
    """Report each import cycle that includes an enrolled module."""
    for component in _Tarjan(graph).run():
        enrolled = sorted(component & sources)
        if enrolled:
            cycle = _cycle_through(graph, enrolled[0])
            yield (
                f"import cycle of {len(component)} modules through enrolled {enrolled[0]}: "
                f"{render(graph, cycle)}"
            )


def _cycle_through(graph: grimp.ImportGraph, source: str) -> list[str]:
    parents: dict[str, str] = {}
    queue = deque([source])
    while queue and source not in parents:
        current = queue.popleft()
        for target in sorted(graph.find_modules_directly_imported_by(current)):
            if target not in parents:
                parents[target] = current
                queue.append(target)
    return [*_chain(parents, source, parents[source]), source]


def package_cycle_findings(graph: grimp.ImportGraph, slots: Mapping[str, Slot], covered: set[str]) -> Iterator[str]:
    """Report a cycle between the children of each fully enrolled package."""
    complete = covered | (set(graph.modules) - set(slots))
    for package in sorted(graph.modules):
        if not graph.find_children(package) or not _subtree(graph, package) <= complete:
            continue
        breakers = sorted(graph.nominate_cycle_breakers(package))
        if breakers:
            imports = ", ".join(f"{importer} -> {imported}" for importer, imported in breakers)
            yield f"children of {package} import each other in a cycle; removing these imports breaks it: {imports}"


def _chain(parents: Mapping[str, str], source: str, target: str) -> list[str]:
    chain = [target]
    while chain[-1] != source:
        chain.append(parents[chain[-1]])
    return chain[::-1]


def render(graph: grimp.ImportGraph, chain: list[str]) -> str:
    """Render an import chain with the line of each explicit import."""
    hops = []
    for importer, imported in zip(chain, chain[1:], strict=False):
        details = graph.get_import_details(importer=importer, imported=imported)
        where = f"line {details[0]['line_number']}" if details else "package initializer"
        hops.append(f"{importer} -> {imported} ({where})")
    return "; ".join(hops)


def module_path(root: Path, module: str) -> Path:
    """Return the source file of ``module`` under ``root/src``."""
    base = root / "src" / Path(*module.split("."))
    package = base / "__init__.py"
    return package if package.is_file() else base.with_suffix(".py")


def source_findings(root: Path, modules: Iterable[str], known: set[str]) -> Iterator[str]:
    """Report private imports and default-style Typer parameters in ``modules``."""
    for module in sorted(modules):
        path = module_path(root, module)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        relative = path.relative_to(root)
        for line, problem in sorted((*_private_imports(tree, package, known), *_typer_defaults(tree))):
            yield f"{relative}:{line}: {problem}"


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _private_imports(tree: ast.Module, package: str, known: set[str]) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield from _internal_module(alias.name, package, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(node, package)
            yield from _internal_module(base, package, node.lineno)
            for alias in node.names:
                if f"{base}.{alias.name}" in known:
                    yield from _internal_module(f"{base}.{alias.name}", package, node.lineno)
                elif _is_private(alias.name):
                    yield node.lineno, f"imports private name {alias.name} from {base}"


def _absolute(node: ast.ImportFrom, package: str) -> str:
    if not node.level:
        return node.module or ""
    parts = package.split(".")
    base = parts[: len(parts) - node.level + 1]
    return ".".join([*base, node.module] if node.module else base)


def _internal_module(module: str, package: str, line: int) -> Iterator[tuple[int, str]]:
    parts = module.split(".")
    for index, part in enumerate(parts):
        owner = ".".join(parts[:index])
        if _is_private(part) and not (package == owner or package.startswith(f"{owner}.")):
            yield line, f"imports internal module {'.'.join(parts[: index + 1])} from outside {owner or 'its package'}"


def _typer_defaults(tree: ast.Module) -> Iterator[tuple[int, str]]:
    modules: set[str] = set()
    functions: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules |= {alias.asname or alias.name for alias in node.names if alias.name == "typer"}
        elif isinstance(node, ast.ImportFrom) and node.module == "typer":
            functions |= {alias.asname or alias.name for alias in node.names if alias.name in _TYPER_PARAMETERS}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if _is_typer_call(default, modules, functions):
                    yield default.lineno, f"Typer parameter of {node.name} is not in the Annotated style"


def _is_typer_call(node: ast.expr | None, modules: set[str], functions: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    called = node.func
    if isinstance(called, ast.Attribute) and isinstance(called.value, ast.Name):
        return called.value.id in modules and called.attr in _TYPER_PARAMETERS
    return isinstance(called, ast.Name) and called.id in functions


def ruff_status(root: Path, settings: Settings) -> int:
    """Run the Ruff rules of ``settings`` on the enrolled files; return Ruff's status."""
    paths = []
    for name in settings.enrolled:
        path = module_path(root, name)
        paths.append(str((path.parent if path.name == "__init__.py" else path).relative_to(root)))
    command = [sys.executable, "-m", "ruff", "check", "--no-fix", "--output-format", "concise"]
    command += ["--select", ",".join(settings.ruff_select)]
    if settings.ruff_ignore:
        command += ["--ignore", ",".join(settings.ruff_ignore)]
    result = subprocess.run([*command, "--", *paths], cwd=root, check=False, capture_output=True, text=True)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def check(root: Path) -> int:
    """Run every check on the repository at ``root`` and return the exit status."""
    try:
        settings = load_settings(root)
        graph = build_graph(root, settings.roots)
        slots = assign_slots(graph, settings)
    except ConfigError as error:
        print(f"check_architecture: configuration error: {error}", file=sys.stderr)
        return 2
    print(f"check_architecture: the layer map assigns {len(slots)} modules.")
    sources = enrolled_modules(graph, settings)
    if not sources:
        print("check_architecture: no code is enrolled, so no module checks ran.")
        return 0
    findings = [
        *layer_findings(graph, slots, sources, settings.extension_api),
        *module_cycle_findings(graph, sources),
        *package_cycle_findings(graph, slots, sources),
        *source_findings(root, sources, set(graph.modules)),
    ]
    for finding in findings:
        print(finding)
    status = ruff_status(root, settings)
    print(f"check_architecture: {len(sources)} enrolled modules, {len(findings)} findings, Ruff exit status {status}.")
    return 1 if findings or status else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check enrolled code against ADR-064.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return check(parser.parse_args(argv).root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
