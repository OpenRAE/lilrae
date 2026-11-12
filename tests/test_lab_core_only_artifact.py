"""Built-wheel smoke proof for the generic startup import boundary."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile

import pytest
from pathlib import Path

from tests.declared_adapters import adapter_packages

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_core_only_wheel_prepares_tiny_start_without_optional_experience(
    tmp_path: Path,
) -> None:
    """A wheel containing only ``aptl`` can select an adapter-free tiny pack."""

    source = tmp_path / "source"
    source.mkdir()
    for name in ("README.md", "hatch_build.py"):
        shutil.copy2(ROOT / name, source / name)
    shutil.copytree(ROOT / "src" / "aptl", source / "src" / "aptl")

    # Build a genuine wheel from the current framework source with every
    # scenario adapter package and its entry points omitted. The main
    # distribution continues to ship its bundled adapter; this variant proves
    # the core import boundary.
    adapters = adapter_packages()
    assert adapters, "the distribution declares no adapter to omit"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pyproject, replaced = re.subn(
        r'(?m)^packages = \[[^\]]*\]$', 'packages = ["src/aptl"]', pyproject
    )
    assert replaced == 1
    pyproject = re.sub(
        r'(?ms)^\[project\.entry-points\."aptl\.[^"]+"\]\n.*?(?=^\[|\Z)',
        "",
        pyproject,
    )
    (source / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    output = tmp_path / "wheel"
    built = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(output),
            str(source),
        ],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    wheels = list(output.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        assert not any(
            name.split("/", 1)[0] in adapters for name in archive.namelist()
        )

    probe = f"ADAPTERS = {tuple(sorted(adapters))!r}\n" + r"""
import importlib.abc
import sys
from pathlib import Path
from unittest.mock import patch

class DenyOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith((*ADAPTERS, "mcp", "aptl.workbench")):
            raise ImportError("optional module is unavailable")
        return None

sys.meta_path.insert(0, DenyOptional())
import aptl
from aptl.core.config import AptlConfig
from aptl.core.lab import _LabStartContext, _selected_start_steps, _step_load_env
from aptl.backends._raes_scenario_queries import AdmittedStartSurface
from aptl.core.scenario_bundle import ScenarioBundle, ScenarioSourceKind

assert ".whl/aptl/" in str(aptl.__file__), aptl.__file__
root = Path.cwd()
bundle = ScenarioBundle("tiny", root, root / "tiny.sdl.yaml", ScenarioSourceKind.ENV_PACK)
(root / "aptl.json").write_text(AptlConfig().model_dump_json())
ctx = _LabStartContext(project_dir=root, skip_seed=False)
with patch("aptl.backends._raes_scenario_resolution.resolve_scenario_bundle", return_value=bundle), \
     patch("aptl.backends.scenario_startup.resolve_scenario_startup", return_value=None):
    assert _step_load_env(ctx) is None
assert ctx.start_selection.bundle is bundle
assert not (root / ".env").exists()
ctx.admitted_surface = AdmittedStartSurface(root, ScenarioSourceKind.ENV_PACK, ("small",), frozenset())
selected = {step.__name__ for step in _selected_start_steps(ctx)}
assert "_step_start_containers" in selected
assert "_step_attest_project_containers" in selected
assert "_step_sync_credentials" not in selected
assert "_step_seed_soc" not in selected
assert not any(name.split(".", 1)[0] in ADAPTERS for name in sys.modules)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(wheels[0])
    observed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert observed.returncode == 0, observed.stderr
