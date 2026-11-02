"""Content-backed capture owners for the released trial reporting boundary."""

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json

from raes_contracts.contracts import (
    ExperimentApparatusContextModel,
    ExperimentArtifactRefModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentResultSummaryModel,
    ParticipantImplementationProvenanceModel,
    ParticipantImplementationSelectionModel,
)
from raes_runtime.experiment_records import ExperimentRunMetadata
from raes_runtime.runtime_trial_services import TrialCaptureObservation

from tests.archival_fixtures import reference_run


class ReportingEvidence:
    """Produce exact fixture bytes and fresh immutable readers, never fetch URIs."""

    def __init__(self, inputs, services):
        self.inputs = inputs
        self.services = services
        self.records = {}
        self.content = {}
        self.metadata = {}
        self.omit_required = False

    def capture(self, request, snapshot):
        event = {
            "event_type": "observation_emitted",
            "timestamp": self.now(),
            "participant_address": "agents.operator",
            "episode_id": "episode",
            "action_instance_id": "action-1",
            "action_contract_address": "actions.perform",
        }
        payload = json.dumps([event]).encode()
        artifact = self.artifact(
            "observation-" + request.run_id, payload, "observation"
        )
        spec = next(iter(self.inputs.capture_specs.values()))
        record = ExperimentEvidenceRecordModel(
            schema_version="experiment-evidence-record/v1",
            evidence_record_id="trace-" + request.run_id,
            record_version="1",
            capture_spec_ref={
                "ref_kind": "capture-spec",
                "ref_id": spec.capture_spec_id,
                "ref_version": spec.spec_version,
            },
            capture_requirement_ref="alert-trace",
            output_contract="participant-behavior-history-event-stream-v1",
            run_ref={"ref_kind": "run", "ref_id": request.run_id},
            source_refs=[
                {
                    "ref_kind": "measurement-channel",
                    "ref_id": "evaluation-history-channel",
                    "ref_version": "1.0.0",
                }
            ],
            evidence_kind="trace",
            captured_at=self.now(),
            capture_window_ref="episode",
            raw_content={"artifact_ref": artifact},
            sensitivity="internal",
            redaction_state="none",
        )
        self.records[request.run_id] = record
        self.services.records[record.evidence_record_id] = record
        from raes_contracts.runtime_state import ApplyResult

        return ApplyResult(True, snapshot), TrialCaptureObservation(
            complete=True, evidence=(record,)
        )

    def evaluate(self, request, result):
        if result is None:
            return self.metadata
        apparatus = reference_run().apparatus_context.model_dump(mode="json")
        apparatus["components"] = {}
        apparatus["selected_manifests"] = []
        from raes_contracts.canonical import canonical_json_digest

        for key, manifest in self.inputs.apparatus_manifests.items():
            kind = key[0]
            ref = {
                "ref_kind": "manifest",
                "ref_id": manifest.identity.name,
                "ref_version": manifest.schema_version,
                "ref_digest": canonical_json_digest(manifest.model_dump(mode="json")),
                "subject_ref": {
                    "ref_kind": kind,
                    "ref_id": manifest.identity.name,
                    "ref_version": manifest.identity.version,
                },
            }
            apparatus["components"][kind] = {
                "component_kind": kind,
                "identity": manifest.identity.model_dump(mode="json"),
                "manifest_ref": ref,
                "observed": True,
            }
            apparatus["selected_manifests"].append(ref)
        setup = self.artifact("setup-" + request.run_id, b"{}", "apparatus-evidence")
        apparatus["observed_setup_evidence"] = [setup.model_dump(mode="json")]
        artifact = self.records[request.run_id].raw_content.artifact_ref
        config = request.participant_configurations[0]
        participant = next(iter(self.inputs.participant_manifests.values()))
        selection = (
            reference_run()
            .participant_implementation_provenance.participant_implementations[0]
            .model_dump(mode="json")
        )
        selection.update(
            participant_address=config.participant_address,
            implementation_identity=participant.identity.model_dump(mode="json"),
            manifest_ref=config.manifest_ref,
            manifest_digest=config.manifest_digest,
            configuration_ref="configuration:" + config.participant_address,
            configuration_digest=config.configuration_digest,
        )
        self.metadata[request.run_id] = ExperimentRunMetadata(
            outcome_status="succeeded",
            traceability={
                "capture_spec_refs": [self.records[request.run_id].capture_spec_ref],
                "evidence_record_refs": [
                    {
                        "ref_kind": "evidence-record",
                        "ref_id": self.records[request.run_id].evidence_record_id,
                        "ref_version": "1",
                    }
                ],
            },
            participant_implementation_provenance=ParticipantImplementationProvenanceModel(
                run_id=request.run_id,
                participant_implementations=[
                    ParticipantImplementationSelectionModel.model_validate(selection)
                ],
            ),
            apparatus_context=ExperimentApparatusContextModel.model_validate(apparatus),
            evidence_artifacts=(artifact, setup),
            result_summaries={
                "findings": ExperimentResultSummaryModel(
                    metric_id="confirmed-findings",
                    value_status="reported",
                    value=1,
                    evidence_refs=[
                        {"ref_kind": "evidence", "ref_id": artifact.artifact_id}
                    ],
                )
            },
        )
        return self.metadata

    def reader(self, run):
        record = self.records[run.run_id]
        artifact = record.raw_content.artifact_ref
        return ExperimentRunEvidenceInputs(
            capture_specs=self.inputs.capture_specs,
            evidence_records={}
            if self.omit_required
            else {record.evidence_record_id: record},
            artifact_readers={}
            if self.omit_required
            else {artifact.artifact_id: BytesIO(self.content[artifact.artifact_id])},
        )

    def artifact(self, identity, content, role):
        self.content[identity] = content
        return ExperimentArtifactRefModel(
            artifact_id=identity,
            role=role,
            media_type="application/json",
            uri="evidence/" + identity + ".json",
            checksum={
                "algorithm": "sha256",
                "value": hashlib.sha256(content).hexdigest(),
            },
            size_bytes=len(content),
            created_at=self.now(),
            source="fixture-owner",
            sensitivity="internal",
        )

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()


def native_failure_bindings():
    from tests.test_lilrae_concurrent_participants import bindings
    from aptl.workbench.process import (
        BoundedProcessError,
        ProcessCleanup,
        REASON_TIMEOUT,
    )

    def fail(action, cancellation):
        raise BoundedProcessError(
            REASON_TIMEOUT, cleanup=ProcessCleanup(1, 0), stdout_bytes=0, stderr_bytes=0
        )

    from dataclasses import replace

    return tuple(
        replace(
            item,
            execution_binding=replace(item.execution_binding, max_action_attempts=2),
        )
        for item in bindings({"red": fail, "blue": lambda *args: "peer observation"})
    )


def add_native_context(context, installed):
    from aptl.backends.raes_manifest import create_aptl_manifest
    from raes_backend_protocols.manifest import backend_manifest_v2_model
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts import AdmittedParticipantManifestReferenceModel

    native = backend_manifest_v2_model(
        create_aptl_manifest(autonomous_bindings=installed)
    )
    key = next(key for key in context["apparatus_manifests"] if key[0] == "backend")
    backend = context["apparatus_manifests"][key]
    payload = backend.model_dump(mode="json")
    payload["capabilities"]["participant_runtime"] = (
        native.capabilities.participant_runtime.model_dump(mode="json")
    )
    payload["capabilities"]["time"] = native.capabilities.time.model_dump(mode="json")
    payload["supported_contract_versions"] = sorted(
        set(payload["supported_contract_versions"])
        | set(native.supported_contract_versions)
        - {"backend-runtime-descendants-v1", "backend-materialization-attestation-v1"}
    )
    context["apparatus_manifests"][key] = type(backend).model_validate(payload)
    refs = list(context["apparatus"].participant_manifest_refs)
    for role, item in zip(("red", "blue"), installed, strict=True):
        participant = item.implementation_manifest
        address = "agents." + role
        context["participant_manifests"][
            (
                address,
                participant.identity.name,
                participant.identity.version,
                participant.schema_version,
            )
        ] = participant
        refs.append(
            AdmittedParticipantManifestReferenceModel(
                participant_address=address,
                implementation_name=participant.identity.name,
                implementation_version=participant.identity.version,
                manifest_version=participant.schema_version,
                manifest_digest=canonical_json_digest(
                    participant.model_dump(mode="json")
                ),
            )
        )
    context["apparatus"] = context["apparatus"].model_copy(
        update={"participant_manifest_refs": refs}
    )


def add_native_scenario(payload, policy):
    from tests.lilrae_concurrent_fixture import scenario

    native = scenario(attempts=2).model_dump(mode="json", exclude_none=True)
    for section in (
        "entities",
        "agents",
        "action_contracts",
        "observation_boundaries",
        "objectives",
    ):
        payload.setdefault(section, {}).update(native[section])
    for section in (
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
    behavior["participant_refs"] = ["red", "blue"]
    behavior["participant_role_refs"] = []
    behavior["autonomous_execution"]["evaluation_authority"]["objective_refs"] = [
        "red",
        "blue",
    ]
    behavior["autonomous_execution"]["failure_policy"] = policy
    from copy import deepcopy

    node = deepcopy(payload["nodes"]["gateway"])
    node["services"] = [{"name": "http", "port": 8080, "protocol": "tcp"}]
    payload["nodes"]["target"] = node
    payload["infrastructure"]["target"] = {"count": 1}


class RecordingArchive:
    """Observe exact public record publication and readback in boundary tests."""

    def __init__(self):
        self.sources = {}
        self.runs = {}
        self.studies = {}

    def write_sources(self, source):
        self.sources[source.run_id] = source

    def write_run(self, run):
        key = (run.run_id, run.run_version)
        prior = self.runs.setdefault(key, run.model_copy(deep=True))
        assert prior == run

    def read_run(self, run_id, run_version):
        return self.runs[(run_id, run_version)].model_copy(deep=True)

    def write_study(self, study):
        key = (study.study_id, study.study_version)
        prior = self.studies.setdefault(key, study.model_copy(deep=True))
        assert prior == study

    def read_study(self, study_id, study_version):
        return self.studies[(study_id, study_version)].model_copy(deep=True)
