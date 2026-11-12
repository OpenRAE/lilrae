"""Run the public CLI with original-family imports unavailable in CI."""

import importlib.abc
from importlib import metadata
import json
from pathlib import Path
import sys


def installed_adapter_packages():
    """Return the installed packages that provide out-of-core ``aptl.*`` entry points."""
    packages = {
        entry_point.value.split(':', 1)[0].split('.', 1)[0]
        for distribution in metadata.distributions()
        for entry_point in distribution.entry_points
        if entry_point.group.startswith('aptl.')
    }
    return sorted(packages - {'aptl'})


class RejectFamilyImports(importlib.abc.MetaPathFinder):
    """Make accidental original-family startup dependencies fail visibly."""

    def __init__(self):
        ledger = Path(__file__).resolve().parents[2] / '.gc/pack-ownership.json'
        owned = json.loads(ledger.read_text())['owned_paths']
        self.blocked = (*installed_adapter_packages(), *(
            row['path'].removeprefix('src/').removesuffix('.py').replace('/', '.')
            for row in owned
        ))

    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in self.blocked):
            raise ImportError('original-family module is unavailable in the core-only test')
        return None


def main():
    guard = RejectFamilyImports()
    sys.meta_path.insert(0, guard)
    try:
        from aptl.cli.main import app
        app()
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    main()
