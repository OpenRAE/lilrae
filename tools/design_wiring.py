#!/usr/bin/env python3
"""Generate the component dependency view of the Python control plane.

The ADR-064 design checks need a dependency or component view that comes from
the code, not from a hand-drawn diagram. This
tool reuses the static import graph that ``tools/check_architecture.py`` builds
with grimp and the ADR-064 layer map in ``[tool.lilrae.architecture]``. It
prints each layer's module count and every observed import edge between two
layers, and then the same edges as a Mermaid graph.

The view is read-only. It builds the graph in memory, writes nothing to disk,
and leaves HEAD, the index, and the working tree unchanged.

Usage: ``python tools/design_wiring.py [--root PATH]``
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from check_architecture import Slot, assign_slots, build_graph, load_settings


def component_edges(graph: object, slots: dict[str, Slot]) -> set[tuple[str, str]]:
    """Return each import edge between two different layer components."""
    edges: set[tuple[str, str]] = set()
    for module, slot in slots.items():
        origin = str(slot)
        for target in graph.find_modules_directly_imported_by(module):
            target_slot = slots.get(target)
            if target_slot is not None and str(target_slot) != origin:
                edges.add((origin, str(target_slot)))
    return edges


def render(slots: dict[str, Slot], edges: set[tuple[str, str]]) -> str:
    """Render the component membership and the sorted edge view."""
    members = Counter(str(slot) for slot in slots.values())
    lines = [
        "design-wiring: component dependency view of src/ (grimp import graph)",
        f"modules mapped: {len(slots)}",
        f"components: {len(members)}",
    ]
    lines += [f"  {component}: {count} modules" for component, count in sorted(members.items())]
    lines.append(f"component edges: {len(edges)}")
    lines += [f"  {importer} -> {imported}" for importer, imported in sorted(edges)]
    lines.append("mermaid:")
    lines.append("graph LR")
    lines += [f"  {importer} --> {imported}" for importer, imported in sorted(edges)]
    return "\n".join(lines)


def wiring(root: Path) -> int:
    settings = load_settings(root)
    graph = build_graph(root, settings.roots)
    slots = assign_slots(graph, settings)
    print(render(slots, component_edges(graph, slots)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the ADR-064 component dependency view.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return wiring(parser.parse_args(argv).root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
