"""Capture apparatus must be admitted before creation and reported after readback."""

from dataclasses import replace

import pytest

from aptl.backends.lilrae_apparatus_reporting import (
    append_verified_apparatus,
    prepare_apparatus_resources,
)
from aptl.core.experiment.capture_plan import CaptureApparatus
from tests.test_lilrae_runtime_inventory_reporting import reporting_runtime


APPARATUS = CaptureApparatus(
    apparatus_id="test.capture",
    service_name="capture",
    container_name="capture",
    purpose="session-capture",
    target_refs=("nodes.holder",),
    governing_scopes=("/nodes",),
    environment_visible=True,
    observer_effects=("Capture container visible on the daemon",),
)


def test_verified_capture_container_is_admitted_by_the_public_runtime(
    tmp_path, monkeypatch
):
    manager, provisioner, _, _, plan, archive = reporting_runtime(
        tmp_path, apparatus=(APPARATUS,)
    )
    original = provisioner._apply_valid_plan

    def realized(request, previous, *args):
        resources = prepare_apparatus_resources(
            request, previous, plan.manifest, (APPARATUS,)
        )
        return append_verified_apparatus(
            original(request, previous, *args),
            resources,
            (
                {
                    "apparatus_id": APPARATUS.apparatus_id,
                    "container_name": "capture",
                    "running": True,
                },
            ),
        )

    monkeypatch.setattr(provisioner, "_apply_valid_plan", realized)
    with manager:
        result = manager.apply(plan)
        assert result.success, [(d.code, d.message) for d in result.diagnostics]
        additions = set(result.snapshot.entries) - set(plan.provisioning.resources)
        captures = [address for address in additions if ".lilrae-cap-" in address]
        assert len(captures) == 1
        assert any(
            entry.address == captures[0]
            and entry.provenance.value == "backend-realized"
            for entry in result.snapshot.realization_provenance
        )
        retained = archive.read(result.snapshot.materialization_attestations[-1]).sdl
        assert captures[0].removeprefix("provision.node.") in retained


def test_capture_addition_cannot_open_a_closed_collection(tmp_path):
    manager, _, _, _, plan, _ = reporting_runtime(tmp_path, open_collection=False)
    with manager:
        request = replace(plan.provisioning, operation_id="prepare-apparatus")
        with pytest.raises(ValueError, match="collection"):
            prepare_apparatus_resources(
                request, manager.snapshot, plan.manifest, (APPARATUS,)
            )


def test_missing_native_capture_readback_grants_no_entry(tmp_path):
    manager, _, _, _, plan, _ = reporting_runtime(tmp_path)
    from raes_contracts.runtime_state import ApplyResult

    with manager:
        resources = prepare_apparatus_resources(
            replace(plan.provisioning, operation_id="prepare-apparatus"),
            manager.snapshot,
            plan.manifest,
            (APPARATUS,),
        )
        applied = ApplyResult(True, manager.snapshot)
        with pytest.raises(ValueError, match="readback"):
            append_verified_apparatus(applied, resources, ())
        assert not manager.snapshot.entries
