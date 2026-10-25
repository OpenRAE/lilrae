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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TECHVAULT_FLAG_PARAMETERS = {
    f"flag_{host}_{level}": f"{host}-{level}"
    for host in ("victim", "workstation", "webapp", "fileshare", "ad")
    for level in ("user", "root")
}


def _pack_root() -> Path:
    return Path(str(ir.files("raes_env_packs") / "resources" / "packs" / "techvault"))


def realize_techvault_pack(tmp_path):
    """Plan and interpret the installed TechVault pack, staged under ``tmp_path``."""

    return plan_techvault_pack(tmp_path)[1]


def plan_techvault_pack(tmp_path, edit_sdl=None):
    """Return the provisioning plan and the realization of the TechVault pack.

    ``edit_sdl`` may change the YAML document of the staged copy after
    env-packs has validated it, so a test can author one more value that RAES
    then parses like any other.
    """

    import yaml

    from aptl.backends.raes import (
        RuntimeManager,
        create_aptl_runtime_target,
        parse_sdl_file,
    )
    from aptl.backends.raes_realization import interpret_provisioning_plan
    from aptl.core.config import AptlConfig
    from aptl.core.scenario_bundle import env_pack_bundle

    bundle = env_pack_bundle(tmp_path, identity="techvault", source_pack=_pack_root())
    if edit_sdl is not None:
        document = yaml.safe_load(bundle.sdl_path.read_text(encoding="utf-8"))
        edit_sdl(document)
        bundle.sdl_path.write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )
    config = AptlConfig(
        lab={"name": "tv"},
        containers={
            "wazuh": True,
            "soc": True,
            "enterprise": True,
            "victim": True,
            "kali": True,
            "fileshare": True,
            "dns": True,
        },
    )
    target = create_aptl_runtime_target(
        project_dir=PROJECT_ROOT, config=config, backend=MagicMock(), bundle=bundle
    )
    scenario = parse_sdl_file(bundle.sdl_path)
    plan = RuntimeManager(target).plan(
        scenario,
        parameters=_TECHVAULT_FLAG_PARAMETERS,
    )
    return plan.provisioning, interpret_provisioning_plan(
        plan=plan.provisioning,
        config=config,
        bundle=bundle,
        component_root=PROJECT_ROOT,
    )
