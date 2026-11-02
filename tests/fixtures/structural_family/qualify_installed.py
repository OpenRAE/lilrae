"""Qualify a structural factorial family on installed wheels (#1465).

Run with ``python -I`` so only the installed artifacts and the interpreter's
site packages are importable:

    qualify_installed.py <installed> <fixture-helper> <fixture-dir> <source-tree> <mode>

``mode`` is ``consistent`` or ``inconsistent``. An inconsistent installation
must stop at family qualification, before any provider callback runs.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

INSTALLED, HELPER, FIXTURE, SOURCE_TREE = (Path(item) for item in sys.argv[1:5])
MODE = sys.argv[5]
sys.path.insert(0, str(INSTALLED))

import aptl  # noqa: E402
import raes  # noqa: E402
import raes_env_packs  # noqa: E402
import structural_family_adapter as adapter  # noqa: E402
import yaml  # noqa: E402
from aptl.backends.scenario_family import (  # noqa: E402
    FamilyTrialInput,
    admit_family_trial,
    require_family_capabilities,
)
from aptl.core.scenario_bundle import env_pack_bundle  # noqa: E402
from aptl.backends.raes import admit_raes_scenario  # noqa: E402
from aptl.backends.raes_start_model import (  # noqa: E402
    ScenarioAdmissionRun,
    ScenarioAdmissionSource,
)
from aptl.core.config import AptlConfig  # noqa: E402
from aptl.core.deployment._compose_runtime_materialization import (  # noqa: E402
    ComposeRuntimeMaterializationMixin,
)
from aptl.core.deployment._compose_node_generation import render_realization_compose  # noqa: E402
from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations  # noqa: E402
from aptl.backends.scenario_trial_archive import archive_family_trial  # noqa: E402
from aptl.core.runstore import LocalRunStore  # noqa: E402
from aptl.validation.scenario_verification import (  # noqa: E402
    ScenarioIdentity,
    VerificationContext,
    VerificationStatus,
)
from aptl.validation.scenario_verification_discovery import verify_scenario  # noqa: E402
from raes_env_packs import PackExperimentError, load_pack_experiments  # noqa: E402


def _load_helper():
    spec = importlib.util.spec_from_file_location("structural_family_fixture", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _refused(call, code: str) -> None:
    try:
        call()
    except ValueError as exc:
        assert str(exc) == code, exc
    else:
        raise AssertionError(f"{code} was not raised")


def _verify(trial) -> None:
    scenario = ScenarioIdentity(
        trial.target.family_id,
        trial.target.family_digest,
        "env-pack",
        trial.target.pack.pack_version,
    )
    report = verify_scenario(
        VerificationContext(
            trial.provenance.run_id,
            "attempt-1",
            scenario,
            trial.target.backend,
            trial=trial,
        )
    )
    assert report.status is VerificationStatus.PASSED


def _qualify_entries(bundle, experiment, plan) -> None:
    expected = []
    for entry_id, entry in plan.entries.items():
        trial = admit_family_trial(
            bundle,
            adapter.TARGET.backend,
            FamilyTrialInput(plan, entry_id, experiment.family),
        )
        assert trial.target == adapter.TARGET
        if MODE == "inconsistent":
            _refused(
                lambda: require_family_capabilities(trial),
                "family-package-versions-inconsistent",
            )
            assert adapter.SEEN == []
            return
        selections = require_family_capabilities(trial)
        assert {
            (item.distribution, item.distribution_version) for item in selections
        } == {("lilrae-structural-family-fixture", "1.0.0")}
        assert trial.participant_configuration_results == tuple(
            entry.participant_configurations
        )
        identity = trial.identity()
        assert (identity["plan_id"], identity["plan_entry_id"], identity["run_id"]) == (
            plan.plan_id,
            entry_id,
            entry.run_id,
        )
        _verify(trial)
        expected.append(
            {
                "plan_entry_id": entry_id,
                "sensor_present": "sensor-9" in trial.scenario.nodes,
                "configuration_digests": [
                    item.configuration_digest
                    for item in entry.participant_configurations
                ],
            }
        )
        unsupported = replace(trial.target.backend, profile="unsupported-profile")
        _refused(
            lambda: require_family_capabilities(
                replace(trial, target=replace(trial.target, backend=unsupported))
            ),
            "family-provider-missing",
        )
    assert adapter.SEEN == expected
    assert {item["sensor_present"] for item in expected} == {True, False}


def _reject_unsupported_factorial_profile(helper, work: Path) -> None:
    root = helper.build_pack(work / "unsupported", FIXTURE)
    spec_path = root / helper.SPEC
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec["factorial_design"]["profile"] = "factorial-treatments-v2"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    helper.write_content_manifest(root)
    try:
        load_pack_experiments(root)
    except PackExperimentError:
        return
    raise AssertionError("unsupported factorial profile was admitted")


def _realize_entries(bundle, experiment, plan) -> None:
    """Exercise installed admission, lowering and scoped startup on every entry."""

    states = []
    for entry_id, entry in plan.entries.items():
        admitted = admit_raes_scenario(
            bundle.root,
            AptlConfig(),
            ComposeRuntimeMaterializationMixin(),
            source=ScenarioAdmissionSource(bundle),
            run=ScenarioAdmissionRun(
                trial=FamilyTrialInput(plan, entry_id, experiment.family)
            ),
        )
        trial = admitted.bundle.trial
        assert trial.provenance.run_id == entry.run_id
        assert (
            admitted.execution_plan.provisioning.materialization_source.run_id
            == entry.run_id
        )
        assert admitted.execution_plan.provisioning.instantiation_id == entry_id
        nodes = {node.name: node for node in admitted.realization.nodes}
        assert set(nodes) == set(trial.scenario.nodes)
        present = "sensor-9" in nodes
        if present:
            assert [
                item.service_listener_id
                for item in nodes["sensor-9"].runtime.service_listeners
            ] == ["active"]
        spec = admitted.realization.deployment_spec(["lab"])
        document = render_realization_compose(spec)
        assert set(document["services"]) == set(trial.scenario.nodes)
        (content,) = spec.content
        assert content.inline_text == trial.scenario.content["logging-config"].text
        assert content.inline_text in {"loglevel notice\n", "loglevel debug\n"}
        errors = [item for item in admitted.execution_plan.diagnostics if item.is_error]
        if present:
            # This fixture deliberately has no native observer for the exact
            # runtime defaults in its selected listener inventory. Retain the
            # owner's refusal; rendering the graph does not prove observation.
            assert errors
            assert all(
                item.code
                in {
                    "realization.unsupported-exact-requirement",
                    "realization.authority-bound-unavailable",
                }
                for item in errors
            ), [(item.code, item.message) for item in errors]
        else:
            assert errors == [], [(item.code, item.message) for item in errors]
            assert admitted.runtime_materialization_failure is None
        operations = AdmittedRuntimeOperations(object(), spec.nodes)
        if not present:
            _refused(
                lambda: operations.container_restart("sensor-9"),
                "runtime-node-not-admitted",
            )
        store = LocalRunStore(bundle.root.parent / "trial-runs")
        archive_family_trial(store, trial)
        assert (
            store.get_run_path(entry.run_id) / "trial/instantiated-snapshot.json"
        ).read_bytes() == trial.snapshot
        states.append((present, content.inline_text))
    assert set(states) == {
        (present, mode)
        for present in (True, False)
        for mode in ("loglevel notice\n", "loglevel debug\n")
    }


def main() -> None:
    for module in (aptl, adapter):
        assert Path(module.__file__).is_relative_to(INSTALLED), module.__file__
    for module in (raes, raes_env_packs):
        assert not Path(module.__file__).is_relative_to(SOURCE_TREE), module.__file__
    helper = _load_helper()
    work = Path(tempfile.mkdtemp())
    source = helper.build_pack(work / "source", FIXTURE)
    bundle = env_pack_bundle(work / "staging", helper.PACK_NAME, source_pack=source)
    (experiment,) = load_pack_experiments(bundle.root)
    plan = helper.compile_plan(experiment, FIXTURE)
    _qualify_entries(bundle, experiment, plan)
    if MODE == "consistent":
        _realize_entries(bundle, experiment, plan)
    _reject_unsupported_factorial_profile(helper, work)
    # The public route needs no concrete RAES reference backend and no
    # LilRAE-owned experiment plan.
    assert "raes_backend_stubs" not in sys.modules
    assert "aptl.core.experiment.trial_plan" not in sys.modules


if __name__ == "__main__":
    main()
