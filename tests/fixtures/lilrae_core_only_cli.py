"""Run the public CLI with original-family imports unavailable in CI."""

import importlib.abc
import json
from pathlib import Path
import sys


class RejectFamilyImports(importlib.abc.MetaPathFinder):
    """Make accidental original-family startup dependencies fail visibly."""

    def __init__(self):
        ledger = Path(__file__).resolve().parents[2] / '.gc/pack-ownership.json'
        owned = json.loads(ledger.read_text())['owned_paths']
        self.blocked = ('aptl_techvault', *(
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
