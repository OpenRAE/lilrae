"""Structural factorial family trials on the released RAES tuple (#1465).

A third-party pack declares a crossed design over a participant model, a
participant control-context prompt and a structural sensor-presence factor.
Public env-packs and RAES APIs load and compile it; LilRAE admits each sealed
entry through its public family trial and retains the entry's selections.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from raes_env_packs import (
    PackExperimentError,
    load_pack_experiments,
    resolve_pack_artifact,
    validate_pack_content_manifest,
)

from aptl.backends.identity import (
    APTL_RAES_TARGET_NAME,
    APTL_RAES_TARGET_PROFILE,
    APTL_RAES_TARGET_VERSION,
    BackendIdentity,
)
from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
from aptl.core.scenario_bundle import env_pack_bundle
from tests.structural_family_fixture import (
    PACK_NAME,
    SPEC,
    build_pack,
    compile_plan,
    write_content_manifest,
)

BACKEND = BackendIdentity(
    APTL_RAES_TARGET_NAME,
    APTL_RAES_TARGET_VERSION,
    APTL_RAES_TARGET_PROFILE,
    provider="docker",
    transport="docker",
)
MODELS = {"lite": "small-model", "full": "large-model"}


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    source = build_pack(tmp_path_factory.mktemp("source"))
    bundle = env_pack_bundle(
        tmp_path_factory.mktemp("staging"), PACK_NAME, source_pack=source
    )
    (experiment,) = load_pack_experiments(bundle.root)
    return bundle, experiment, compile_plan(experiment)


def _levels(experiment, entry) -> dict[str, str]:
    allocation = experiment.experiment.run_plan.allocation
    return allocation.condition_assignments[entry.coordinate.condition_id].factor_levels


def test_every_entry_retains_its_sealed_selections_and_identity(compiled):
    bundle, experiment, plan = compiled
    assert len(plan.entries) == 8

    for entry_id, entry in plan.entries.items():
        trial = admit_family_trial(
            bundle, BACKEND, FamilyTrialInput(plan, entry_id, experiment.family)
        )
        levels = _levels(experiment, entry)
        (configuration,) = trial.participant_configuration_results
        values = {item.target_id: item for item in configuration.configuration.values}

        assert trial.participant_configuration_results == tuple(
            entry.participant_configurations
        )
        assert values["engine.model"].value.value == MODELS[levels["operator-model"]]
        assert values[
            "context.brief"
        ].control_context_selection.asset_ref.asset_version == (
            f"brief-{levels['operator-prompt']}"
        )
        assert ("sensor-9" in trial.scenario.nodes) is (levels["sensor"] == "present")
        assert {
            key: trial.identity()[key]
            for key in ("plan_id", "plan_entry_id", "entry_digest", "run_id")
        } == {
            "plan_id": plan.plan_id,
            "plan_entry_id": entry_id,
            "entry_digest": entry.entry_digest,
            "run_id": entry.run_id,
        }


def test_pack_artifact_references_bind_their_verified_bytes(compiled):
    bundle, experiment, _plan = compiled
    manifest = validate_pack_content_manifest(bundle.root)
    entry_ids = {
        entry.uri.removeprefix("raes-environment-pack:/"): entry_id
        for entry_id, entry in manifest.artifacts.items()
    }
    references = [*experiment.task.artifact_refs]
    for capture in experiment.capture_specs.values():
        references.extend(capture.artifact_refs)
    assert len(references) == 2

    for reference in references:
        resolved = resolve_pack_artifact(bundle.root, entry_ids[reference.uri])
        assert (hashlib.sha256(resolved.data).hexdigest(), len(resolved.data)) == (
            reference.checksum.value,
            reference.size_bytes,
        )


def test_trial_evidence_names_configuration_digests_without_values(compiled):
    bundle, experiment, plan = compiled
    entry_id, entry = next(iter(plan.entries.items()))
    trial = admit_family_trial(
        bundle, BACKEND, FamilyTrialInput(plan, entry_id, experiment.family)
    )

    evidence = trial.evidence()

    assert evidence["participant_configurations"] == [
        {
            "participant_address": "agents.operator",
            "manifest_digest": entry.participant_configurations[0].manifest_digest,
            "configuration_digest": entry.participant_configurations[
                0
            ].configuration_digest,
        }
    ]
    assert not {"small-model", "large-model", "brief-terse", "brief-rich"} & set(
        json.dumps(evidence).split('"')
    )


def test_an_altered_sealed_configuration_is_rejected(compiled):
    bundle, experiment, plan = compiled
    entry_id = next(iter(plan.entries))
    altered = plan.model_copy(deep=True)
    value = altered.entries[entry_id].participant_configurations[0].configuration.values
    model = next(item for item in value if item.target_id == "engine.model")
    model.value.value = "substituted-model"

    with pytest.raises(ValueError, match="^family-trial-invalid$"):
        admit_family_trial(
            bundle, BACKEND, FamilyTrialInput(altered, entry_id, experiment.family)
        )


def test_an_unsupported_factorial_profile_is_rejected_before_compilation(tmp_path):
    root = build_pack(tmp_path)
    spec_path = root / SPEC
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec["factorial_design"]["profile"] = "factorial-treatments-v2"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    write_content_manifest(root)

    with pytest.raises(PackExperimentError) as rejected:
        load_pack_experiments(Path(root))
    assert [item.code for item in rejected.value.result.diagnostics] == [
        "experiment.spec-invalid"
    ]


@pytest.mark.integration
def test_installed_release_tuple_qualifies_a_third_party_structural_family(
    tmp_path, compiled
):
    """Build and install the host and adapter wheels, then qualify outside the tree.

    The consistent installation admits every entry and retains its selections.
    An adapter that declares a host release the installation lacks stops at
    family qualification.
    """

    import shutil
    import subprocess
    import sys

    from aptl.backends.scenario_family import encode_family_target

    bundle, experiment, plan = compiled
    trial = admit_family_trial(
        bundle,
        BACKEND,
        FamilyTrialInput(plan, next(iter(plan.entries)), experiment.family),
    )
    repo = Path(__file__).resolve().parents[1]
    fixture = repo / "tests/fixtures/structural_family"

    def run(argv: list[str]) -> None:
        result = subprocess.run(
            argv, cwd=tmp_path, capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def wheel(project: Path, output: str) -> str:
        run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(tmp_path / output),
                str(project),
            ]
        )
        return str(next((tmp_path / output).glob("*.whl")))

    host = wheel(repo, "host-wheel")
    for mode, host_requirement in (
        ("consistent", "lilrae"),
        ("inconsistent", "lilrae>=999"),
    ):
        adapter = tmp_path / mode / "adapter"
        shutil.copytree(fixture / "adapter", adapter)
        metadata = adapter / "pyproject.toml"
        metadata.write_text(
            metadata.read_text().replace('["lilrae",', f'["{host_requirement}",')
        )
        (adapter / "structural_family_adapter/qualification.json").write_text(
            encode_family_target(trial.target)
        )
        installed = tmp_path / mode / "installed"
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--target",
                str(installed),
                host,
                wheel(adapter, f"{mode}-wheel"),
            ]
        )
        run(
            [
                sys.executable,
                "-I",
                str(fixture / "qualify_installed.py"),
                str(installed),
                str(repo / "tests/structural_family_fixture.py"),
                str(fixture),
                str(repo / "src"),
                mode,
            ]
        )
