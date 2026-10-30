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
    _reject_unsupported_factorial_profile(helper, work)
    # The public route needs no concrete RAES reference backend and no
    # LilRAE-owned experiment plan.
    assert "raes_backend_stubs" not in sys.modules
    assert "aptl.core.experiment.trial_plan" not in sys.modules


if __name__ == "__main__":
    main()
