"""Public owner admission, exact prompt pins and safe immutable publication."""

import json
import copy
import subprocess
import sys

import pytest
import yaml
from raes import Scenario
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import ParticipantConfigurationResultModel


from tests.participant_request_fixture import owner_fixture, profile_data, realize


@pytest.mark.parametrize("provider", ["claude", "codex", "opencode"])
def test_each_provider_publishes_and_validates_fixed_and_changed_choices(provider):
    owner, scenario = owner_fixture(provider)
    first = realize(owner)
    second = realize(owner.for_scenario(scenario), profile_index=1, prompt="brief-rich")
    assert first.configuration_digest != second.configuration_digest
    assert first.manifest_digest == second.manifest_digest
    restored = ParticipantConfigurationResultModel.model_validate_json(
        second.model_dump_json()
    )
    selected = next(
        v for v in restored.configuration.values if v.target_id == "context.brief"
    )
    assert selected.control_context_selection.asset_ref.asset_version == "brief-rich"
    assert owner.manifest.constraints["served_identity"] == "unattested"
    assert owner.manifest.constraints["seed_determinism"] == "not-guaranteed"
    assert "request.profile" in owner.manifest.configuration_registry.targets


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "openrouter/unknown"},
        {"request.profile": "unknown@v1"},
        {"request.profile_digest": "sha256:" + "0" * 64},
        {"temperature": 0.1},
        {"context.brief": "control_context_assets.unknown"},
    ],
)
def test_unknown_or_changed_selection_cannot_be_admitted(changes):
    owner, _ = owner_fixture()
    with pytest.raises(ValueError):
        realize(owner, **changes)


def test_profile_content_is_part_of_both_manifest_and_configuration_identity():
    first, _ = owner_fixture()
    changed, _ = owner_fixture(changed_profile=True)
    old = realize(first)
    new = realize(changed)
    assert old.manifest_digest != new.manifest_digest
    assert old.configuration_digest != new.configuration_digest
    with pytest.raises(ValueError):
        realize(changed, **{"request.profile_digest": first.catalog.profiles[0].digest})


@pytest.mark.parametrize(
    "field,value",
    [
        ("no_fallback", False),
        ("temperature", {"state": "unsupported", "value": 0.2}),
        ("seed", {"state": "set", "value": 7}),
        ("output_limit", {"state": "set", "value": True}),
        ("arbitrary_options", {}),
    ],
)
def test_request_schema_rejects_unsupported_or_ambiguous_controls(field, value):
    from aptl.core.participant_requests import RequestCatalog

    data = profile_data()
    data[field] = value
    with pytest.raises(ValueError):
        RequestCatalog(
            provider="opencode",
            implementation_version="1.0.0",
            build_version="1.19.5",
            executable_sha256="a" * 64,
            profiles=(data,),
        )


def test_published_manifest_configuration_and_usage_survive_create_once_storage(
    tmp_path,
):
    from aptl.core.runstore import LocalRunStore

    owner, _ = owner_fixture()
    store = LocalRunStore(tmp_path)
    store.create_run("trial")
    for name, payload in [
        ("manifest", owner.manifest.model_dump(mode="json")),
        ("configuration", realize(owner).model_dump(mode="json")),
        ("usage", {"input_tokens": 12, "output_tokens": 0}),
    ]:
        path = store.create_run_json_once("trial", f"{name}.json", payload)
        assert json.loads(path.read_bytes()) == payload


@pytest.mark.parametrize("provider", ["claude", "codex", "opencode"])
def test_request_route_and_reasoning_domains_are_implementation_owned(provider):
    from aptl.core.participant_requests import RequestCatalog

    data = profile_data(provider)
    for changes in [
        {"gateway_endpoint": "https://unapproved.invalid/v1"},
        {"gateway": "openai" if provider != "codex" else "anthropic"},
        {
            "reasoning_mode": "effort",
            "reasoning_effort": {"state": "set", "value": "invented"},
            "reasoning_budget": {"state": "omit", "value": None},
        },
    ]:
        with pytest.raises(ValueError):
            RequestCatalog(
                provider=provider,
                implementation_version="1.0.0",
                build_version="1.19.5",
                executable_sha256="a" * 64,
                profiles=({**data, **changes},),
            )


@pytest.mark.parametrize("provider", ["claude", "codex", "opencode"])
@pytest.mark.parametrize("fixed", [False, True])
def test_public_raes_compiler_seals_independent_participant_choices(
    tmp_path, provider, fixed
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
    scenario_path.write_text(yaml.safe_dump(scenario_data))
    owner, _ = owner_fixture(provider)
    owner = owner.for_scenario(Scenario.model_validate(scenario_data))
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
    compiled = compile_admitted_trial_plan(experiment.compilation_request(**context))
    assert compiled.plan is not None, [
        (d.code, d.message) for d in compiled.diagnostics
    ]
    assert len(compiled.plan.entries) == (1 if fixed else 32)
    pairs = set()
    for entry in compiled.plan.entries.values():
        assert len(entry.participant_configurations) == 2
        pairs.add(
            tuple(
                result.configuration_digest
                for result in entry.participant_configurations
            )
        )
    assert len(pairs) == (1 if fixed else 16)


@pytest.mark.parametrize(
    "provider,effort", [("claude", "ultracode"), ("codex", "max"), ("codex", "ultra")]
)
def test_effort_names_outside_native_vocabulary_are_rejected(provider, effort):
    from aptl.core.participant_requests import RequestCatalog

    owner, _ = owner_fixture(provider)
    data = owner.catalog.model_dump(mode="json")
    data["profiles"][0].update(
        reasoning_mode="effort",
        reasoning_effort={"state": "set", "value": effort},
        reasoning_budget={"state": "omit", "value": None},
    )
    serialized = json.dumps(data)
    with pytest.raises(ValueError, match="effort is unsupported"):
        RequestCatalog.model_validate_json(serialized)


@pytest.mark.parametrize(
    "provider,mode", [("claude", "effort"), ("codex", "effort"), ("opencode", "effort")]
)
def test_reviewed_profiles_keep_reasoning_and_sampling_dispositions(provider, mode):
    from aptl.core.participant_requests import RequestCatalog

    data = profile_data(provider)
    data.update(
        reasoning_mode=mode,
        reasoning_effort={
            "state": "set" if mode == "effort" else "omit",
            "value": "high" if mode == "effort" else None,
        },
        reasoning_budget={
            "state": "set" if mode == "budget" else "omit",
            "value": 1024 if mode == "budget" else None,
        },
    )
    if provider == "opencode":
        data["temperature"] = {"state": "locked", "value": 0.2}
        data["top_p"] = {"state": "omit", "value": None}
        data["limit_scope"] = "combined-generation"
    catalog = RequestCatalog(
        provider=provider,
        implementation_version="1.0.0",
        build_version="1.19.5",
        executable_sha256="a" * 64,
        profiles=(data,),
    )
    assert catalog.profiles[0].reasoning_mode == mode
    assert catalog.profiles[0].seed.state == "unsupported"


def test_profile_omissions_and_integer_limits_are_strict():
    from aptl.core.participant_requests import RequestCatalog

    for field, value in [
        ("temperature", float("nan")),
        ("top_p", float("inf")),
        ("output_limit", 0),
        ("output_limit", "128"),
    ]:
        data = profile_data()
        data[field] = {"state": "set", "value": value}
        with pytest.raises(ValueError):
            RequestCatalog(
                provider="opencode",
                implementation_version="1.0.0",
                build_version="1.19.5",
                executable_sha256="a" * 64,
                profiles=(data,),
            )


def test_opencode_reasoning_budget_must_fit_combined_generation_limit():
    from aptl.core.participant_requests import RequestCatalog

    data = profile_data()
    data.update(
        reasoning_mode="budget",
        reasoning_effort={"state": "omit", "value": None},
        reasoning_budget={"state": "set", "value": 1024},
        limit_scope="combined-generation",
    )
    with pytest.raises(ValueError, match="budget"):
        RequestCatalog(
            provider="opencode",
            implementation_version="1.0.0",
            build_version="1.19.5",
            executable_sha256="a" * 64,
            profiles=(data,),
        )


@pytest.mark.parametrize(
    "provider,mode", [("claude", "budget"), ("claude", "disabled"), ("codex", "budget")]
)
def test_unqualified_reasoning_modes_are_rejected_before_dispatch(provider, mode):
    from aptl.core.participant_requests import RequestCatalog

    owner, _ = owner_fixture(provider)
    data = owner.catalog.model_dump(mode="json")
    profile = data["profiles"][0]
    profile.update(
        reasoning_mode=mode,
        reasoning_effort={"state": "omit", "value": None},
        reasoning_budget={
            "state": "set" if mode == "budget" else "omit",
            "value": 2048 if mode == "budget" else None,
        },
    )
    serialized = json.dumps(data)
    with pytest.raises(ValueError, match="unsupported"):
        RequestCatalog.model_validate_json(serialized)


@pytest.mark.integration
def test_public_schemas_manifests_and_validators_are_installed(tmp_path):
    from tests.opencode_fixture import install_wheel

    installed = install_wheel(tmp_path)
    owner, scenario = owner_fixture()
    payload = {
        "catalog": owner.catalog.model_dump(mode="json"),
        "scenario": scenario.model_dump(mode="json"),
        "result": realize(owner).model_dump(mode="json"),
    }
    script = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from aptl.core.participant_requests import ParticipantRequestOwner, RequestCatalog
from raes import Scenario
from raes_contracts.contracts import ParticipantConfigurationResultModel, ParticipantImplementationManifestModel
from raes_contracts.participant_control_context import control_context_asset_reference
import aptl.core.participant_requests as public
assert Path(public.__file__).is_relative_to(Path(sys.argv[1]))
data = json.loads(sys.stdin.read())
catalog = RequestCatalog.model_validate_json(json.dumps(data['catalog']))
scenario = Scenario.model_validate(data['scenario'])
domains = {'brief': {f'control_context_assets.{name}': control_context_asset_reference(asset) for name, asset in scenario.control_context_assets.items()}}
owner = ParticipantRequestOwner(catalog=catalog, context_domains=domains, scenario=scenario)
result = ParticipantConfigurationResultModel.model_validate(data['result'])
owner.validate_and_normalize(result.configuration)
assert RequestCatalog.model_json_schema()['additionalProperties'] is False
assert ParticipantImplementationManifestModel.model_validate_json(owner.manifest.model_dump_json()) == owner.manifest
assert owner.manifest.constraints['served_identity'] == 'unattested'
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script, str(installed)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=tmp_path,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
