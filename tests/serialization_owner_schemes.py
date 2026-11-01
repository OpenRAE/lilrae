"""The owner schemes of the serialization vectors (#1555).

Each function calls one owner in ``src`` with a vector input and returns its
result in the form that ``test_serialization_vectors.py`` compares. An owner
here applies its own rule: a name, an identifier, a digest input, or a
document projection. The base schemes of that module cover the serializers
and the hash that the owners share.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aptl.appliance import guest_surfaces
from aptl.appliance.policy import write_full_techvault_boundary_policy
from aptl.appliance.seat import overlay_identity, readiness
from aptl.appliance.seat.access import (
    GuestAccessBundle,
    GuestAccessRequest,
    encode_guest_access_bundle,
    publish_guest_access_request,
)
from aptl.appliance.seat.models import SeatRecord
from aptl.appliance.seat.persistence import persist_seat_record, seat_state_path
from aptl.core import startup_reset_state
from aptl.core.appliance_boundary import ApplianceBoundaryPolicy, render_egress_proxy_policy
from aptl.core.appliance_boundary_observation import GuestBoundaryObservation
from aptl.core.archival.discovery_index import DiscoveryIndex, IndexEntry
from aptl.core.deployment import lilrae_docker_recording
from aptl.backends import lilrae_runtime_evidence
from aptl.backends.identity import BackendIdentity
from aptl.backends.scenario_family import QualifiedFamilyTarget, encode_family_target
from aptl.core.operator_group_state import persist_admitted_operator_groups
from aptl.core.scenario_bundle import PackIdentity
from aptl.validation.participant_qualification_evidence import (
    ParticipantQualificationReport,
    participant_qualification_attestation_payload,
)
from aptl_techvault.evidence import techvault as techvault_evidence
from aptl_techvault.evidence.techvault_readiness import SuricataRuleReadinessSource
from aptl_techvault.evidence import techvault_misp_readiness, techvault_readiness_probes, techvault_wazuh_agent_readiness
from aptl.appliance.seat import image_selection, image_trust
from aptl.appliance.seat.image import parse_seat_image_reference
from aptl.appliance.seat.observation import observation_id_for
from aptl.backends import raes_participant_actions
from aptl.backends._raes_participant_crossing import _delivery_crossing_policies
from aptl.backends._raes_participant_evidence import _ParticipantDeliveryCollector
from aptl.backends._raes_participant_execution import _control_intent_fields
from aptl.backends.lilrae_apparatus_reporting import apparatus_node_name
from aptl.backends.raes import admit_raes_scenario
from aptl.backends.raes_participant_candidates import candidate_selections
from aptl.backends.raes_runtime_model_artifact import compiled_runtime_model_bytes, compiled_runtime_model_sha256
from aptl.backends.raes_participant_fixture_core import participant_episode_state_dir
from aptl.backends.raes_participant_support import binding_post_state_digest
from aptl.core.appliance_boundary_observation import HostBoundaryObservation
from aptl.core.certs import _cert_generator_project_name
from aptl.core.correlation.identity import stable_ref
from aptl.core.deployment._compose_artifact_paths import artifact_environment_file_path
from aptl.core.deployment._compose_environment import sourced_environment_file
from aptl.core.deployment._compose_ownership_override import write_compose_ownership_override
from aptl.core.config import AptlConfig
from aptl.core.evidence_bundle.limits import DEFAULT_LIMITS
from aptl.core.experiment.bindings import _apparatus_configuration
from aptl.core.experiment.capture_plan import admit_capture_demands
from aptl.core.evidence_bundle.projections.jsonl import JsonlProjection
from aptl.core.evidence_bundle.projections.registry import ProjectionContext
from aptl.core.execution.assembly import write_lifecycle_evidence
from aptl.core.provenance.providers.apparatus import ApparatusManifestProvider
from aptl.core.provenance.providers.runtime_facts import RuntimeFactsProvider
from aptl.core.runstore import LocalRunStore
from aptl.core.snapshot_models import (
    ContainerSnapshot,
    NetworkSnapshot,
    RangeSnapshot,
    ServiceEndpoint,
    SoftwareVersions,
    SSHEndpoint,
    WazuhRulesSnapshot,
)
from aptl.core.deployment._compose_resource_ownership import WorkspaceOwnership
from aptl.core.deployment.lilrae_docker_recording import RecordingStore
from aptl.core.deployment import lilrae_native_evidence
from aptl.core.deployment._compose_resource_ownership import ResourceReceipt
from aptl.core.deployment.lilrae_native_evidence import _directory as native_evidence_directory
from aptl.core.experiment import trial_plan
from aptl.validation._live_gate_probes import _matched_alert_summary
from raes_contracts.contracts import ExperimentBindingDescriptorModel
from aptl.workbench.codex_agent import CodexManagedAgentAdapter
from aptl.workbench.dispatch import key_fingerprint
from aptl.workbench.process import AgentExecutionError
from aptl_techvault.database_access import _scram_verifier
from aptl_techvault.evidence.techvault_transcript import (
    TranscriptFrame,
    TranscriptSession,
    _transcript_chain,
    _transcript_result,
)


class Rejected(Exception):
    """An owner rejected a vector input at a named stage."""

    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


def _episode_state_dir(case_input: dict) -> dict[str, str]:
    return {"text": participant_episode_state_dir(case_input["participant_address"], case_input["episode_id"])}


def _binding_post_state_digest(case_input: dict) -> dict[str, str]:
    return {"text": binding_post_state_digest(SimpleNamespace(**case_input))}


def _cert_generator_name(case_input: dict) -> dict[str, str]:
    return {"text": _cert_generator_project_name(Path(case_input["project_dir"]))}


def _stable_ref(case_input: dict) -> dict[str, str]:
    try:
        return {"text": stable_ref(*case_input["parts"], domain=case_input["domain"].encode("utf-8"))}
    except ValueError as exc:
        raise Rejected("validate") from exc


def _compose_environment_names(case_input: dict) -> dict[str, object]:
    scenario = Path("/scenario")
    artifact = SimpleNamespace(address=case_input["artifact_address"])
    path = artifact_environment_file_path(scenario, artifact, case_input["service_name"])
    return {
        "value": {
            "sourced": sourced_environment_file(case_input["service_name"]),
            "generated": path.relative_to(scenario).as_posix(),
        }
    }


def _receipt_path(case_input: dict) -> dict[str, str]:
    return {"text": WorkspaceOwnership._receipt_path(case_input["kind"], case_input["native_id"]).as_posix()}


def _attempt_directories(case_input: dict) -> dict[str, object]:
    ownership = WorkspaceOwnership._from_payload(
        Path("/workspace"), "lab", json.dumps({"schema": 1, "workspace_id": "0" * 32}).encode()
    )
    store = RecordingStore(ownership, daemon_id="daemon", attempt_id=case_input["attempt_id"])
    return {
        "value": {
            "docker_recording": store.relative.as_posix(),
            "native_evidence": native_evidence_directory(case_input["attempt_id"]).as_posix(),
        }
    }


def _sealed_schema_name(case_input: dict) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as work_dir:
        agent = SimpleNamespace(_work_dir=Path(work_dir))
        return {"text": CodexManagedAgentAdapter._sealed_output_schema(agent, case_input["schema_json"]).name}


def _ssh_key_fingerprint(case_input: dict) -> dict[str, str]:
    try:
        return {"text": key_fingerprint(case_input["public_key"])}
    except ValueError as exc:
        raise Rejected("validate") from exc


def _scram(case_input: dict) -> dict[str, str]:
    return {"text": _scram_verifier(case_input["password"], salt=bytes.fromhex(case_input["salt_hex"]))}


def _transcript(case_input: dict) -> dict[str, str]:
    frames = [
        TranscriptFrame(frame["sequence"], frame["timestamp"], frame["direction"], bytes.fromhex(frame["data_hex"]))
        for frame in case_input["frames"]
    ]
    return {"text": _transcript_chain(frames)}


def _trial_id_and_seed(case_input: dict) -> dict[str, object]:
    coordinate = {
        "source_set_digest": case_input["source_set_digest"],
        "condition_id": case_input["condition_id"],
        "replication_ordinal": case_input["replication_ordinal"],
    }
    return {
        "value": {
            "planned_trial_id": trial_plan._derive_planned_trial_id(**coordinate),
            "seed": trial_plan._derive_seed(**coordinate, control_id=case_input["control_id"]),
        }
    }


def _control_intent(case_input: dict) -> dict[str, object]:
    turn = SimpleNamespace(**case_input["turn"])
    return {
        "value": _control_intent_fields(
            turn,
            run_id=case_input["run_id"],
            suffix=case_input["suffix"],
            expected_state_revision=case_input["expected_state_revision"],
        )
    }


def _apparatus_node_name(case_input: dict) -> dict[str, str]:
    return {"text": apparatus_node_name(SimpleNamespace(apparatus_id=case_input["apparatus_id"]))}


def _seat_image_names(case_input: dict) -> dict[str, object]:
    reference = parse_seat_image_reference(case_input["reference"])
    cache = Path("/cache")
    selection = image_selection._selection_path(cache, reference).relative_to(cache).as_posix()
    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / "key.pub"
        key.write_text(case_input["public_key_pem"], encoding="ascii")
        image_trust.configure_trust(Path(tmp) / "cache", case_input["reference"], key)
        (trusted,) = (Path(tmp) / "cache" / "trust").iterdir()
    return {"value": {"selection": selection, "trust_key": f"trust/{trusted.name}"}}


def _observation_event(case_input: dict) -> dict[str, object]:
    spec = SimpleNamespace(**case_input["spec"])
    state = SimpleNamespace(**case_input["state"])
    observation = SimpleNamespace(**case_input["observation"])
    return {
        "value": raes_participant_actions._observation_event(
            spec, state, case_input["action_instance_id"], case_input["timestamp"], observation
        )
    }


def _shared_state_records(case_input: dict) -> dict[str, object]:
    return {
        "value": raes_participant_actions._shared_state_records(
            case_input["participant_address"],
            SimpleNamespace(**case_input["spec"]),
            case_input["action_instance_id"],
            case_input["success"],
        )
    }


def _seat_observation_id(case_input: dict) -> dict[str, str]:
    return {"text": observation_id_for(HostBoundaryObservation.model_validate_json(json.dumps(case_input)))}


def _alert_summary(case_input: dict) -> dict[str, object]:
    return {"value": _matched_alert_summary(case_input)}


def _guest_recovery_status(_case_input: dict) -> dict[str, str]:
    return {"hex": guest_surfaces._RECOVERY_STATUS.hex()}


def _model(model: type, value: object) -> object:
    """Validate value as JSON text, as the owner reads a persisted document."""

    return model.model_validate_json(json.dumps(value))


def _written(write: Callable[[Path], object], name: str = "document.json") -> bytes:
    """Return the bytes that write puts at a file of a new directory."""

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        write(path)
        return path.read_bytes()


def _guest_access_bundle(case_input: dict) -> dict[str, str]:
    return {"hex": encode_guest_access_bundle(_model(GuestAccessBundle, case_input)).hex()}


def _guest_access_request(case_input: dict) -> dict[str, str]:
    request = _model(GuestAccessRequest, case_input)
    return {"hex": _written(lambda path: publish_guest_access_request(path, request)).hex()}


def _overlay_identity(case_input: dict) -> dict[str, object]:
    draws = iter((bytes.fromhex(case_input["identity_hex"]), bytes.fromhex(case_input["credential_hex"])))
    identity = overlay_identity._new_identity(lambda size: next(draws))
    data = _written(lambda path: overlay_identity._persist_create_once(path, identity))
    return {"value": {"identity": identity.model_dump(mode="json"), "file_hex": data.hex()}}


def _seat_record(case_input: dict) -> dict[str, str]:
    record = _model(SeatRecord, case_input)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "seat"
        persist_seat_record(root, record)
        return {"hex": seat_state_path(root).read_bytes().hex()}


def _guest_readiness(case_input: dict) -> dict[str, str]:
    challenge = _model(readiness.GuestReadinessChallenge, case_input["challenge"])
    observation = _model(GuestBoundaryObservation, case_input["observation"])
    return {"hex": readiness.encode_guest_readiness(challenge, observation).hex()}


def _readiness_challenge(case_input: dict) -> dict[str, str]:
    fields = {key: case_input[key] for key in ("seat_id", "instance_id", "generation", "launch_descriptor_digest")}
    with patch.object(readiness.secrets, "token_hex", side_effect=[case_input["nonce"], "0" * 16]):
        data = _written(lambda path: readiness.publish_readiness_challenge(path, **fields), "challenge.json")
    return {"hex": data.hex()}


def _techvault_boundary_policy(_case_input: dict) -> dict[str, object]:
    data = _written(write_full_techvault_boundary_policy, "policy.json")
    return {"value": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}}


def _runtime_evidence_json(case_input: object) -> dict[str, str]:
    try:
        return {"hex": lilrae_runtime_evidence._json_bytes(case_input).hex()}
    except ValueError as exc:
        raise Rejected("serialize") from exc


def _docker_recording_json(case_input: object) -> dict[str, object]:
    return {
        "value": {
            "hex": lilrae_docker_recording._encode(case_input).hex(),
            "digest": lilrae_docker_recording.recording_digest(case_input),
        }
    }


def _cleanup_action_record(case_input: dict) -> dict[str, object]:
    action = startup_reset_state.CleanupAction(**case_input)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            startup_reset_state.persist_cleanup_action(root, action)
        except ValueError as exc:
            raise Rejected("validate") from exc
        (path,) = (root / ".aptl/lifecycle/cleanup-actions-v1").iterdir()
        return {"value": {"name": path.name, "hex": path.read_bytes().hex()}}


def _discovery_line(case_input: dict) -> dict[str, str]:
    try:
        return {"hex": DiscoveryIndex._render_line(case_input["event"], IndexEntry(**case_input["entry"])).hex()}
    except ValueError as exc:
        raise Rejected("serialize") from exc


def _egress_proxy_policy(case_input: dict) -> dict[str, str]:
    try:
        return {"hex": render_egress_proxy_policy(_model(ApplianceBoundaryPolicy, case_input)).hex()}
    except ValueError as exc:
        raise Rejected("validate") from exc


def _qualification_attestation(case_input: dict) -> dict[str, str]:
    report = _model(ParticipantQualificationReport, case_input)
    return {"hex": participant_qualification_attestation_payload(report).hex()}


def _family_target(case_input: dict) -> dict[str, str]:
    target = QualifiedFamilyTarget(
        pack=PackIdentity(**case_input["pack"]),
        family_id=case_input["family_id"],
        family_digest=case_input["family_digest"],
        backend=BackendIdentity(**case_input["backend"]),
    )
    try:
        return {"text": encode_family_target(target)}
    except ValueError as exc:
        raise Rejected("validate") from exc


def _operator_groups(case_input: dict) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            persist_admitted_operator_groups(root, case_input["groups"])
        except ValueError as exc:
            raise Rejected("validate") from exc
        (path,) = (root / ".aptl/lifecycle/operator-groups-v1").iterdir()
        return {"value": {"name": path.name, "hex": path.read_bytes().hex()}}


def _techvault_bounded_json(case_input: dict) -> dict[str, object]:
    native = techvault_evidence._bounded_json(case_input["value"])
    readiness = techvault_readiness_probes.bounded_json(case_input["value"], case_input["limit"])
    return {
        "value": {
            "native_hex": None if native is None else native.hex(),
            "readiness_hex": None if readiness is None else readiness.hex(),
        }
    }


def _compose_ownership_override(case_input: dict) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = json.dumps({"schema": 1, "workspace_id": case_input["workspace_id"]}, sort_keys=True, separators=(",", ":"))
        try:
            ownership = WorkspaceOwnership._from_payload(root, case_input["logical"], (state + "\n").encode())
        except ValueError as exc:
            raise Rejected("validate") from exc
        files = []
        for index, text in enumerate(case_input["compose_files"]):
            path = root / f"compose-{index}.yml"
            path.write_text(text, encoding="utf-8")
            files.append(path)
        path, _semantic, expected = write_compose_ownership_override(
            ownership, attempt_id=case_input["attempt_id"], compose_files=tuple(files)
        )
        return {
            "value": {
                "path": path.relative_to(root).as_posix(),
                "hex": path.read_bytes().hex(),
                "expected": {kind: list(names) for kind, names in expected.items()},
            }
        }


def _jsonl_projection(case_input: dict) -> dict[str, object]:
    context = ProjectionContext(
        run_dir=Path("/run"), records=tuple(case_input["records"]), retained_sizes={}, limits=DEFAULT_LIMITS
    )
    result = JsonlProjection.project(context)
    if not result.members:
        return {"value": {"members": [], "limitations": [item.code for item in result.limitations]}}
    (member,) = result.members
    return {
        "value": {
            "path": member.bundle_path,
            "digest": member.digest,
            "size": member.size,
            "content_hex": member.content.hex(),
        }
    }


def _lifecycle_attestation(case_input: dict) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalRunStore(Path(tmp))
        evidence = write_lifecycle_evidence(
            store,
            attempt_id=case_input["attempt_id"],
            scope=SimpleNamespace(planned_trial_id=case_input["planned_trial_id"]),
            resolution=SimpleNamespace(cause=case_input["terminal_cause"]),
            ended_at=case_input["ended_at"],
        )
        run_dir = Path(tmp) / case_input["attempt_id"]
        return {
            "value": {
                "blob_path": evidence.artifact.uri,
                "blob_hex": (run_dir / evidence.artifact.uri).read_bytes().hex(),
                "checksum": evidence.artifact.checksum.value,
                "record_path": evidence.record_spec.path,
                "record_hex": (run_dir / evidence.record_spec.path).read_bytes().hex(),
            }
        }


def _provenance_result(result: object) -> dict[str, object]:
    return {
        "value": {
            "status": result.status.value,
            "leaves": [[leaf.logical_id, leaf.digest] for leaf in result.leaves],
            "payload": result.payload,
        }
    }


def _apparatus_provenance(case_input: dict) -> dict[str, object]:
    provider = ApparatusManifestProvider(lambda: case_input["backend"], lambda: case_input["processor"])
    return _provenance_result(provider.collect(SimpleNamespace(expired=lambda: False)))


def _range_snapshot(value: dict) -> RangeSnapshot:
    return RangeSnapshot(
        timestamp=value.get("timestamp", ""),
        software=SoftwareVersions(**value.get("software", {})),
        containers=[ContainerSnapshot(**item) for item in value.get("containers", [])],
        wazuh_rules=WazuhRulesSnapshot(**value.get("wazuh_rules", {})),
        networks=[NetworkSnapshot(**item) for item in value.get("networks", [])],
        config_hashes=dict(value.get("config_hashes", {})),
        services=[ServiceEndpoint(**item) for item in value.get("services", [])],
        ssh=[SSHEndpoint(**item) for item in value.get("ssh", [])],
    )


def _runtime_facts(case_input: dict) -> dict[str, object]:
    provider = RuntimeFactsProvider(_range_snapshot(case_input["snapshot"]), lambda: case_input["host_facts"])
    return _provenance_result(provider.collect(SimpleNamespace(expired=lambda: False, max_entries=64)))


def _apparatus_configuration_digest(case_input: dict) -> dict[str, object]:
    descriptors = tuple(ExperimentBindingDescriptorModel.model_validate(item) for item in case_input["descriptors"])
    try:
        realized, projection, digest, binding_ids = _apparatus_configuration(descriptors, AptlConfig())
    except ValueError as exc:
        raise Rejected("validate") from exc
    return {
        "value": {
            "digest": digest,
            "projection": [list(item) for item in projection],
            "binding_ids": sorted(binding_ids),
            "action_timeout_seconds": realized.experiment.participant_action_timeout_seconds,
        }
    }


def _capture_plan(case_input: dict) -> dict[str, object]:
    plan = admit_capture_demands((), source_identity=case_input["source_identity"])
    return {
        "value": {
            "canonical_hex": plan.canonical_bytes.hex(),
            "plan_digest": plan.plan_digest,
            "plan_id": plan.plan_id,
        }
    }


def _bytes_or_none(data: bytes | None) -> dict[str, object]:
    return {"value": None if data is None else data.hex()}


def _misp_readiness(case_input: dict) -> dict[str, object]:
    admitted = techvault_misp_readiness.AdmittedMispState(**case_input["admitted"])
    return _bytes_or_none(techvault_misp_readiness._readiness_document(case_input["payload"], admitted))


def _wazuh_agent_readiness(case_input: dict) -> dict[str, object]:
    return _bytes_or_none(
        techvault_wazuh_agent_readiness._readiness_document(case_input["payload"], tuple(case_input["expected_nodes"]))
    )


def _source_result(result: object) -> dict[str, object]:
    return {
        "value": {
            "status": result.status.value,
            "chunks_hex": [chunk.hex() for chunk in result.chunks],
            "source_pipeline": result.source_pipeline,
        }
    }


def _sqli_correlation(case_input: dict) -> dict[str, object]:
    source = techvault_evidence.SuricataWazuhSqliSource(
        lambda: case_input["trigger"],
        lambda _start, _end: case_input["suricata_events"],
        lambda _start, _end: case_input["wazuh_events"],
    )
    return _source_result(source.fetch(case_input["start"], case_input["end"]))


def _suricata_readiness(case_input: dict) -> dict[str, object]:
    source = SuricataRuleReadinessSource(lambda _start, _end: case_input["payload"])
    return _source_result(source.fetch(case_input["start"], case_input["end"]))


def _transcript_document(case_input: dict) -> dict[str, object]:
    sessions = tuple(
        TranscriptSession(
            session_id=item["session_id"],
            started_at=item["started_at"],
            finished_at=item["finished_at"],
            close_reason=item["close_reason"],
            frames=tuple(
                TranscriptFrame(frame["sequence"], frame["timestamp"], frame["direction"], bytes.fromhex(frame["data_hex"]))
                for frame in item["frames"]
            ),
            final_chain_digest=item["final_chain_digest"],
        )
        for item in case_input["sessions"]
    )
    return _source_result(_transcript_result(sessions, case_input["start"], case_input["end"]))


def _crossing_policies(case_input: dict) -> dict[str, object]:
    turns = tuple(SimpleNamespace(**turn) for turn in case_input["turns"])
    try:
        policies = _delivery_crossing_policies(turns)
    except AgentExecutionError as exc:
        raise Rejected("validate") from exc
    return {"value": {participant: policy.model_dump(mode="json") for participant, policy in policies.items()}}


def _delivery_evidence(case_input: dict) -> dict[str, object]:
    collector = SimpleNamespace(
        _context=SimpleNamespace(clock=SimpleNamespace(now=lambda: case_input["finished_at"])),
        _failed=False,
        _payload=case_input["payload"],
        _started_at=case_input["started_at"],
        result=SimpleNamespace(
            provider_payload=case_input["provider_payload"],
            response=case_input["response"],
            session_id=case_input["session_id"],
            cleanup=None,
        ),
    )
    outcome = _ParticipantDeliveryCollector.stop(collector, collector)
    return {"value": {"status": outcome.status.value, "chunks_hex": [chunk.hex() for chunk in outcome.chunks]}}


class _FixedClock:
    """A datetime stand-in whose now returns one instant."""

    def __init__(self, instant: str) -> None:
        self._instant = instant

    def now(self, tz: object = None) -> object:
        return SimpleNamespace(isoformat=lambda: self._instant)


def _native_cleanup(case_input: dict) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = json.dumps({"schema": 1, "workspace_id": case_input["workspace_id"]}, sort_keys=True, separators=(",", ":"))
        ownership = WorkspaceOwnership._from_payload(root, case_input["logical"], (state + "\n").encode())
        receipt = ResourceReceipt(
            workspace_id=ownership.workspace_id, project_name=ownership.project_name, **case_input["receipt"]
        )
        ownership.record(receipt)
        with (
            patch.object(lilrae_native_evidence, "datetime", _FixedClock(case_input["recorded_at"])),
            patch.object(lilrae_native_evidence, "uuid4", return_value=SimpleNamespace(hex=case_input["uuid_hex"])),
        ):
            try:
                lilrae_native_evidence.record_cleanup(ownership, receipt, cause=case_input["cause"])
            except ValueError as exc:
                raise Rejected("validate") from exc
        directory = root / native_evidence_directory(receipt.attempt_id)
        (retained,) = (directory / "receipts").iterdir()
        (observation,) = (directory / "cleanup").iterdir()
        return {
            "value": {
                "retained_name": retained.name,
                "observation_name": observation.name,
                "observation_hex": observation.read_bytes().hex(),
            }
        }


_REPOSITORY = Path(__file__).resolve().parents[1]


def _compiled_runtime_model(case_input: dict) -> dict[str, object]:
    admitted = admit_raes_scenario(
        _REPOSITORY, AptlConfig(lab={"name": "vectors"}), MagicMock(), scenario_path=_REPOSITORY / case_input["scenario"]
    )
    model = admitted.execution_plan.model
    data = compiled_runtime_model_bytes(model)
    return {"value": {"sha256": compiled_runtime_model_sha256(model), "size": len(data), "last_byte_hex": data[-1:].hex()}}


def _candidate_selections(case_input: dict) -> dict[str, object]:
    view = case_input["participant_view"]
    surface = SimpleNamespace(
        delivery=SimpleNamespace(delivery_ref=case_input["delivery_ref"]),
        assurance=SimpleNamespace(participant_view_digest=case_input["participant_view_digest"]),
        participant_view=SimpleNamespace(
            surface_id=view["surface_id"],
            decision_epoch=view["decision_epoch"],
            episode_id=view["episode_id"],
            action_entries=[SimpleNamespace(**entry) for entry in view["action_entries"]],
        ),
    )
    model = SimpleNamespace(
        action_contracts={
            address: SimpleNamespace(argument_definitions=definitions)
            for address, definitions in case_input["argument_definitions"].items()
        }
    )
    try:
        selections = candidate_selections(surface, model, completed_action_sequence=tuple(case_input["completed"]))
    except ValueError as exc:
        raise Rejected("validate") from exc
    return {"value": [selection.model_dump(mode="json") for selection in selections]}


OWNER_SCHEMES: dict[str, Callable[[dict], dict[str, object]]] = {
    "participant-episode-state-dir": _episode_state_dir,
    "participant-binding-post-state-digest": _binding_post_state_digest,
    "cert-generator-project-name": _cert_generator_name,
    "correlation-stable-ref": _stable_ref,
    "compose-environment-file-names": _compose_environment_names,
    "compose-receipt-path": _receipt_path,
    "attempt-directory-names": _attempt_directories,
    "sealed-output-schema-name": _sealed_schema_name,
    "ssh-key-fingerprint": _ssh_key_fingerprint,
    "postgres-scram-verifier": _scram,
    "techvault-transcript-chain": _transcript,
    "trial-id-and-seed": _trial_id_and_seed,
    "participant-control-intent": _control_intent,
    "apparatus-node-name": _apparatus_node_name,
    "seat-image-names": _seat_image_names,
    "participant-observation-event": _observation_event,
    "participant-shared-state-records": _shared_state_records,
    "seat-observation-id": _seat_observation_id,
    "live-gate-alert-summary": _alert_summary,
    "guest-recovery-status": _guest_recovery_status,
    "seat-guest-access-bundle": _guest_access_bundle,
    "seat-guest-access-request": _guest_access_request,
    "seat-overlay-identity": _overlay_identity,
    "seat-record": _seat_record,
    "seat-guest-readiness": _guest_readiness,
    "seat-readiness-challenge": _readiness_challenge,
    "techvault-boundary-policy": _techvault_boundary_policy,
    "runtime-evidence-json": _runtime_evidence_json,
    "docker-recording-json": _docker_recording_json,
    "cleanup-action-record": _cleanup_action_record,
    "archival-discovery-line": _discovery_line,
    "egress-proxy-policy": _egress_proxy_policy,
    "participant-qualification-attestation": _qualification_attestation,
    "family-target-encoding": _family_target,
    "operator-group-record": _operator_groups,
    "techvault-bounded-json": _techvault_bounded_json,
    "compose-ownership-override": _compose_ownership_override,
    "bundle-jsonl-projection": _jsonl_projection,
    "lifecycle-attestation": _lifecycle_attestation,
    "apparatus-provenance-leaves": _apparatus_provenance,
    "runtime-facts-provenance": _runtime_facts,
    "apparatus-configuration-digest": _apparatus_configuration_digest,
    "capture-plan": _capture_plan,
    "techvault-misp-readiness": _misp_readiness,
    "techvault-wazuh-agent-readiness": _wazuh_agent_readiness,
    "techvault-sqli-correlation": _sqli_correlation,
    "techvault-suricata-readiness": _suricata_readiness,
    "techvault-transcript-document": _transcript_document,
    "participant-crossing-policies": _crossing_policies,
    "participant-delivery-evidence": _delivery_evidence,
    "native-cleanup-observation": _native_cleanup,
    "compiled-runtime-model": _compiled_runtime_model,
    "participant-candidate-selections": _candidate_selections,
}
