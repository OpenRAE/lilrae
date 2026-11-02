"""A native deletion request must never enter the start/realization path."""

from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp
from raes_contracts.runtime_state import RuntimeSnapshot

from aptl.backends.raes_provisioner import AptlProvisioner
from aptl.core.config import AptlConfig
from aptl.core.scenario_bundle import ScenarioBundle


def test_unbound_delete_is_refused_without_trying_to_start_the_lab(tmp_path):
    class Provisioner(AptlProvisioner):
        def realize_plan(self, plan):
            raise AssertionError("DELETE entered the lab-start realization path")

    provisioner = Provisioner(
        project_dir=tmp_path,
        config=AptlConfig(),
        deployment_backend=None,
        bundle=ScenarioBundle("test", tmp_path, tmp_path / "scenario.yaml"),
    )
    snapshot = RuntimeSnapshot()
    plan = ProvisioningPlan(
        resources={},
        operations=[
            ProvisionOp(
                action=ChangeAction.DELETE,
                address="provision.node.victim",
                resource_type="node",
                payload={},
            )
        ],
    )
    result = provisioner.apply(plan, snapshot)
    assert not result.success
    assert result.snapshot is snapshot
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "lilrae.provisioner.delete-scope-unavailable"
    ]
