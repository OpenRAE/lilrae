"""TechVault's Tempo registration cannot admit required loss accounting (#1700)."""

from __future__ import annotations

from raes_contracts.contracts import ExperimentCaptureSpecModel

from aptl.core.experiment.capture_registry import (
    CollectorRegistry,
)
from tests.test_capture_registry import _spec_with


def test_best_effort_tempo_delivery_cannot_admit_required_loss_accounting():
    from aptl_techvault.capture_registrations import BUILTIN_REGISTRATIONS

    tempo = next(
        item
        for item in BUILTIN_REGISTRATIONS
        if item.registration_id == "aptl.collector.tempo-traces"
    )
    spec = _spec_with(
        capture_kind="trace",
        capture_scope="run",
        retention_policy="run_lifetime",
        redaction_policy="redact_secrets",
        loss_disclosure_required=True,
    )
    requirement = next(iter(spec.capture_requirements.values()))
    assert CollectorRegistry((tempo,)).match(spec, requirement) is None
    # This is specifically the unavailable loss guarantee, not a wrong media,
    # role, scope or policy that accidentally makes the negative test pass.
    payload = spec.model_dump(mode="json")
    payload["capture_requirements"][requirement.requirement_id][
        "loss_disclosure_required"
    ] = False
    best_effort = ExperimentCaptureSpecModel.model_validate(payload)
    assert (
        CollectorRegistry((tempo,)).match(
            best_effort, best_effort.capture_requirements[requirement.requirement_id]
        )
        is not None
    )
