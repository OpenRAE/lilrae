"""Small authored scenario and installed implementation for runtime tests."""

from raes import parse_sdl
from raes_contracts.contracts import (
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.canonical import canonical_contract_digest
import yaml


def scenario(*, attempts=1):
    payload = {
        "name": "lilrae-concurrent-participants",
        "nodes": {
            "target": {
                "type": "compute",
                "services": [{"name": "http", "port": 8080, "protocol": "tcp"}],
            }
        },
        "infrastructure": {"target": {"count": 1}},
        "entities": {},
        "agents": {},
        "action_contracts": {},
        "observation_boundaries": {},
        "behavior_specifications": {},
        "objectives": {},
        "propositions": {
            "target-present": {
                "description": "Target is a compute node",
                "subjects": ["nodes.target"],
                "basis": "declared_state",
                "quantifier": "all",
                "predicate": {
                    "kind": "string",
                    "property": "type",
                    "semantic_ref": "urn:lilrae:test:node-type",
                    "operator": "equals",
                    "expected": "compute",
                },
            }
        },
        "assertions": {
            "target-present": {
                "proposition": "target-present",
                "role": "postcondition",
                "polarity": "positive",
            }
        },
        "time_domains": {
            "trial": {
                "kind": "simulated",
                "tick_period_seconds": {"numerator": 1, "denominator": 1},
                "epoch": "scenario_start",
                "visibility": "participant_visible",
            }
        },
        "clocks": {
            "trial": {
                "time_domain_ref": "trial",
                "authority_kind": "runtime",
                "authority_ref": "runtime.time-coordinator",
                "monotonicity": "non_decreasing",
                "supports_pause": True,
                "supports_reset": False,
            }
        },
        "time_progression_policies": {
            "trial": {
                "clock_ref": "trial",
                "advancement_mode": "stepped",
                "synchronization_mode": "barrier",
                "step_ticks": 1,
                "reset_behavior": "unsupported",
                "replay_behavior": "unsupported",
            }
        },
        "temporal_constraints": {
            "turn": {
                "constraint_kind": "cadence",
                "clock_ref": "trial",
                "subject_refs": ["nodes.target"],
                "start": {"tick": 0},
                "cadence_ticks": 1,
            }
        },
    }
    for role in ("red", "blue"):
        payload["entities"][role] = {"role": role}
        payload["objectives"][role] = {
            "assigned_participant": role,
            "actions": [role],
            "targets": ["nodes.target.services.http"],
            "success": {"assertions": ["target-present"]},
        }
        payload["agents"][role] = {
            "affiliations": [role],
            "actions": [role],
            "observation_boundaries": [role],
            "operating_scope": ["nodes.target.services.http"],
        }
        payload["observation_boundaries"][role] = {
            "projection_basis": "Own bounded terminal output",
            "observable_refs": ["nodes.target.services.http"],
        }
        payload["action_contracts"][role] = {
            "semantic_version": "1.0.0",
            "lifecycle_state": "active",
            "behavioral_granularity": "atomic",
            "procedure_basis": "Bounded participant invocation",
            "realization_profile": "backend-declared",
            "fidelity_claim": "Terminal outcome only",
            "preconditions": [
                {
                    "precondition_id": "target",
                    "precondition_class": "target",
                    "description": "Target exists",
                    "support_refs": ["nodes.target.services.http"],
                }
            ],
            "effects": [
                {
                    "effect_id": "observation",
                    "effect_class": "observation_effect",
                    "description": "Terminal observation",
                    "target_refs": ["nodes.target.services.http"],
                }
            ],
            "state_transition_effects": ["Participant observation recorded"],
            "observation_expectations": ["Terminal observation"],
            "evidence_expectations": ["Participant history"],
            "failure_classes": ["backend_error", "timeout", "authority_denied"],
            "interactions": [
                {
                    "interaction_class": "shared_state_change",
                    "target": "nodes.target.services.http",
                    "rationale": "Independent observation",
                    "shared_state_refs": ["nodes.target.services.http"],
                    "commutative": True,
                }
            ],
        }
        payload["behavior_specifications"][role] = {
            "semantic_version": "1.0.0",
            "lifecycle_state": "active",
            "participant_refs": [role],
            "participant_role_refs": [role],
            "action_contract_refs": [role],
            "observation_boundary_refs": [role],
            "behavior_mode": "autonomous",
            "realization_profile_ref": "participant-implementation-manifests.fixture.v1",
            "backend_feature_support_refs": [
                "action_contracts",
                "autonomous_execution",
                "behavior_history",
                "observation_boundaries",
                "temporal_contracts",
            ],
            "evidence_contract_refs": ["participant-behavior-history-event-stream-v1"],
            "extension_policy": "governed-extension",
            "autonomous_execution": {
                "participant_implementation_ref": "participant-implementation-manifests.fixture.v1",
                "clock_ref": "trial",
                "progression_policy_ref": "trial",
                "temporal_constraint_refs": ["turn"],
                "action_order": [role],
                "observation_boundary_ref": role,
                "selection_strategy": "ordered_cycle",
                "max_action_attempts": 1,
                "max_in_flight": 2,
                "failure_policy": "continue",
                "evaluation_authority": {"mode": "declared", "objective_refs": [role]},
            },
        }
    # RAES 7 batches participants within one authored execution policy.
    shared = payload["behavior_specifications"]["red"]
    shared["autonomous_execution"]["max_action_attempts"] = attempts
    shared["participant_refs"] = ["red", "blue"]
    shared["participant_role_refs"] = ["red", "blue"]
    shared["autonomous_execution"]["evaluation_authority"]["objective_refs"] = [
        "red",
        "blue",
    ]
    payload["behavior_specifications"] = {"duel": shared}
    payload["agents"]["blue"]["actions"] = ["red"]
    payload["agents"]["blue"]["observation_boundaries"] = ["red"]
    payload["objectives"]["blue"]["actions"] = ["red"]
    payload["action_contracts"].pop("blue")
    payload["observation_boundaries"].pop("blue")
    for section in (
        "time_domains",
        "clocks",
        "time_progression_policies",
        "temporal_constraints",
    ):
        for item in payload[section].values():
            item["description"] = "Bounded shared trial time"
    for boundary in payload["observation_boundaries"].values():
        boundary.update(
            redaction_policy="No credentials", latency_profile="Terminal observation"
        )
    return parse_sdl(yaml.safe_dump(payload))


def apparatus(role):
    contracts = [
        "participant-implementation-manifest-v1",
        "participant-implementation-provenance-v1",
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
    ]
    manifest = ParticipantImplementationManifestModel.model_validate(
        {
            "identity": {"name": "fixture", "version": "1.0.0"},
            "implementation_kind": "agent",
            "supported_contract_versions": contracts,
            "compatibility": {"participant_runtimes": ["aptl-participant-runtime"]},
            "concept_bindings": [
                {"scope": scope, "family": family}
                for scope, family in (
                    ("implementation_kind", "apparatus-declarations"),
                    (
                        "capabilities.supported_participant_contracts",
                        "apparatus-declarations",
                    ),
                    (
                        "capabilities.supported_decision_surface_modes",
                        "apparatus-declarations",
                    ),
                    (
                        "capabilities.tool_affordance_expectations",
                        "tools-and-artifacts",
                    ),
                    ("capabilities.exposure_policy_kinds", "provenance-and-evidence"),
                )
            ],
            "capabilities": {
                "supported_participant_contracts": contracts[2:],
                "supported_decision_surface_modes": ["autonomous"],
                "tool_affordance_expectations": ["http-api"],
                "exposure_policy_kinds": ["observation-stream"],
            },
        }
    )
    selection = ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": f"participant.behavior.{role}",
            "implementation_identity": manifest.identity,
            "manifest_ref": "participant-implementation-manifests.fixture.v1",
            "manifest_digest": canonical_contract_digest(manifest),
            "selected_decision_surface_mode": "autonomous",
            "participant_contract_versions": contracts[2:],
            "exposure_policy": {
                "policy_id": role,
                "policy_version": "1.0.0",
                "policy_digest": "sha256:" + "2" * 64,
                "exposure_policy_kinds": ["observation-stream"],
                "disclosed_refs": ["nodes.target.services.http"],
                "withheld_refs": [],
                "tool_affordance_refs": [],
                "visibility_scope_refs": [f"participants.{role}.visible"],
            },
        }
    )
    return manifest, selection
