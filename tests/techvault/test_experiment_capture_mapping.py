"""Capture binding against the TechVault built-in fleet is deterministic (#1700)."""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402
from raes_contracts.contracts import ExperimentCaptureSpecModel

from aptl.core.experiment.capture_mapping import bind_capture_requirements
from aptl.core.experiment.capture_registry import (
    CollectorRegistry,
)
from aptl.core.experiment.errors import AdmissionRejection
from aptl.core.experiment.policy import (
    default_admission_policy,
)
from aptl_techvault.capture_registrations import BUILTIN_REGISTRATIONS
from tests.test_experiment_capture_mapping import _CAPTURE_KINDS, _CAPTURE_SCOPES, _read

#: The (capture_kind, capture_scope) pairs the TechVault built-in fleet covers
#: for the reference requirement's other axes (media/integrity/window/etc.).
#: EXP-010 PR 2 turned these on; every other legal combination still fails
#: closed. Since #1141 that fleet is contributed by the admitted TechVault pack,
#: not the core default registry, which is an honest empty baseline.
_COVERED_BY_TECHVAULT_FLEET = frozenset(
    {
        ("observation", "participant"),
        ("log", "service"),
        ("log", "network"),
        ("telemetry", "service"),
        ("trace", "run"),
    }
)


@pytest.mark.fuzz
class TestFuzzCaptureRequirementsDeterministic:
    @given(
        capture_kind=st.sampled_from(_CAPTURE_KINDS),
        capture_scope=st.sampled_from(_CAPTURE_SCOPES),
    )
    @settings(max_examples=56, deadline=2000)
    def test_every_legal_kind_scope_combination_is_deterministic_against_each_fleet(
        self, capture_kind, capture_scope
    ):
        payload = json.loads(
            _read(
                "experiment-core",
                "experiment-capture-spec-v1",
                "valid",
                "reference.json",
            )
        )
        requirement = next(iter(payload["capture_requirements"].values()))
        requirement["capture_kind"] = capture_kind
        requirement["capture_scope"] = capture_scope
        # Hold every non-fuzzed axis at the exact common built-in policy. The
        # corpus fixture intentionally uses free-form legacy retention prose,
        # which the v2 registry now rejects rather than treating as equivalent
        # to run_lifetime. Loss disclosure is disabled here because the Tempo
        # source cannot truthfully account for upstream exporter loss.
        requirement["retention_policy"] = "run_lifetime"
        requirement["loss_disclosure_required"] = False
        payload["capture_requirements"] = {requirement["requirement_id"]: requirement}
        spec = ExperimentCaptureSpecModel.model_validate(payload)
        policy = default_admission_policy()

        # The core default registry carries no collectors, so admission without
        # a pack-contributed registry fails closed for every combination.
        with pytest.raises(AdmissionRejection):
            bind_capture_requirements([spec], policy=policy)

        techvault = CollectorRegistry(BUILTIN_REGISTRATIONS)
        if (capture_kind, capture_scope) in _COVERED_BY_TECHVAULT_FLEET:
            bindings = bind_capture_requirements(
                [spec], registry=techvault, policy=policy
            )
            assert len(bindings) == 1
            assert bindings == bind_capture_requirements(
                [spec], registry=techvault, policy=policy
            )
        else:
            with pytest.raises(AdmissionRejection):
                bind_capture_requirements([spec], registry=techvault, policy=policy)
