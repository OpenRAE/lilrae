"""The ADR-064 conventions check (#1510).

Each test writes a small source tree and a ``[tool.lilrae.architecture]`` table,
runs ``tools/check_architecture.py`` on it, and reads the exit status and the
output. The tree has one package for each layer and two adapters.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]

LAYERS = {
    "entry": ["demo.entry"],
    "application": ["demo.app"],
    "core": ["demo.core"],
    "foundation": ["demo.base"],
    "plugins": ["demo_plugin"],
    "adapters": {"store": ["demo.store"], "web": ["demo.web"]},
}

CLEAN = {
    "demo/__init__.py": "",
    "demo/base/__init__.py": "",
    "demo/base/text.py": "def upper(value: str) -> str:\n    return value.upper()\n",
    "demo/core/__init__.py": "",
    "demo/core/model.py": "from demo.base import text\n\nNAME = text.upper('demo')\n",
    "demo/core/api.py": "from demo.core import model\n\nNAME = model.NAME\n",
    "demo/app/__init__.py": "",
    "demo/app/service.py": "from demo.core import model\n\nNAME = model.NAME\n",
    "demo/store/__init__.py": "",
    "demo/store/disk.py": "from demo.core import model\n\nNAME = model.NAME\n",
    "demo/web/__init__.py": "",
    "demo/web/client.py": "from demo.core import model\n\nNAME = model.NAME\n",
    "demo/entry/__init__.py": "",
    "demo/entry/cli.py": (
        "from demo.app import service\nfrom demo.store import disk\n\nNAMES = (service.NAME, disk.NAME)\n"
    ),
    "demo_plugin/__init__.py": "",
    "demo_plugin/hooks.py": "from demo.core import api\n\nNAME = api.NAME\n",
}


@pytest.fixture(scope="module")
def check() -> ModuleType:
    path = ROOT / "tools" / "check_architecture.py"
    spec = importlib.util.spec_from_file_location("check_architecture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table(**overrides: object) -> dict[str, object]:
    table: dict[str, object] = {
        "enrolled": [],
        "extension-api": ["demo.core.api"],
        "ruff-select": ["DTZ"],
        "ruff-ignore": [],
        "layers": LAYERS,
    }
    table.update(overrides)
    return table


def _toml(table: dict[str, object]) -> str:
    lines = [
        "[project]",
        'name = "demo"',
        'version = "0"',
        'requires-python = ">=3.14"',
        "[tool.ruff]",
        "[tool.lilrae.architecture]",
    ]
    lines += [f"{key} = {json.dumps(value)}" for key, value in table.items() if key != "layers"]
    layers = table.get("layers")
    if isinstance(layers, dict):
        lines.append("[tool.lilrae.architecture.layers]")
        lines += [f"{key} = {json.dumps(value)}" for key, value in layers.items() if key != "adapters"]
        if isinstance(layers.get("adapters"), dict):
            lines.append("[tool.lilrae.architecture.layers.adapters]")
            lines += [f"{key} = {json.dumps(value)}" for key, value in layers["adapters"].items()]
    return "\n".join(lines) + "\n"


def _run(
    check: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    changes: dict[str, str] | None = None,
    **table: object,
) -> tuple[int, str]:
    for name, text in {**CLEAN, **(changes or {})}.items():
        path = tmp_path / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(_toml(_table(**table)), encoding="utf-8")
    status = check.main(["--root", str(tmp_path)])
    captured = capsys.readouterr()
    return status, captured.out + captured.err


def test_a_valid_map_with_no_enrolled_code_passes(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    status, output = _run(check, capsys, tmp_path)

    assert status == 0
    assert "no code is enrolled" in output


@pytest.mark.parametrize(
    ("changes", "table", "message"),
    [
        ({}, {"enroled": []}, "unknown keys"),
        ({}, {"enrolled": ["demo.core.missing"]}, "demo.core.missing is not a module"),
        ({}, {"layers": {**LAYERS, "core": ["demo.core.model"]}}, "demo.core has no layer"),
        ({}, {"layers": {**LAYERS, "foundation": ["demo.base", "demo.core"]}}, "names a module twice"),
        (
            {"demo/core/lab.py": ""},
            {"layers": {**LAYERS, "application": ["demo.app", "demo.core.lab"]}, "enrolled": ["demo.core"]},
            "enrolled entry demo.core spans",
        ),
        ({}, {"extension-api": ["demo.app.service"]}, "is not in the core layer"),
        ({}, {"enrolled": "demo.core"}, "enrolled must be a list of names"),
    ],
)
def test_an_invalid_configuration_fails_visibly(
    check: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    changes: dict[str, str],
    table: dict[str, object],
    message: str,
) -> None:
    status, output = _run(check, capsys, tmp_path, changes, **table)

    assert status == 2
    assert message in output


def test_a_missing_table_fails_visibly(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    assert check.main(["--root", str(tmp_path)]) == 2
    assert "cannot read [tool.lilrae.architecture]" in capsys.readouterr().err


def test_direct_and_indirect_imports_of_a_higher_layer_fail(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {
        "demo/core/direct.py": "from demo.app import service\n\nNAME = service.NAME\n",
        "demo/core/legacy.py": "from demo.store import disk\n\nNAME = disk.NAME\n",
        "demo/core/indirect.py": "from demo.core import legacy\n\nNAME = legacy.NAME\n",
    }

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.core.direct", "demo.core.indirect"])

    assert status == 1
    assert "demo.core.direct -> demo.app.service (line 1)" in output
    assert "core code must not import application" in output
    assert "demo.core.indirect -> demo.core.legacy (line 1); demo.core.legacy -> demo.store.disk (line 1)" in output


def test_a_violation_in_code_that_is_not_enrolled_passes(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {"demo/core/legacy.py": "from demo.store import disk\n\nNAME = disk.NAME\n"}

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.core.model", "demo.base"])

    assert status == 0, output


def test_function_type_checking_and_initializer_imports_count(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {
        "demo/core/lazy.py": "def name() -> str:\n    from demo.app import service\n    return service.NAME\n",
        "demo/core/typed.py": (
            "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from demo.web import client\n"
        ),
        "demo/store/values.py": "NAME = 'values'\n",
    }
    layers = {**LAYERS, "core": ["demo.core", "demo.store.values"]}
    enrolled = ["demo.core.lazy", "demo.core.typed", "demo.store.values"]

    status, output = _run(check, capsys, tmp_path, changes, enrolled=enrolled, layers=layers)

    assert status == 1
    assert "demo.core.lazy -> demo.app.service (line 2)" in output
    assert "demo.core.typed -> demo.web.client (line 4)" in output
    assert "core code must not import adapters:store: demo.store.values -> demo.store," in output
    assert "demo.store.values -> demo.store (package initializer)" in output


def test_application_and_adapters_are_peers_and_adapters_are_independent(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {
        "demo/app/uses_adapter.py": "from demo.store import disk\n\nNAME = disk.NAME\n",
        "demo/store/uses_app.py": "from demo.app import service\n\nNAME = service.NAME\n",
        "demo/store/uses_web.py": "from demo.web import client\n\nNAME = client.NAME\n",
    }
    enrolled = ["demo.app.uses_adapter", "demo.store.uses_app", "demo.store.uses_web", "demo.store.disk"]

    status, output = _run(check, capsys, tmp_path, changes, enrolled=enrolled)

    assert status == 1
    assert "application code must not import adapters:store" in output
    assert "adapters:store code must not import application" in output
    assert "adapters:store code must not import adapters:web" in output
    assert "demo.store.disk ->" not in output


def test_each_import_is_checked_when_paths_converge(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {"demo/store/disk.py": "from demo.app import service\n\nNAME = service.NAME\n"}

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.entry.cli"])

    assert status == 1
    assert "adapters:store code must not import application: demo.store.disk -> demo.app.service," in output
    assert "demo.entry.cli -> demo.store.disk (line 2); demo.store.disk -> demo.app.service (line 1)" in output


def test_plugins_import_only_the_extension_api(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {"demo_plugin/direct.py": "from demo.core import model\n\nNAME = model.NAME\n"}

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo_plugin"])

    assert status == 1
    assert "plugins:demo_plugin code must not import core: demo_plugin.direct -> demo.core.model," in output
    assert "demo_plugin.hooks" not in output


def test_no_first_party_package_imports_a_plugin(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {"demo/entry/loads.py": "from demo_plugin import hooks\n\nNAME = hooks.NAME\n"}

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.entry"])

    assert status == 1
    assert "entry code must not import plugins:demo_plugin" in output


def test_import_cycles_fail(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {
        "demo/core/first.py": "from demo.core import second\n\nNAME = 'first'\n",
        "demo/core/second.py": "def name() -> str:\n    from demo.core import first\n    return first.NAME\n",
        "demo/base/left/__init__.py": "",
        "demo/base/left/one.py": "from demo.base.right import two\n\nNAME = two.NAME\n",
        "demo/base/right/__init__.py": "",
        "demo/base/right/two.py": "NAME = 'two'\n",
        "demo/base/right/three.py": "from demo.base.left import one\n\nNAME = one.NAME\n",
    }

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.core.first", "demo.base"])

    assert status == 1
    assert "import cycle of 2 modules" in output
    assert "demo.core.second -> demo.core.first (line 2)" in output
    assert "children of demo.base import each other in a cycle" in output


def test_private_imports_fail(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {
        "demo/core/_shared.py": (
            "def _hidden() -> str:\n    return 'hidden'\n\n\ndef shown() -> str:\n    return 'shown'\n"
        ),
        "demo/core/inside.py": (
            "from demo.core._shared import shown\nfrom . import _shared\n\nNAMES = (shown, _shared)\n"
        ),
        "demo/core/name.py": "from demo.core._shared import _hidden\n\nNAME = _hidden\n",
        "demo/core/version.py": "from demo import __doc__ as doc\n\nNAME = doc\n",
        "demo/app/outside.py": "from demo.core._shared import shown\n\nNAME = shown\n",
        "demo/app/vendor.py": "from json import _default_decoder\n\nNAME = _default_decoder\n",
    }
    enrolled = ["demo.core.inside", "demo.core.name", "demo.core.version", "demo.app.outside", "demo.app.vendor"]

    status, output = _run(check, capsys, tmp_path, changes, enrolled=enrolled)

    assert status == 1
    assert "src/demo/core/name.py:1: imports private name _hidden from demo.core._shared" in output
    assert "src/demo/app/outside.py:1: imports internal module demo.core._shared from outside demo.core" in output
    assert "src/demo/app/vendor.py:1: imports private name _default_decoder from json" in output
    assert "inside.py" not in output
    assert "version.py" not in output


def test_typer_parameters_must_use_the_annotated_style(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {
        "demo/entry/old.py": "import typer\n\n\ndef run(name: str = typer.Option('x')) -> None:\n    print(name)\n",
        "demo/entry/aliased.py": (
            "from typer import Argument\n\n\ndef run(*, name: str = Argument(...)) -> None:\n    print(name)\n"
        ),
        "demo/entry/new.py": (
            "from typing import Annotated\n\nimport typer\n\n\n"
            "def run(name: Annotated[str, typer.Option()] = 'x') -> None:\n    print(name)\n"
        ),
    }

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.entry"])

    assert status == 1
    assert "src/demo/entry/old.py:4: Typer parameter of run is not in the Annotated style" in output
    assert "src/demo/entry/aliased.py:4: Typer parameter of run is not in the Annotated style" in output
    assert "new.py" not in output


def test_ruff_rules_apply_to_enrolled_files_only(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    old_union = "from typing import Optional\n\n\ndef name(value: Optional[str]) -> str | None:\n    return value\n"
    changes = {"demo/core/old.py": old_union, "demo/app/old.py": old_union}

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.core"], **{"ruff-select": ["UP"]})

    assert status == 1
    assert "UP045" in output
    assert "src/demo/core/old.py" in output
    assert "src/demo/app/old.py" not in output


def test_the_check_imports_no_project_code_and_prints_no_source_text(
    check: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    changes = {
        "demo/core/explodes.py": (
            "from demo.app import service  # TOKEN-1510\n\nraise RuntimeError('imported')\n"
        ),
    }

    status, output = _run(check, capsys, tmp_path, changes, enrolled=["demo.core.explodes"])

    assert status == 1
    assert "demo.core.explodes -> demo.app.service (line 1)" in output
    assert "TOKEN-1510" not in output
