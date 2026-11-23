"""Native trial offers and scenario semantics for the installed runtime path."""

from dataclasses import replace
import copy
import json

from aptl.core.trial_participants import PendingTrialParticipant
from tests.test_lilrae_concurrent_participants import bindings


def add_scenario(payload, manifest_ref):
    from tests.lilrae_concurrent_fixture import scenario

    native = json.loads(
        scenario()
        .model_dump_json()
        .replace('"red"', '"operator"')
        .replace('"blue"', '"reviewer"')
    )
    native["entities"]["operator"]["role"] = "red"
    native["entities"]["reviewer"]["role"] = "blue"
    for section in (
        "entities",
        "agents",
        "action_contracts",
        "observation_boundaries",
        "objectives",
        "time_domains",
        "clocks",
        "time_progression_policies",
        "temporal_constraints",
        "propositions",
        "assertions",
        "behavior_specifications",
    ):
        payload[section] = native[section]
    behavior = payload["behavior_specifications"]["duel"]
    behavior["participant_refs"] = ["operator", "reviewer"]
    behavior["participant_role_refs"] = []
    native_ref = "participant-implementation-manifests." + manifest_ref
    behavior["realization_profile_ref"] = native_ref
    behavior["autonomous_execution"]["participant_implementation_ref"] = native_ref
    node = copy.deepcopy(payload["nodes"]["gateway"])
    node["services"] = [{"name": "http", "port": 8080, "protocol": "tcp"}]
    payload["nodes"]["target"] = node
    payload["infrastructure"]["target"] = {"count": 1}


def native_bindings(results, manifest, *, timeout_seconds=90):
    result = []
    for template, configuration in zip(
        bindings({"red": lambda *a: "", "blue": lambda *a: ""}), results, strict=True
    ):
        name = configuration.participant_address.removeprefix("agents.")
        selection = template.implementation_selection.model_copy(
            update={
                "participant_address": "participant.behavior." + name,
                "implementation_identity": manifest.identity,
                "manifest_ref": "participant-implementation-manifests."
                + configuration.manifest_ref,
                "manifest_digest": configuration.manifest_digest,
                "configuration_digest": configuration.configuration_digest,
                "configuration_ref": "configuration:"
                + configuration.participant_address,
            }
        )
        result.append(
            replace(
                template,
                implementation_manifest=manifest,
                implementation_selection=selection,
                observation_boundary_address="participant.observation-boundary.operator",
                executor=PendingTrialParticipant(configuration, timeout_seconds),
                execution_binding=replace(
                    template.execution_binding,
                    action_contract_address="participant.action-contract.operator",
                    participant_implementation_ref=selection.manifest_ref,
                    timeout_seconds=timeout_seconds,
                ),
            )
        )
    return tuple(result)


def add_context(context, owner):
    from aptl.backends.raes_manifest import create_aptl_manifest
    from raes_backend_protocols.manifest import backend_manifest_v2_model
    from tests.participant_request_fixture import realize

    initial = [
        realize(owner, participant=a).model_copy(
            update={"manifest_ref": owner.manifest.identity.name}
        )
        for a in ("agents.operator", "agents.reviewer")
    ]
    installed = native_bindings(initial, owner.manifest)
    native = backend_manifest_v2_model(
        create_aptl_manifest(autonomous_bindings=installed)
    )
    key = next(k for k in context["apparatus_manifests"] if k[0] == "backend")
    backend = context["apparatus_manifests"][key]
    data = backend.model_dump(mode="json")
    for capability in ("participant_runtime", "time"):
        data["capabilities"][capability] = getattr(
            native.capabilities, capability
        ).model_dump(mode="json")
    data["supported_contract_versions"] = sorted(
        set(data["supported_contract_versions"])
        | set(native.supported_contract_versions)
        - {"backend-runtime-descendants-v1", "backend-materialization-attestation-v1"}
    )
    data["realization_support"][0]["observation_capabilities"]["compute-substrate"] = {
        "verification_scope": "presence",
        "observation_strength": "guest-observed",
    }
    data["capabilities"]["cleanup"]["supported_verification_methods"] = [
        "native-absence"
    ]
    backend = type(backend).model_validate(data)
    context["apparatus_manifests"][key] = backend
    from tests.structural_family_fixture import _manifest_ref
    from raes_contracts.contracts import ExperimentBackendReferenceModel

    context["apparatus"] = context["apparatus"].model_copy(
        update={
            "manifest_refs": [
                _manifest_ref(backend, "backend", ExperimentBackendReferenceModel)
                if ref.subject_ref.ref_kind == "backend"
                else ref
                for ref in context["apparatus"].manifest_refs
            ]
        }
    )
    authority = context["execution_authority"].model_dump(mode="json")
    authority["cleanup"]["clean_state"]["verification_probe_refs"] = [
        "native-absence:range"
    ]
    authority["cleanup"]["cleanup_obligations"]["destroy"][
        "verification_probe_refs"
    ] = ["native-absence:range"]
    context["execution_authority"] = type(
        context["execution_authority"]
    ).model_validate(authority)
