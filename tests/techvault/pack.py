"""The released TechVault pack, realized without Docker.

Tests that check a runtime property of a TechVault node read it from this
realization: the pinned pack's SDL planned by ``RuntimeManager.plan()`` and
interpreted by ``interpret_provisioning_plan()``, which the provisioner runs on
start. Nothing boots.

Deliberately import-safe: unlike ``tests.helpers`` it reads no project ``.env``
and runs no lab script, so a test module may import it at collection time.
Named without a ``test_`` prefix so pytest does not collect it.
"""

from __future__ import annotations

import importlib.resources as ir
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TECHVAULT_FLAG_PARAMETERS = {
    f"flag_{host}_{level}": f"{host}-{level}"
    for host in ("victim", "workstation", "webapp", "fileshare", "ad")
    for level in ("user", "root")
}


def _pack_root() -> Path:
    return Path(str(ir.files("raes_env_packs") / "resources" / "packs" / "techvault"))


def techvault_scenario_bundle(staging_root: Path):
    """Stage the acquired TechVault env-pack beneath ``staging_root`` (#875)."""
    from aptl.core.scenario_bundle import env_pack_bundle

    return env_pack_bundle(Path(staging_root) / ".aptl" / "staged-packs", "techvault")


def techvault_scenario_path(staging_root: Path) -> Path:
    """Return the staged SDL path of the acquired TechVault pack (#875)."""
    return techvault_scenario_bundle(staging_root).sdl_path


def realize_techvault_pack(tmp_path, *, bundle=None, scenario=None):
    """Plan and interpret the installed TechVault pack, staged under ``tmp_path``."""

    from aptl.backends.raes import (
        RuntimeManager,
        create_aptl_runtime_target,
        parse_sdl_file,
    )
    from aptl.backends.raes_realization import interpret_provisioning_plan
    from aptl.core.config import AptlConfig
    from aptl.core.scenario_bundle import env_pack_bundle

    if bundle is None:
        bundle = env_pack_bundle(tmp_path, identity="techvault", source_pack=_pack_root())
    config = AptlConfig(
        lab={"name": "tv"},
        containers={'profiles': ['wazuh', 'victim', 'kali', 'enterprise', 'soc', 'fileshare', 'dns']},
    )
    target = create_aptl_runtime_target(
        project_dir=PROJECT_ROOT, config=config, backend=MagicMock(), bundle=bundle
    )
    if scenario is None:
        scenario = parse_sdl_file(bundle.sdl_path)
    plan = RuntimeManager(target).plan(
        scenario,
        parameters=_TECHVAULT_FLAG_PARAMETERS,
    )
    return interpret_provisioning_plan(
        plan=plan.provisioning,
        config=config,
        bundle=bundle,
        component_root=PROJECT_ROOT,
    )
