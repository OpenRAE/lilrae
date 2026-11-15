"""Per-outcome persistence for the acquisition coordinator (EXP-010 / #752).

Split out of :mod:`aptl.core.evidence.coordinator` to keep that module within
the 500-line budget and its orchestration readable. This module owns the
coordinator-side work for one captured outcome, including failed partial data: the
media-type check, structured redaction, streamed content-addressed
persistence, and RAES evidence-record + reference assembly.
A collector never does any of this itself (preflight "Narrow collector
boundary").
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from raes_contracts.contracts import ExperimentEvidenceRecordModel

from aptl.core.evidence import content_store
from aptl.core.evidence.outcomes import (
    ABORTING_STATUSES,
    SUCCESS_STATUSES,
    AcquisitionPhase,
    CollectorStatus,
)
from aptl.core.evidence.protocol import CollectorOutcome
from aptl.core.evidence.records import (
    RecordDisclosure,
    RecordScope,
    build_evidence_record,
)
from aptl.core.experiment.capture_registry import CaptureBinding
from aptl.core.evidence._stream_prepare import (
    JSON_MEDIA_TYPE as _JSON_MEDIA_TYPE,
    TEXT_MEDIA_TYPE as _TEXT_MEDIA_TYPE,
    prepare_stream,
)
from aptl.core.runstore import LocalRunStore

#: Redaction policies with a trusted handler. APTL's shared recursive redactor
#: serves both. They are named explicitly so an unknown policy can never be
#: treated as either one by a truthy boolean conversion.
_REDACTION_POLICIES = frozenset({"redact_secrets", "redact_sensitive"})

#: Run-relative subdirectory for content-addressed raw evidence blobs.
_EVIDENCE_SUBDIR = "evidence/blobs"

#: Run-relative subdirectory for the explicit, create-once evidence-record ledger.
_LEDGER_SUBDIR = "evidence/records"


@dataclass(frozen=True)
class EvidenceRef:
    """A verified evidence reference for the run / #447 correlation projection.

    Carries only bounded identity — record/content identity, the capture
    spec/requirement it satisfies, the producing registration, and the
    visibility class — never raw bytes or a host path.
    """

    evidence_record_id: str
    content_uri: str
    content_digest: str
    capture_spec_id: str
    requirement_id: str
    registration_id: str
    visibility_class: str
    run_id: str = ""
    planned_trial_id: str = ""
    attempt_id: str | None = None

    def as_reference_dict(self) -> dict[str, str]:
        """Project to the ``backend_evidence.evidence_references`` shape OBS-002 consumes."""
        return {
            "path": self.content_uri,
            "kind": "experiment-evidence",
            "evidence_record_id": self.evidence_record_id,
            "digest": self.content_digest,
            "requirement_id": self.requirement_id,
            "visibility_class": self.visibility_class,
            **(
                {
                    "run_id": self.run_id,
                    "planned_trial_id": self.planned_trial_id,
                    "attempt_id": self.attempt_id,
                }
                if self.attempt_id is not None
                else {}
            ),
        }


@dataclass(frozen=True)
class ProcessedOutcome:
    """The result of persisting one success outcome.

    ``effective_status`` may downgrade the collector's reported status, for
    example to :attr:`CollectorStatus.MID_RUN_LOSS` when the source reports
    dropped events.
    """

    record: ExperimentEvidenceRecordModel
    ref: EvidenceRef
    effective_status: CollectorStatus


def _media_type_of(outcome: CollectorOutcome, binding: CaptureBinding) -> str:
    """Return the effective media type (collector-reported, else the binding's first expected)."""
    if outcome.media_type is not None:
        return outcome.media_type
    return (
        binding.expected_media_types[0]
        if binding.expected_media_types
        else "application/octet-stream"
    )


def media_type_supported(outcome: CollectorOutcome, binding: CaptureBinding) -> bool:
    """Return whether the outcome's media type is one the requirement expects."""
    if not binding.expected_media_types:
        return True
    return _media_type_of(outcome, binding) in binding.expected_media_types


def _prepared_chunks(
    outcome: CollectorOutcome, media_type: str, binding: CaptureBinding
) -> Iterable[bytes]:
    """Return the complete stream to persist, redacted when the binding asks."""
    if binding.redaction_required and binding.redaction_policy not in _REDACTION_POLICIES:
        raise ValueError("capture redaction policy has no trusted handler")
    return prepare_stream(
        outcome.chunks, media_type, redacted=binding.redaction_required
    )


def persist_success_outcome(
    *,
    binding: CaptureBinding,
    outcome: CollectorOutcome,
    run_store: LocalRunStore,
    run_id: str,
    planned_trial_id: str,
    attempt_id: str | None = None,
    phase: AcquisitionPhase | None = None,
) -> ProcessedOutcome:
    """Persist one captured outcome content-addressably and build its RAES record.

    Streams the complete content to the run store, redacting structured
    payloads only when the binding applies a redaction policy, and derives a
    deterministic evidence-record identity. Evaluator-only references stay
    excluded from participant projections. The record's capture time is the
    collector's observed finish time.
    """
    captured_at = outcome.finished_at
    media_type = _media_type_of(outcome, binding)
    content = content_store.create_content_addressed(
        run_store,
        run_id,
        _prepared_chunks(outcome, media_type, binding),
        subdir=_EVIDENCE_SUBDIR,
    )
    effective_status = _effective_status(outcome)

    # A binding that applies a redaction policy records that policy, so its
    # state is "redacted" even when the policy changed no bytes. RAES rejects
    # a record with a policy and the state "none".
    redaction_state = "redacted" if binding.redaction_policy else "none"
    loss_disclosure = _loss_disclosure(
        outcome, effective_status=effective_status, redaction_state=redaction_state
    )

    record = build_evidence_record(
        binding=binding,
        scope=RecordScope(run_id, planned_trial_id, attempt_id),
        content=content,
        outcome=outcome,
        captured_at=captured_at,
        disclosure=RecordDisclosure(
            sensitivity=_record_sensitivity(binding.sensitivity),
            redaction_state=redaction_state,
            loss_disclosure=loss_disclosure,
        ),
        phase=phase,
    )
    # Persist the record into the explicit, create-once run-scoped evidence
    # ledger (identity is content-derived, so re-persisting is idempotent).
    content_store.create_run_json_once(
        run_store,
        run_id,
        f"{_LEDGER_SUBDIR}/{record.evidence_record_id}.json",
        record.model_dump(mode="json", exclude_none=True),
    )
    ref = EvidenceRef(
        evidence_record_id=record.evidence_record_id,
        content_uri=content.relative_path,
        content_digest=content.digest,
        capture_spec_id=binding.capture_spec_id,
        requirement_id=binding.requirement_id,
        registration_id=binding.registration_id,
        visibility_class=binding.visibility_class.value,
        run_id=run_id,
        planned_trial_id=planned_trial_id,
        attempt_id=attempt_id,
    )
    return ProcessedOutcome(record=record, ref=ref, effective_status=effective_status)


def _failure_fact_blob(
    binding: CaptureBinding, status: CollectorStatus, effect: str
) -> tuple[str, bytes]:
    """Render core-owned failure facts in a media type the binding retains."""
    expected = binding.expected_media_types
    if expected and _JSON_MEDIA_TYPE not in expected and _TEXT_MEDIA_TYPE in expected:
        text = f"status={status.value}; observer_effect={effect}"
        return _TEXT_MEDIA_TYPE, text.encode("utf-8")
    facts = {"status": status.value, "observer_effect": effect}
    return _JSON_MEDIA_TYPE, json.dumps(facts, separators=(",", ":")).encode("utf-8")


def retained_failure_outcome(
    outcome: CollectorOutcome,
    binding: CaptureBinding,
    phase: AcquisitionPhase | None,
) -> CollectorOutcome:
    """Give a top-level content-free non-aborting failure a durable facts blob.

    A preparation operation that ran and then failed may have changed state,
    even when the source supplied no observer-effect string. Absence of effect
    text cannot establish absence of an effect, so a preparation failure retains
    bounded core-owned facts (status and observer effect, "unknown" when absent).
    A measurement is observe-only, so it retains a fact only when it reports an
    observer effect, which is itself a contract violation worth recording; a
    failed observation that reports no effect keeps no evidence reference, which
    preserves the delivery contract (issue #963). An aborting status (a source
    that never started) and an outcome that already carries content are left
    unchanged. The coordinator calls this once per binding before persistence,
    so the persistence-failure path keeps the fail-closed policy that never
    manufactures evidence from content that could not be safely retained.
    """
    if (
        outcome.status in SUCCESS_STATUSES
        or outcome.chunks
        or outcome.status in ABORTING_STATUSES
    ):
        return outcome
    if phase is not AcquisitionPhase.PREPARATION and outcome.observer_effect is None:
        return outcome
    effect = outcome.observer_effect or "unknown"
    media, blob = _failure_fact_blob(binding, outcome.status, effect)
    return CollectorOutcome(
        status=outcome.status,
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        chunks=(blob,),
        media_type=media,
        event_count=1,
        dropped_count=outcome.dropped_count,
        source_min_time=outcome.source_min_time,
        source_max_time=outcome.source_max_time,
        observer_effect=effect,
        detail=outcome.detail,
        source_pipeline=outcome.source_pipeline,
    )


#: Fixed disclosure text per non-``none`` redaction state (RAES requires a
#: disclosure whenever the record is redacted or withheld).
_REDACTION_DISCLOSURES = {
    "withheld": "content withheld from participant projection (evaluator-only/apparatus-only visibility)",
    "redacted": "payload redacted at the persistence boundary (ADR-029)",
}

#: Disclosure text per limit/loss status the coordinator enforces. ``{dropped}``
#: is filled from the outcome's dropped-event count.
_STATUS_DISCLOSURES = {
    CollectorStatus.MID_RUN_LOSS: "{dropped} event(s) dropped mid-run",
}

# Capture-demand sensitivity and evidence-record sensitivity are different
# governed vocabularies. ``plain`` means the retained payload is not marked
# sensitive; the portable evidence record expresses that as ``public``.
_RECORD_SENSITIVITY = {
    "plain": "public",
    "public": "public",
    "internal": "internal",
    "restricted": "restricted",
    "redacted": "redacted",
}


def _record_sensitivity(value: str) -> str:
    """Map an admitted capture sensitivity to the portable record vocabulary."""

    try:
        return _RECORD_SENSITIVITY[value]
    except KeyError as exc:
        raise ValueError("unsupported evidence-record sensitivity") from exc


def _effective_status(outcome: CollectorOutcome) -> CollectorStatus:
    """Downgrade a reported OK to ``MID_RUN_LOSS`` when the source dropped events.

    A dropped-event capture is never silently OK or seal-ready.
    """
    return CollectorStatus.MID_RUN_LOSS if outcome.dropped_count > 0 else outcome.status


def _loss_disclosure(
    outcome: CollectorOutcome,
    *,
    effective_status: CollectorStatus,
    redaction_state: str,
) -> str | None:
    """Return a mandatory, bounded loss/redaction disclosure, or ``None`` when there is nothing to disclose.

    A limit/loss status (timeout, truncation, mid-run loss) always discloses;
    otherwise a redacted/withheld record discloses; a lossless, un-redacted,
    participant-visible record needs none.
    """
    if outcome.status not in {CollectorStatus.OK, CollectorStatus.EMPTY_OK}:
        return (
            f"collector status {outcome.status.value}; partial capture retained; "
            f"{outcome.dropped_count} event(s) dropped"
        )
    status_text = _STATUS_DISCLOSURES.get(effective_status)
    if status_text is not None:
        return status_text.format(dropped=outcome.dropped_count)
    return _REDACTION_DISCLOSURES.get(redaction_state)
