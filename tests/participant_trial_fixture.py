"""Public RAE compiler fixture shared by publication and trial-start tests."""

import copy
from datetime import datetime, timedelta, timezone
import json
import yaml
from raes import Scenario
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.participant_control_context import control_context_asset_reference
from tests.participant_request_fixture import owner_fixture


def _installed_owner(
    owner, scenario_data, initial_scenario, executable, endpoint, assistant_turn_limit
):
    for node in scenario_data["nodes"].values():
        node.update(os_distribution="ubuntu", os_version="22.04", architecture="x86_64")
        node.pop("runtime", None)
    for alternative in scenario_data["variation_points"]["sensor-layout"][
        "alternatives"
    ].values():
        alternative.pop("inventory", None)
    import hashlib
    from aptl.core.participant_requests import ParticipantRequestOwner, RequestCatalog

    for name, payload in (
        ("brief-terse", b"trial preamble\n"),
        ("brief-rich", b"trial preamble\nselected playbook\n"),
    ):
        artifact = scenario_data["control_context_assets"][name]["content"]
        artifact["size_bytes"] = len(payload)
        artifact["checksum"]["value"] = hashlib.sha256(payload).hexdigest()
    data = owner.catalog.model_dump(mode="json")
    if assistant_turn_limit is not None:
        for profile in data["profiles"]:
            profile["assistant_turn_limit"] = {
                "state": "set",
                "value": assistant_turn_limit,
            }
    if endpoint is not None:
        for profile in data["profiles"]:
            profile["gateway_endpoint"] = endpoint
    data["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    catalog = RequestCatalog.model_validate_json(json.dumps(data))
    owner = ParticipantRequestOwner(
        catalog=catalog,
        context_domains={
            "brief": {
                f"control_context_assets.{name}": control_context_asset_reference(asset)
                for name, asset in initial_scenario.control_context_assets.items()
            }
        },
        scenario=initial_scenario,
    )
    return owner


def compiled_participants(
    tmp_path,
    provider="opencode",
    fixed=False,
    executable=None,
    endpoint=None,
    assistant_turn_limit=1,
    native=False,
):
    from raes import admit_scenario_family
    from raes.canonical import canonical_sdl_digest
    from raes_env_packs import load_pack_experiments, PackExperimentError
    from raes_contracts.contracts import AdmittedParticipantManifestReferenceModel
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from tests.structural_family_fixture import (
        FIXTURE,
        build_pack,
        write_content_manifest,
        _apparatus_context,
    )

    source = build_pack(tmp_path)
    scenario_path = source / "sdl" / "structural-fixture.sdl.yaml"
    scenario_data = yaml.safe_load(scenario_path.read_text())
    scenario_data["agents"]["reviewer"] = {"role": "blue"}
    owner, initial_scenario = owner_fixture(provider)
    if native:
        from tests.participant_runtime_trial_fixture import add_scenario

        add_scenario(scenario_data, owner.manifest.identity.name)
    if executable is not None:
        owner = _installed_owner(
            owner,
            scenario_data,
            initial_scenario,
            executable,
            endpoint,
            assistant_turn_limit,
        )
    scenario_path.write_text(yaml.safe_dump(scenario_data))
    scenario = Scenario.model_validate(scenario_data)
    from aptl.core.participant_requests import ParticipantRequestOwner

    owner = ParticipantRequestOwner(
        catalog=owner.catalog,
        context_domains={
            "brief": {
                f"control_context_assets.{name}": control_context_asset_reference(asset)
                for name, asset in scenario.control_context_assets.items()
            }
        },
        scenario=scenario,
    )
    family_digest = canonical_sdl_digest(
        admit_scenario_family(Scenario.model_validate(scenario_data))
    ).value
    manifest = owner.manifest
    spec_path = source / "experiments" / "structural-design.exp.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    design = spec["factorial_design"]
    for name in ("operator-model", "operator-prompt"):
        clone = name.replace("operator", "reviewer")
        spec["factors"][clone] = copy.deepcopy(spec["factors"][name])
        design["factor_ids"].append(clone)
        design["level_effects"][clone] = copy.deepcopy(design["level_effects"][name])
    design["condition_bound"] = 32
    for factor, levels in design["level_effects"].items():
        for i, effect in enumerate(levels.values()):
            for binding in list(effect.get("bindings", [])):
                target = binding["target"]
                target.update(
                    implementation_name=manifest.identity.name,
                    implementation_version=manifest.identity.version,
                )
                if factor.startswith("reviewer"):
                    target["participant_address"] = "agents.reviewer"
                binding["owner"] = manifest.configuration_registry.owner.model_dump(
                    mode="json"
                )
                if factor.endswith("model"):
                    target["target_id"] = owner.model_target
                    profile = owner.catalog.profiles[i]
                    binding["value"]["value"] = profile.model
                    for key, value in (
                        ("request.profile", profile.reference),
                        ("request.profile_digest", profile.digest),
                    ):
                        added = copy.deepcopy(binding)
                        added["target"]["target_id"] = key
                        added["value"]["value"] = value
                        effect["bindings"].append(added)
            # Shared scenario effects belong to the existing operator factor.
            if factor.startswith("reviewer"):
                effect.pop("selections", None)
            for selection in effect.get("selections", []):
                selection["scenario_family_digest"] = family_digest
    if fixed:
        for factor, levels in design["level_effects"].items():
            key = next(iter(levels))
            design["level_effects"][factor] = {key: levels[key]}
            spec["factors"][factor]["levels"] = [key]
        design["condition_bound"] = 1
    spec_path.write_text(yaml.safe_dump(spec))
    write_content_manifest(source)
    try:
        (experiment,) = load_pack_experiments(source)
    except PackExperimentError as exc:
        raise AssertionError(exc.result) from None
    context = _apparatus_context(experiment, FIXTURE)
    if executable is not None:
        context["execution_authority"] = context["execution_authority"].model_copy(
            update={"attempt_timeout_seconds": 90}
        )
    tail = (manifest.identity.name, manifest.identity.version, manifest.schema_version)
    refs = [
        AdmittedParticipantManifestReferenceModel(
            participant_address=address,
            implementation_name=tail[0],
            implementation_version=tail[1],
            manifest_version=tail[2],
            manifest_digest=canonical_contract_digest(manifest),
        )
        for address in ("agents.operator", "agents.reviewer")
    ]
    context["apparatus"] = context["apparatus"].model_copy(
        update={"participant_manifest_refs": refs}
    )
    context["participant_manifests"] = {
        (ref.participant_address, *tail): manifest for ref in refs
    }
    authority = manifest.configuration_registry.owner
    context["participant_configuration_validators"] = {
        (authority.validator_id, authority.validator_version): owner
    }
    if native:
        from tests.participant_runtime_trial_fixture import add_context

        add_context(context, owner)
    compilation = experiment.compilation_request(**context)
    compiled = compile_admitted_trial_plan(compilation)
    assert compiled.plan is not None, [
        (d.code, d.message) for d in compiled.diagnostics
    ]
    return compiled, compilation, owner


def realized_participants(compiled, compilation, owner, *, index=0, now=None):
    from raes_contracts.trial_unit import TrialUnitRequest
    from raes_processor.trial_realization import (
        TrialRealizationInputs,
        realize_admitted_trial_entry,
    )
    from raes_runtime.runtime_trial_decisions import TrialAttemptDecision

    inputs = TrialRealizationInputs(
        plan=compiled.plan,
        family=compilation.family,
        experiment=compilation.experiment,
        task=compilation.task,
        capture_specs=compilation.capture_specs,
        apparatus_manifests=compilation.apparatus_manifests,
        realization_envelope=compilation.realization_envelope,
        backend_key=next(
            k for k in compilation.apparatus_manifests if k[0] == "backend"
        ),
        participant_manifests=compilation.participant_manifests,
    )
    entry = list(compiled.plan.entries.values())[index]
    realized = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=entry.plan_entry_id
    )
    request = TrialUnitRequest(
        plan=compiled.plan,
        plan_entry_id=entry.plan_entry_id,
        execution_attempt_id=f"attempt-{index}",
        instantiated_sdl_digest=realized.snapshot_digest,
        provisioning_plan=realized.provisioning_plan,
        orchestration_plan=realized.orchestration_plan,
        evaluation_plan=realized.evaluation_plan,
    )
    now = now or datetime(2026, 11, 3, tzinfo=timezone.utc)
    attempt = TrialAttemptDecision(
        experiment_id="experiment-fixture",
        plan_entry_id=entry.plan_entry_id,
        run_id=entry.run_id,
        execution_attempt_id=request.execution_attempt_id,
        attempt=1,
        started_at=now.isoformat(),
        deadline=(
            now + timedelta(seconds=request.execution_controls.attempt_timeout_seconds)
        ).isoformat(),
    )
    contents = {}
    for result in request.participant_configurations:
        selected = next(
            v.value.value
            for v in result.configuration.values
            if v.target_id == "context.brief"
        )
        contents[result.participant_address] = {
            "brief": b"trial preamble\n"
            if selected.endswith("brief-terse")
            else b"trial preamble\nselected playbook\n"
        }
    return (
        request,
        attempt,
        realized.instantiated,
        compilation.experiment,
        owner,
        contents,
        now,
    )
