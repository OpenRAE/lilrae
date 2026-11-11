"""Compatibility with the independently installed RPT adapter."""

import json
from types import SimpleNamespace
import pytest
from aptl.backends.raes_evidence_acquisition import NativeEvidenceRequest
from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.experiment.capture_plan import admit_capture_demands
from aptl.core.experiment.capture_registry import CollectorRegistry
from aptl.core.runstore import LocalRunStore
from aptl.core.evidence.outcomes import CollectorStatus


@pytest.mark.integration
def test_installed_rpt_adapter_manifest_and_native_source_use_backend_capture(tmp_path):
    """Check the owner's real contribution without requiring a live study."""
    from dataclasses import fields

    rpt_capture = pytest.importorskip("rpt_techvault.capture")
    from rpt_techvault.qualification import QUALIFIED_FAMILY_TARGETS
    from aptl.backends.scenario_capture import (
        ScenarioCaptureContext,
        ResolvedScenarioCapture,
    )
    from aptl.backends.raes_evidence_acquisition import acquire_trial_evidence
    from raes_processor.capture_admission import CaptureDemand
    from tests.techvault.test_techvault_native_evidence import _Backend, _realization
    from aptl.utils.pathsafe import read_contained_nofollow

    trial = SimpleNamespace(
        scenario=SimpleNamespace(nodes={"kali": None, "suricata": None})
    )
    contribution = rpt_capture.provider.resolve(SimpleNamespace(trial=trial))
    registry = CollectorRegistry(contribution.registrations)
    manifest = create_aptl_manifest(registry=registry)
    registration = next(
        r
        for r in registry.registrations
        if r.registration_id == "rpt.collector.suricata-rule-readiness"
    )
    offer = registration.capture_offer
    assert offer in manifest.observation.capture_offers
    values = {
        f.name: getattr(offer, f.name)
        for f in fields(CaptureDemand)
        if hasattr(offer, f.name)
    }
    values = {
        key: tuple(sorted(value)) if isinstance(value, frozenset) else value
        for key, value in values.items()
    }
    demand = CaptureDemand(
        demand_id="suricata-local-rule-readiness",
        address="evidence_requirements.suricata-local-rule-readiness",
        **values,
    )
    plan = admit_capture_demands(
        (demand,), source_identity="sha256:" + "a" * 64, registry=registry
    )
    qualified = QUALIFIED_FAMILY_TARGETS[0]
    selection = ResolvedScenarioCapture(
        registry,
        contribution,
        ScenarioCaptureContext(qualified.pack, qualified.backend),
        rpt_capture.provider.provider_id,
        "1",
    )
    store = LocalRunStore(tmp_path / "runs")
    request = NativeEvidenceRequest(
        plan=plan,
        backend=_Backend(),
        realization=_realization(),
        project_dir=tmp_path,
        environment={},
        run_store=store,
        run_id="rpt-native-run",
        capture_selection=selection,
        clock=FixedClockProvider(measurement_time="2026-11-04T00:00:00Z"),
    )
    result = acquire_trial_evidence(request, attempt_id="attempt-1")
    assert len(result.refs) == 1
    assert result.reports[0].status is CollectorStatus.OK
    retained = json.loads(
        read_contained_nofollow(
            store.get_run_path(request.run_id), result.refs[0].content_uri
        )
    )
    assert retained["native_configuration"] == "ok"
    assert retained["local_rule_count"] == 16
