"""Backend conformance on the curated TechVault slice and gate docs (#1700)."""

import pytest

from aptl.core.config import AptlConfig
from tests.test_raes_backend import PROJECT_ROOT, _bundle, _RealizedBackend

CONFORMANCE_SCENARIO = PROJECT_ROOT / "scenarios" / "techvault-defensive-min.sdl.yaml"


def test_current_backend_docs_cover_declared_manifest_components():
    from raes_backend_protocols.manifest import backend_manifest_payload

    from aptl.backends.raes_manifest import create_aptl_manifest

    payload = backend_manifest_payload(create_aptl_manifest())
    documentation = " ".join(
        (PROJECT_ROOT / "docs" / "raes" / "techvault-static-validation-gate.md")
        .read_text()
        .split()
    )

    assert "full-remote-control-plane" in documentation
    for component in payload["capabilities"]:
        assert f"`{component}`" in documentation
    assert "standalone observation component" in documentation
    assert "compatible processors" in documentation
    assert "concept-authority bindings" in documentation
    assert "supported contract versions" in documentation


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/raes/dsl-008-realization-preflight.md",
        "docs/raes/dsl-010-participant-runtime-preflight.md",
        "docs/raes/orchestration-capable-profile-preflight.md",
        "docs/raes/techvault-live-validation-preflight.md",
        "docs/raes/techvault-static-validation-preflight.md",
    ],
)
def test_dated_profile_preflights_direct_readers_to_current_truth(relative_path):
    documentation = (PROJECT_ROOT / relative_path).read_text()

    assert '!!! warning "Historical backend-profile milestone"' in documentation
    assert "techvault-static-validation-gate.md#backend-manifest" in documentation


# techvault-defensive-min.sdl.yaml's realized containers and network (issue
# #578): the reference scenario declares six ``vm`` nodes and one ``switch``
# node, and the provisioner now reads its snapshot back from what the backend
# was actually *observed* to have realized rather than echoing the plan. A
# bare ``MagicMock`` realizes nothing observable, so the conformance target
# has to model the lab it genuinely brings up.
_CONFORMANCE_SCENARIO_CONTAINERS = (
    "aptl-wazuh-manager",
    "aptl-wazuh-indexer",
    "aptl-wazuh-dashboard",
    "aptl-otel-collector",
    "aptl-tempo",
    "aptl-grafana-otel",
)


_CONFORMANCE_SCENARIO_NETWORKS = ("security-net",)


def test_aptl_target_passes_provisioning_only_conformance():
    from raes_conformance.conformance import run_target_conformance

    from aptl.backends.raes import create_aptl_runtime_target

    backend = _RealizedBackend(
        containers=_CONFORMANCE_SCENARIO_CONTAINERS,
        networks=_CONFORMANCE_SCENARIO_NETWORKS,
    )
    config = AptlConfig(lab={"name": "test"})
    target = create_aptl_runtime_target(
        project_dir=PROJECT_ROOT,
        bundle=_bundle(PROJECT_ROOT),
        config=config,
        backend=backend,
    )

    report = run_target_conformance(
        target,
        profile="provisioning-only",
        reference_scenario=CONFORMANCE_SCENARIO,
    )

    # The realization-envelope constructive case is live-harness-only and is
    # proven at the live lab-boot gate (issue #889); the static target must pass
    # every other conformance case. This mirrors the backend-conformance gate's
    # own toleration in _gate_checks._target_conformance_diagnostics.
    from aptl.validation._gate_checks import _target_conformance_diagnostics

    assert _target_conformance_diagnostics(report) == [], (
        report.passed,
        [d.code for d in report.diagnostics],
    )
    assert report.unsupported_contract_gaps == ()
    assert report.unsupported_capability_gaps == ()


def test_aptl_target_passes_orchestration_evaluation_conformance():
    from raes_conformance.conformance import run_target_conformance

    from aptl.backends.raes import create_aptl_runtime_target

    backend = _RealizedBackend(
        containers=_CONFORMANCE_SCENARIO_CONTAINERS,
        networks=_CONFORMANCE_SCENARIO_NETWORKS,
    )
    config = AptlConfig(lab={"name": "test"})
    target = create_aptl_runtime_target(
        project_dir=PROJECT_ROOT,
        bundle=_bundle(PROJECT_ROOT),
        config=config,
        backend=backend,
    )

    report = run_target_conformance(
        target,
        profile="orchestration-evaluation",
        reference_scenario=CONFORMANCE_SCENARIO,
    )

    # The realization-envelope constructive case is live-harness-only and is
    # proven at the live lab-boot gate (issue #889); the static target must pass
    # every other conformance case. This mirrors the backend-conformance gate's
    # own toleration in _gate_checks._target_conformance_diagnostics.
    from aptl.validation._gate_checks import _target_conformance_diagnostics

    assert _target_conformance_diagnostics(report) == [], (
        report.passed,
        [d.code for d in report.diagnostics],
    )
    assert report.unsupported_contract_gaps == ()
    assert report.unsupported_capability_gaps == ()
    from aptl.validation._gate_checks import _requires_live_realization_harness

    assert all(
        case.passed
        for case in report.cases
        if not _requires_live_realization_harness(case)
    ), [
        (case.name, [d.message for d in case.diagnostics])
        for case in report.cases
        if not case.passed and not _requires_live_realization_harness(case)
    ]
    case_names = {case.name for case in report.cases}
    # With a realization envelope declared, target realization is covered by the
    # realization-envelope conformance cases; RAES supersedes the legacy
    # target-provisioning / target-snapshot adapter probes (the temporary
    # runner-parameter bridge) with the envelope design (#667/#668, issue #889).
    assert "realization-envelope-constructive" in case_names


def test_aptl_target_passes_full_remote_control_plane_conformance():
    from raes_conformance.conformance import run_target_conformance

    from aptl.backends.raes import create_aptl_runtime_target

    backend = _RealizedBackend(
        containers=_CONFORMANCE_SCENARIO_CONTAINERS,
        networks=_CONFORMANCE_SCENARIO_NETWORKS,
    )
    config = AptlConfig(lab={"name": "test"})
    target = create_aptl_runtime_target(
        project_dir=PROJECT_ROOT,
        bundle=_bundle(PROJECT_ROOT),
        config=config,
        backend=backend,
    )

    report = run_target_conformance(
        target,
        profile="full-remote-control-plane",
        reference_scenario=CONFORMANCE_SCENARIO,
    )

    # The realization-envelope constructive case is live-harness-only and is
    # proven at the live lab-boot gate (issue #889); the static target must pass
    # every other conformance case. This mirrors the backend-conformance gate's
    # own toleration in _gate_checks._target_conformance_diagnostics.
    from aptl.validation._gate_checks import _target_conformance_diagnostics

    assert _target_conformance_diagnostics(report) == [], (
        report.passed,
        [d.code for d in report.diagnostics],
    )
    assert report.unsupported_contract_gaps == ()
    assert report.unsupported_capability_gaps == ()
    from aptl.validation._gate_checks import _requires_live_realization_harness

    assert all(
        case.passed
        for case in report.cases
        if not _requires_live_realization_harness(case)
    ), [
        (case.name, [d.message for d in case.diagnostics])
        for case in report.cases
        if not case.passed and not _requires_live_realization_harness(case)
    ]
    case_names = {case.name for case in report.cases}
    # With a realization envelope declared, target realization is covered by the
    # realization-envelope conformance cases; RAES supersedes the legacy
    # target-provisioning / target-snapshot adapter probes (the temporary
    # runner-parameter bridge) with the envelope design (#667/#668, issue #889).
    assert "realization-envelope-constructive" in case_names
