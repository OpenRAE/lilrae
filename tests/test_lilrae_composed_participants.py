"""Participant experiments retain parameterized, generic node composition."""

from unittest.mock import Mock

from raes.parser import parse_sdl

from aptl.backends.raes import create_aptl_runtime_target
from aptl.backends.raes_node_materialization import realize_node
from aptl.backends.raes_planning_compat import AptlRuntimeManager
from aptl.backends.raes_realization import interpret_provisioning_plan
from aptl.core.config import AptlConfig
from aptl.core.scenario_bundle import project_tree_bundle
from tests.test_raes_node_materialization import _FakeBackend


def test_node_parameters_reach_composition_without_prebaked_images(tmp_path):
    path = tmp_path / "composed.yaml"
    path.write_text("""name: composed-participant-target
variables:
  account: {type: string, default: reduser, allowed_values: [reduser, blueuser]}
  package: {type: string, default: curl, allowed_values: [curl, wazuh-manager]}
nodes:
  target:
    type: compute
    os: linux
    runtime:
      packages:
        - {manager: apt, name: '${package}', version: '*'}
      local_identity:
        users:
          - {username: '${account}'}
""")
    scenario = parse_sdl(path.read_text())
    config = AptlConfig()
    bundle = project_tree_bundle(tmp_path, path)
    target = create_aptl_runtime_target(
        project_dir=tmp_path, config=config, backend=Mock(), bundle=bundle
    )
    with AptlRuntimeManager(target) as manager:
        for account, package in (("reduser", "curl"), ("blueuser", "wazuh-manager")):
            plan = manager.plan(
                scenario, parameters={"account": account, "package": package}
            )
            assert not plan.diagnostics
            realization = interpret_provisioning_plan(
                plan=plan.provisioning, config=config, bundle=bundle
            )
            assert not realization.diagnostics
            assert len(realization.nodes) == 1
            node = realization.nodes[0]
            assert node.image is None
            backend = _FakeBackend()
            assert realize_node(node, backend) is None
            assert backend.users == {account}
            assert backend.installed == {package}
            assert (
                backend.started[0].image_ref
                == "aptl/generic-systemd-base-debian:latest"
            )
