"""TechVault scenarios cannot report success on the default bridge (#1700)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aptl.core.deployment import (
    DockerComposeBackend,
)
from aptl.core.lab_types import LabResult
from tests.test_compose_network_readback import _info


@pytest.mark.parametrize(
    "selection",
    [
        "techvault",
        "bounded-participant-agency-techvault",
        "techvault-attacker-target",
        "techvault-defensive-min",
        "techvault-enterprise-web",
    ],
)
def test_authored_scenario_networks_cannot_report_success_on_default_bridge(
    tmp_path, selection
):
    """Use real admission/lowering for every plausible reported variant."""
    from raes import parse_sdl_file
    from raes_runtime.manager import RuntimeManager

    from aptl.backends.raes import create_aptl_runtime_target
    from aptl.backends.raes_realization import interpret_provisioning_plan
    from aptl.backends.scenario_runtime_parameters import resolve_runtime_parameters
    from aptl.core.config import AptlConfig
    from aptl.core.deployment._compose_base_container_realization import _needs_compose
    from aptl.core.deployment._compose_realization_networks import (
        _concrete_network_name,
    )
    from aptl.core.scenario_bundle import env_pack_bundle, project_tree_bundle

    root = Path(__file__).resolve().parents[2]
    bundle = (
        env_pack_bundle(tmp_path / "packs", "techvault")
        if selection == "techvault"
        else project_tree_bundle(root, root / "scenarios" / f"{selection}.sdl.yaml")
    )
    config = AptlConfig()
    backend = DockerComposeBackend(project_dir=tmp_path, project_name="test")
    target = create_aptl_runtime_target(
        project_dir=tmp_path,
        config=config,
        backend=backend,
        bundle=bundle,
    )
    plan = RuntimeManager(target).plan(
        parse_sdl_file(bundle.sdl_path),
        parameters=resolve_runtime_parameters(bundle),
    )
    lowered = interpret_provisioning_plan(
        plan=plan.provisioning,
        config=config,
        bundle=bundle,
        component_root=root,
    )
    assert not [d.message for d in lowered.diagnostics if d.is_error]
    spec = lowered.deployment_spec([])
    assert _needs_compose(spec) == (selection != "bounded-participant-agency-techvault")
    assert spec.nodes
    assert spec.networks
    assert all(node.network_attachments for node in spec.nodes)

    backend.host_list_lab_networks = MagicMock(
        return_value=[_concrete_network_name(n.name, "test") for n in spec.networks]
    )
    backend.container_inspect = MagicMock(return_value=_info())
    backend.connect_container_network = MagicMock(return_value=LabResult(success=True))
    backend.disconnect_container_network = MagicMock(
        return_value=LabResult(success=True)
    )

    failures = backend._reconcile_realization_networks(spec)

    assert failures
    assert all("missing declared network attachment" in failure for failure in failures)
    assert backend.connect_container_network.call_count == sum(
        len(n.network_attachments) for n in spec.nodes
    )
    backend.disconnect_container_network.assert_not_called()
