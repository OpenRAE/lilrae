"""The persisted byte and identity schemes pass the shared vectors (#1555).

Each file in ``conformance/testdata/vectors`` holds the vectors of one scheme.
A closed map binds each scheme ID to its existing owner in ``src/aptl``. The
expected values are fixed in the corpus; no test computes them with the code
under test. A failure names the scheme and the case, never the input or the
expected bytes, because a vector can hold a synthetic secret.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import rfc8785
import yaml
from raes_contracts.contracts import ExperimentEvidenceRecordModel

from aptl.appliance.seat import lifecycle as seat_lifecycle
from aptl.appliance.seat.launch_descriptor import (
    SeatLaunchDescriptor,
    canonical_launch_bytes,
)
from aptl.backends import _raes_proposition_truth, raes_artifact_mechanisms
from aptl.backends._raes_evidence_truth_refresh import evidence_cut_key
from aptl.backends._raes_participant_execution import _ParticipantDeliveryExecutor
from aptl.backends.raes_participant_apparatus import canonical_mapping_digest
from aptl.backends.raes_participant_control_evidence import selection_fingerprint
from aptl.backends.raes_participant_execution_support import mapping_digest
from aptl.backends.raes_participant_fixture_core import (
    _mapping_digest as fixture_mapping_digest,
)
from aptl.core import continuity
from aptl.core._credential_sources import ProcessEnvironmentCredentialSource
from aptl.core.appliance_boundary import ApplianceBoundaryPolicy
from aptl.core.config import validate_compose_project_name
from aptl.core.correlation import clock as correlation_clock
from aptl.core.correlation._extract import _content_signature
from aptl.core.correlation.models import (
    AssociationMethod,
    ClockContext,
    CorrelationEdge,
    CorrelationNode,
    CorrelationProjection,
)
from aptl.core.deployment import _boundary_validation
from aptl.core.deployment import _compose_ownership_override as compose_override
from aptl.core.deployment import _compose_resource_ownership as ownership
from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    WorkspaceOwnership,
)
from aptl.core.evidence.records import derive_evidence_record_id
from aptl.core.evidence_bundle import verify as bundle_verify
from aptl.core.evidence_bundle.envelope import BundleEnvelopeV1
from aptl.core.evidence_bundle.projections import parquet as parquet_projection
from aptl.core.experiment import resolver, spec_loading
from aptl.core.experiment.capture_registry import (
    CaptureLimits,
    CaptureVisibility,
    CollectorRegistration,
)
from aptl.core.experiment.errors import AdmissionRejection
from aptl.core.experiment.policy import OrderingKind
from aptl.core.experiment.trial_plan import compute_source_set_digest
from aptl.core.experiment.trial_plan_models import PlannedTrial, canonicalize_trial_plan
from aptl.core.flags import verify_token
from aptl.core.provenance.identity import ProvenanceIdentityError, derive_identity
from aptl.core.runstore_internals import _canonicalize_payload, _validate_id
from aptl.core.runtime import workflow_engine
from aptl.utils.strict_json import loads_strict
from tests.serialization_owner_schemes import OWNER_SCHEMES, Rejected

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "conformance" / "testdata" / "vectors"
INVENTORY = ROOT / "docs" / "reference" / "serialization-schemes.md"

_CASE_FIELDS = {"id", "input", "input_hex", "expect", "note"}
_EXPECT_FIELDS = {"hex", "text", "value", "reject"}


def _decode(value: object) -> object:
    """Return the vector input with its number tags decoded."""

    if isinstance(value, dict):
        if set(value) == {"$int"}:
            return int(value["$int"])
        if set(value) == {"$float"}:
            return float(value["$float"])
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _rfc8785(case_input: object) -> dict[str, str]:
    try:
        return {"hex": rfc8785.dumps(case_input).hex()}
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise Rejected("serialize") from exc


def _sorted_compact_json(case_input: object) -> dict[str, str]:
    data = json.dumps(case_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"hex": data.hex()}


def _compose_ownership_json(case_input: object) -> dict[str, str]:
    return {"hex": ownership._canonical_json(case_input).hex()}


def _credential_descriptor(case_input: object) -> dict[str, str]:
    source = ProcessEnvironmentCredentialSource.model_validate(case_input)
    return {"text": source.descriptor_digest()}


def _provenance_identity(case_input: object) -> dict[str, str]:
    try:
        return {"text": derive_identity(case_input["domain"], case_input["payload"])}
    except ProvenanceIdentityError as exc:
        raise Rejected("serialize") from exc


def _source_set_digest(case_input: object) -> dict[str, str]:
    try:
        return {"text": compute_source_set_digest(case_input)}
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise Rejected("serialize") from exc


def _evidence_record_id(case_input: object) -> dict[str, str]:
    binding = SimpleNamespace(**case_input["binding"])
    record_id = derive_evidence_record_id(
        run_id=case_input["run_id"],
        planned_trial_id=case_input["planned_trial_id"],
        binding=binding,
        content_digest=case_input["content_digest"],
    )
    return {"text": record_id}


def _locator_digest(case_input: object) -> dict[str, str]:
    data = bytes.fromhex(case_input["data_hex"])
    return {"text": resolver._digest_hex(data, case_input["algorithm"])}


def _compose_project_name(case_input: object) -> dict[str, str]:
    try:
        return {"text": validate_compose_project_name(case_input)}
    except ValueError as exc:
        raise Rejected("validate") from exc


def _runstore_payload(case_input: object) -> dict[str, str]:
    try:
        canonical, _structure = _canonicalize_payload(case_input)
    except ValueError as exc:
        raise Rejected("serialize") from exc
    return {"hex": canonical.hex()}


def _sha256_bytes(case_input: bytes) -> dict[str, str]:
    return {"text": hashlib.sha256(case_input).hexdigest()}


def _rfc8785_digest(owner: Callable[[object], str]) -> Callable[[object], dict[str, str]]:
    """Bind a scheme whose owner returns the digest of RFC 8785 bytes."""

    def run(case_input: object) -> dict[str, str]:
        try:
            return {"text": owner(case_input)}
        except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
            raise Rejected("serialize") from exc

    return run


def _text(owner: Callable[[object], str]) -> Callable[[object], dict[str, str]]:
    """Bind a scheme whose owner returns text and rejects nothing."""

    return lambda case_input: {"text": owner(case_input)}


def _boundary_policy_digest(case_input: object) -> dict[str, str]:
    return {"text": _boundary_validation.digest(_boundary_validation.canonical(case_input))}


def _participant_session_id(case_input: object) -> dict[str, str]:
    executor = SimpleNamespace(sessions={}, context=SimpleNamespace(run_id=case_input["run_id"]))
    turn = SimpleNamespace(participant_address=case_input["participant_address"])
    return {"text": _ParticipantDeliveryExecutor._session_id(executor, turn)}


def _evidence_cut_key(case_input: object) -> dict[str, str]:
    records = tuple(ExperimentEvidenceRecordModel.model_validate(record) for record in case_input)
    return {"text": evidence_cut_key(records)}


def _bundle_identity(case_input: object) -> dict[str, object]:
    """The writer's root identity and bundle.json bytes, and the verifier's root."""

    envelope = BundleEnvelopeV1.model_validate(case_input)
    return {
        "value": {
            "root_identity": envelope.root_identity(),
            "bundle_json_hex": envelope.to_canonical_bytes().hex(),
            "verifier_root": bundle_verify._root_identity(case_input),
        }
    }


def _collector_registration_digest(case_input: object) -> dict[str, str]:
    fields = dict(case_input)
    for name, value in fields.items():
        if isinstance(value, list):
            fields[name] = frozenset(value)
    fields["visibility_class"] = CaptureVisibility(fields["visibility_class"])
    fields["limits"] = CaptureLimits(**fields["limits"])
    return {"text": CollectorRegistration(**fields).effective_config_digest()}


def _correlation_projection(case_input: object) -> dict[str, object]:
    try:
        projection = CorrelationProjection(
            run_id=case_input["run_id"],
            nodes=tuple(CorrelationNode(**node) for node in case_input["nodes"]),
            edges=tuple(
                CorrelationEdge(
                    **{**edge, "association_method": AssociationMethod(edge["association_method"])},
                )
                for edge in case_input["edges"]
            ),
            clock_contexts=tuple(ClockContext(**clock) for clock in case_input["clock_contexts"]),
            disclosures=tuple(case_input["disclosures"]),
        )
    except ValueError as exc:
        raise Rejected("validate") from exc
    return {"value": {"bytes_hex": projection.canonical_bytes.hex(), "digest": projection.projection_digest}}


def _frozen_now(module: object, instant: str, owner: Callable[[], str]) -> str:
    """Call a timestamp producer with its clock frozen at instant."""

    fixed = datetime.fromisoformat(instant)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    with patch.object(module, "datetime", FrozenDatetime):
        return owner()


def _utc_now(case_input: object) -> dict[str, str]:
    return {"text": _frozen_now(correlation_clock, case_input, correlation_clock.utc_now)}


def _continuity_now(case_input: object) -> dict[str, str]:
    return {"text": _frozen_now(continuity, case_input, continuity._utc_now_iso)}


def _next_timestamp(case_input: object) -> dict[str, str]:
    try:
        return {"text": workflow_engine._next_timestamp(case_input["previous"], offset_ms=case_input["offset_ms"])}
    except ValueError as exc:
        raise Rejected("parse") from exc


def _run_store_id(case_input: object) -> dict[str, str]:
    try:
        return {"text": _validate_id(case_input, "run_id")}
    except ValueError as exc:
        raise Rejected("validate") from exc


def _workspace_names(case_input: object) -> dict[str, object]:
    """The workspace-scoped project name, container names, and labels."""

    try:
        ownership = WorkspaceOwnership._from_payload(
            Path("/workspace"), case_input["logical"], case_input["workspace_state"].encode("utf-8")
        )
        return {
            "value": {
                "project_name": ownership.project_name,
                "container_names": {name: ownership.container_name(name) for name in case_input["semantic_names"]},
                "labels": ownership.labels(attempt_id=case_input["attempt_id"]),
            }
        }
    except (OwnershipConflictError, ValueError) as exc:
        raise Rejected("validate") from exc


def _typed(value: object) -> object:
    """Return a parse result as JSON, tagging each type that JSON cannot carry."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2**53 else {"$int": str(value)}
    if isinstance(value, float):
        return {"$float": repr(value)}
    if isinstance(value, bytes):
        return {"$bytes_hex": value.hex()}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [_typed(item) for item in value]
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: _typed(item) for key, item in value.items()}
        return {"$map": [[_typed(key), _typed(item)] for key, item in value.items()]}
    raise TypeError(f"no vector form for {type(value).__name__}")


def _yaml_loader(load: Callable[[str], object]) -> Callable[[object], dict[str, object]]:
    """Bind a YAML loader: its typed parse result, or a parse rejection."""

    def run(case_input: object) -> dict[str, object]:
        try:
            return {"value": _typed(load(case_input))}
        except yaml.YAMLError as exc:
            raise Rejected("parse") from exc

    return run


def _experiment_yaml_preflight(case_input: object) -> dict[str, str]:
    try:
        spec_loading._yaml_duplicate_key_preflight(case_input, address="spec", code="vector")
    except AdmissionRejection as exc:
        raise Rejected("parse") from exc
    return {"text": "accepted"}


def _strict_json(case_input: bytes) -> dict[str, object]:
    try:
        return {"value": _typed(loads_strict(case_input))}
    except ValueError as exc:
        raise Rejected("parse") from exc


def _seat_launch_bytes(case_input: object) -> dict[str, str]:
    try:
        descriptor = SeatLaunchDescriptor.model_validate(case_input)
    except ValueError as exc:
        raise Rejected("validate") from exc
    return {"hex": canonical_launch_bytes(descriptor).hex()}


def _seat_policy_digest(case_input: object) -> dict[str, str]:
    return {"text": seat_lifecycle._canonical_policy_digest(ApplianceBoundaryPolicy.model_validate(case_input))}


def _parquet_canonical_json(case_input: object) -> dict[str, str]:
    try:
        return {"text": parquet_projection._canonical_json(case_input)}
    except UnicodeDecodeError as exc:
        raise Rejected("serialize") from exc


def _flag_token(case_input: object) -> dict[str, object]:
    return {"value": verify_token(case_input["token"], case_input["key"])}


def _tuples(value: object) -> object:
    """Return value with each list turned into a tuple, as the trial model holds them."""

    if isinstance(value, list):
        return tuple(_tuples(item) for item in value)
    return value


def _trial_plan(case_input: object) -> dict[str, object]:
    trials = tuple(
        PlannedTrial(**{key: _tuples(value) for key, value in trial.items()})
        for trial in case_input["trials"]
    )
    canonical, digest, plan_id = canonicalize_trial_plan(
        policy_version=case_input["policy_version"],
        source_set_digest=case_input["source_set_digest"],
        ordering_kind=OrderingKind(case_input["ordering_kind"]),
        trials=trials,
        capture_bindings=(),
    )
    return {"value": {"bytes_hex": canonical.hex(), "digest": digest, "plan_id": plan_id}}


SCHEMES: dict[str, Callable[[object], dict[str, object]]] = {
    "rfc8785": _rfc8785,
    "sorted-compact-json": _sorted_compact_json,
    "compose-ownership-json": _compose_ownership_json,
    "credential-descriptor-digest": _credential_descriptor,
    "provenance-identity": _provenance_identity,
    "source-set-digest": _source_set_digest,
    "evidence-record-id": _evidence_record_id,
    "locator-digest": _locator_digest,
    "compose-project-name": _compose_project_name,
    "runstore-canonical-payload": _runstore_payload,
    "sha256-bytes": _sha256_bytes,
    "artifact-profile-digest": _text(raes_artifact_mechanisms._profile_digest),
    "participant-selection-fingerprint": _text(selection_fingerprint),
    "governed-arguments-digest": _text(mapping_digest),
    "participant-workflow-digest": _text(fixture_mapping_digest),
    "boundary-policy-digest": _boundary_policy_digest,
    "correlation-content-signature": _text(_content_signature),
    "apparatus-mapping-digest": _rfc8785_digest(canonical_mapping_digest),
    "declared-artifact-digest": _rfc8785_digest(_raes_proposition_truth._declared_artifact_digest),
    "participant-session-id": _participant_session_id,
    "evidence-cut-key": _evidence_cut_key,
    "bundle-identity": _bundle_identity,
    "collector-registration-digest": _collector_registration_digest,
    "correlation-projection": _correlation_projection,
    "trial-plan": _trial_plan,
    "utc-now": _utc_now,
    "continuity-now": _continuity_now,
    "workflow-next-timestamp": _next_timestamp,
    "run-store-id": _run_store_id,
    "workspace-names": _workspace_names,
    "yaml-safe-load": _yaml_loader(yaml.safe_load),
    "yaml-compose-loader": _yaml_loader(
        lambda text: yaml.load(text, Loader=compose_override._ComposeLoader)
    ),
    "experiment-yaml-preflight": _experiment_yaml_preflight,
    "strict-json": _strict_json,
    "seat-launch-bytes": _seat_launch_bytes,
    "seat-policy-digest": _seat_policy_digest,
    "flag-token": _flag_token,
    "parquet-canonical-json": _parquet_canonical_json,
    **OWNER_SCHEMES,
}


def _corpus_files() -> list[Path]:
    return sorted(VECTORS.glob("*.json"))


def _corpus(path: Path) -> dict[str, object]:
    # The Go ports reject a duplicate member, so the corpus has none.
    return loads_strict(path.read_bytes())


def _cases() -> list[tuple[str, str, dict[str, object]]]:
    cases = []
    for path in _corpus_files():
        corpus = _corpus(path)
        for case in corpus["cases"]:
            cases.append((corpus["scheme"], case["id"], case))
    return cases


def test_each_corpus_file_is_well_formed() -> None:
    files = _corpus_files()
    assert files, "the vector corpus is empty"
    for path in files:
        corpus = _corpus(path)
        assert set(corpus) == {"corpus", "scheme", "version", "owner", "cases"}, path.name
        assert corpus["corpus"] == 1, path.name
        assert corpus["scheme"] in SCHEMES, path.name
        assert path.name == f"{corpus['scheme']}.json", path.name
        assert corpus["cases"], path.name
        ids = [case["id"] for case in corpus["cases"]]
        assert len(ids) == len(set(ids)), path.name
        for case in corpus["cases"]:
            # Assert on the member names only: a failure must not print a value.
            fields, expected = set(case), set(case["expect"])
            assert fields <= _CASE_FIELDS, (path.name, case["id"])
            assert len(fields & {"input", "input_hex"}) == 1, (path.name, case["id"])
            assert len(expected) == 1, (path.name, case["id"])
            assert expected <= _EXPECT_FIELDS, (path.name, case["id"])


def _matches(result: object, expect: object) -> bool:
    """Compare as JSON text, which keeps true and 1, and 1.0 and 1, apart."""

    return json.dumps(result, sort_keys=True) == json.dumps(expect, sort_keys=True)


@pytest.mark.parametrize(
    ("scheme", "case_id", "case"),
    _cases(),
    ids=[f"{scheme}/{case_id}" for scheme, case_id, _case in _cases()],
)
def test_vector(scheme: str, case_id: str, case: dict[str, object]) -> None:
    case_input = bytes.fromhex(case["input_hex"]) if "input_hex" in case else _decode(case["input"])
    expect = case["expect"]
    try:
        result = SCHEMES[scheme](case_input)
    except Rejected as rejection:
        result = {"reject": rejection.stage}
    # Compare without an assertion diff: a vector can hold a synthetic secret.
    if not _matches(result, expect):
        pytest.fail(f"{scheme}/{case_id}: the owner result differs from the vector", pytrace=False)


def test_vector_comparison_keeps_json_types_apart() -> None:
    # Python equality treats True as 1 and 1.0 as 1, so it hides a type change.
    assert not _matches({"value": [True, False]}, {"value": [1, 0]})
    assert not _matches({"value": {"a": 1.0}}, {"value": {"a": 1}})
    assert _matches({"value": {"b": 1, "a": [False]}}, {"value": {"a": [False], "b": 1}})


def test_inventory_names_each_vector_file() -> None:
    inventory = INVENTORY.read_text(encoding="utf-8")
    named = set(re.findall(r"`conformance/testdata/vectors/([a-z0-9-]+\.json)`", inventory))
    files = {path.name for path in _corpus_files()}
    assert files - named == set(), "a vector file has no inventory row"
    assert named - files == set(), "an inventory row names a missing vector file"


def test_number_tags_decode_exactly() -> None:
    assert _decode({"$int": "9007199254740993"}) == 9007199254740993
    assert math.copysign(1.0, _decode({"$float": "-0.0"})) == -1.0
    assert math.isnan(_decode({"$float": "nan"}))
