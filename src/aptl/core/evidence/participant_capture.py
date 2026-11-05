"""Protected, attempt-scoped participant source records and honest accounting."""

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from aptl.core.evidence.adapters.sources import SourceResult
from aptl.core.evidence._participant_tools import (
    aggregate_tool_calls,
    tool_sequence_complete,
)
from aptl.core.evidence._bounded_json import capture_prefix as _capture_prefix
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.protocol import RunScope
from aptl.core.experiment.capture_registry import (
    CaptureBinding,
    CaptureLimits,
    CaptureVisibility,
    CollectorRegistration,
)
from raes_backend_protocols.capabilities import ObservationCaptureOffer
from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import (
    PathContainmentError,
    REASON_NOT_FOUND,
    listdir_contained_nofollow,
    open_contained_nofollow,
)
from aptl.core.evidence._participant_calls import aggregate_model_calls
from aptl.utils.redaction import redact
from aptl.utils.strict_json import loads_strict

_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_FILE = re.compile(r"[a-f0-9]{64}\.json\Z")
_JSON_SUFFIX = ".json"
_CAPTURE_SCHEMA = "lilrae.participant-capture/v1"


def _capture_limits_supported(limits: CaptureLimits) -> bool:
    """Check the implemented byte, artifact, and duration bounds without coercion."""
    bounded = (
        (limits.max_bytes, 4096, 64 * 1024 * 1024),
        (limits.max_artifact_count, 1, 4096),
    )
    return (
        all(type(value) is int and low <= value <= high for value, low, high in bounded)
        and type(limits.max_duration_s) is int
        and limits.max_duration_s >= 1
    )


def participant_capture_registration(
    registration_id: str,
    offer: ObservationCaptureOffer,
    *,
    limits: CaptureLimits = CaptureLimits(8 * 1024 * 1024, 4096, 3600),
) -> CollectorRegistration:
    """Declare the participant source this backend actually implements.

    The selected adapter supplies its source/role/channel identifiers. This
    declaration covers raw capture records, without study interpretation or
    stronger integrity and post-handoff retention promises.
    """
    expected = {
        "output_contract": "experiment-evidence-record-v1",
        "field_selectors": ("",),
        "window_kinds": frozenset({"run"}),
        "media_types": frozenset({"application/json"}),
        "redaction_policy": "redact_secrets",
        "channel_kinds": frozenset({"participant-observation"}),
        "source_classes": frozenset({"apparatus"}),
        "scopes": frozenset({"participant"}),
        "export_policy": "not-required",
    }
    if not all(getattr(offer, key) == value for key, value in expected.items()):
        raise ValueError("participant capture offer is unsupported")
    supported = (
        offer.sensitivity in {"internal", "restricted", "redacted"},
        offer.integrity_modes <= {"none", "checksum", "sha256-digest"},
        offer.retention_policy_refs <= {"run_lifetime"},
        _capture_limits_supported(limits),
    )
    if not all(supported):
        raise ValueError("participant capture offer is unsupported")
    return CollectorRegistration(
        registration_id=registration_id,
        implementation_version="1.0.0",
        contract_version="experiment-capture-spec/v1",
        channel_kind="participant-observation",
        capture_kind=offer.capture_kind,
        capture_scope="participant",
        window_kinds=offer.window_kinds,
        media_types=offer.media_types,
        required_artifact_roles=offer.artifact_roles,
        supported_sensitivities=frozenset({offer.sensitivity}),
        supports_redaction=True,
        integrity_modes=offer.integrity_modes,
        sealing_modes=frozenset({"digest"}),
        supports_chain_of_custody=False,
        supports_retention=True,
        supports_loss_disclosure=True,
        visibility_class=CaptureVisibility.EVALUATOR_ONLY,
        limits=limits,
        redaction_policies=frozenset({"redact_secrets"}),
        retention_policies=offer.retention_policy_refs,
        capture_offer=offer,
    )


@dataclass(frozen=True)
class ParticipantCaptureGrant:
    """Content authority composed from an admitted protected binding and trial."""

    binding: CaptureBinding
    scope: RunScope
    participant_address: str
    capture_spec_version: str
    configuration_digest: str

    def __post_init__(self) -> None:
        if (
            self.binding.visibility_class
            not in {CaptureVisibility.EVALUATOR_ONLY, CaptureVisibility.APPARATUS_ONLY}
            or not self.binding.redaction_required
            or self.binding.redaction_policy != "redact_secrets"
            or self.binding.sensitivity not in {"internal", "restricted", "redacted"}
            or "application/json" not in self.binding.expected_media_types
            or any(
                not isinstance(value, str) or not _IDENTITY.fullmatch(value)
                for value in (
                    self.scope.run_id,
                    self.scope.attempt_id,
                    self.scope.planned_trial_id,
                    self.participant_address,
                    self.capture_spec_version,
                )
            )
            or any(
                not isinstance(value, str)
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", value)
                for value in (self.configuration_digest,)
            )
        ):
            raise ValueError("participant content capture is not admitted")

    def identity(self) -> dict[str, str]:
        return {
            "run_id": self.scope.run_id,
            "attempt_id": self.scope.attempt_id,
            "planned_trial_id": self.scope.planned_trial_id,
            "participant_address": self.participant_address,
            "capture_spec_id": self.binding.capture_spec_id,
            "capture_spec_version": self.capture_spec_version,
            "capture_requirement_id": self.binding.requirement_id,
            "configuration_digest": self.configuration_digest,
        }


class ParticipantCaptureArchive:
    """One native source owner; the plugin receives no archive authority."""

    def __init__(self, store: LocalRunStore, grant: ParticipantCaptureGrant) -> None:
        self.store, self.grant = store, grant
        self._tool_write_failed = False
        participant = hashlib.sha256(grant.participant_address.encode()).hexdigest()
        attempt = hashlib.sha256(grant.scope.attempt_id.encode()).hexdigest()
        self._relative = Path("evaluator/participant-capture") / attempt / participant
        self._intents_relative = (
            Path("evaluator/participant-capture-intents") / attempt / participant
        )
        self._tools_relative = (
            Path("evaluator/participant-tool-capture") / attempt / participant
        )

    def record_tool_event(self, payload: Mapping[str, object]) -> None:
        """A failed observation write makes subsequent collection incomplete."""
        try:
            self._record_tool_event(payload)
        except Exception:
            self._tool_write_failed = True
            raise

    def _record_tool_event(self, payload: Mapping[str, object]) -> None:
        """Retain the runtime event under its actual participant and generation."""
        if payload.get("participant_address") != self.grant.participant_address:
            raise ValueError("tool capture belongs to another participant")
        invocation, ordinal = payload.get("invocation_id"), payload.get("sequence")
        if (
            not isinstance(invocation, str)
            or not _IDENTITY.fullmatch(invocation)
            or type(ordinal) is not int
            or not 0 <= ordinal < 65536
        ):
            raise ValueError("tool capture identity is invalid")
        identity = hashlib.sha256(f"{invocation}:{ordinal}".encode()).hexdigest()
        record = {
            **redact(dict(payload)),
            **self.grant.identity(),
            "schema": "lilrae.participant-tool-capture/v1",
        }
        if (
            len(json.dumps(record, allow_nan=False).encode())
            > self.grant.binding.limits.max_bytes
        ):
            raise BufferError("tool capture exceeds its admitted bound")
        self.store.create_run_json_once(
            self.grant.scope.run_id,
            (self._tools_relative / f"{identity}.json").as_posix(),
            record,
        )

    def expect_invocation(self, invocation: str) -> None:
        """Record membership before provider effects; an unpublished result stays missing."""
        if not isinstance(invocation, str) or not _IDENTITY.fullmatch(invocation):
            raise ValueError("participant capture invocation is invalid")
        name = hashlib.sha256(invocation.encode()).hexdigest() + _JSON_SUFFIX
        self.store.create_run_json_once(
            self.grant.scope.run_id,
            (self._intents_relative / name).as_posix(),
            {**self.grant.identity(), "invocation_id": invocation},
        )

    def record(self, payload: Mapping[str, object]) -> None:
        """Publish safe source data once before the harness's private state goes."""
        invocation = payload.get("invocation_id")
        if not isinstance(invocation, str) or not _IDENTITY.fullmatch(invocation):
            raise ValueError("participant capture invocation is invalid")
        self.expect_invocation(invocation)
        safe = redact(dict(payload))
        record = {
            **safe,
            **self.grant.identity(),
            "schema": _CAPTURE_SCHEMA,
            "tool_observation_write_failed": self._tool_write_failed,
        }
        encoded = json.dumps(record, allow_nan=False).encode()
        if len(encoded) > self.grant.binding.limits.max_bytes:
            record = _capture_prefix(
                record,
                {
                    **self.grant.identity(),
                    "schema": _CAPTURE_SCHEMA,
                    "tool_observation_write_failed": self._tool_write_failed,
                    "invocation_id": invocation,
                    "calls": [],
                    "records": [],
                    "harness_failure_reason": record.get("harness_failure_reason"),
                    "prompt_delivery": record.get("prompt_delivery"),
                },
                self.grant.binding.limits.max_bytes // 2,
            )
        name = hashlib.sha256(invocation.encode()).hexdigest() + _JSON_SUFFIX
        self.store.create_run_json_once(
            self.grant.scope.run_id, (self._relative / name).as_posix(), record
        )

    def _read_names(self, root: Path, optional: bool) -> tuple[list[str], bool]:
        """Distinguish an absent optional source from an unreadable archive."""
        missing = False
        try:
            names = listdir_contained_nofollow(self.store.base_dir, root)
        except (OSError, PathContainmentError) as exc:
            absent = isinstance(exc, FileNotFoundError)
            if isinstance(exc, PathContainmentError):
                absent = absent or exc.reason == REASON_NOT_FOUND
            names = []
            missing = not optional or not absent
        return names, missing

    def _read_bytes(self, root: Path, name: str, remaining: int) -> bytes:
        """Refuse unexpected filenames and read within the remaining archive quota."""
        if not _FILE.fullmatch(name):
            raise ValueError("participant capture filename is invalid")
        with open_contained_nofollow(self.store.base_dir, root / name) as stream:
            return stream.read(remaining + 1)

    @staticmethod
    def _validate_payload(record: dict[str, object], tool: bool) -> None:
        """Validate one measurement independently of later malformed archive rows."""
        if tool:
            if (
                type(record.get("monotonic_ns")) is not int
                or record["monotonic_ns"] < 0
            ):
                raise ValueError("tool capture clock is invalid")
            aggregate_tool_calls((record,))
        else:
            aggregate_model_calls((record,))

    def _validate_record(
        self, data: bytes, name: str, optional: bool, intent: bool
    ) -> dict[str, object]:
        """Require exact trial membership and stable invocation or tool-event identity."""
        record = loads_strict(data)
        if not isinstance(record, dict) or any(
            record.get(key) != value for key, value in self.grant.identity().items()
        ):
            raise ValueError("participant capture belongs to another trial")
        invocation = record.get("invocation_id")
        if not isinstance(invocation, str):
            raise ValueError("participant capture identity is unavailable")
        identity = (
            f"{invocation}:{record['sequence']}"
            if optional and not intent
            else invocation
        )
        if name != hashlib.sha256(identity.encode()).hexdigest() + _JSON_SUFFIX:
            raise ValueError("participant capture identity changed")
        if not intent:
            self._validate_payload(record, optional)
        return record

    def _read(
        self, relative: Path, *, optional: bool = False, intent: bool = False
    ) -> tuple[list[dict[str, object]], bool]:
        """Retain independent valid rows while enforcing the cumulative source bounds."""
        root = Path(self.grant.scope.run_id) / relative
        names, missing = self._read_names(root, optional)
        maximum = self.grant.binding.limits.max_artifact_count
        missing |= len(names) > maximum or (not names and not optional)
        remaining = self.grant.binding.limits.max_bytes
        records = []
        for name in sorted(names)[:maximum]:
            try:
                data = self._read_bytes(root, name, remaining)
                remaining -= len(data)
                if remaining < 0:
                    missing = True
                    break
                records.append(self._validate_record(data, name, optional, intent))
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                PathContainmentError,
            ):
                missing = True
        return records, missing

    @staticmethod
    def _invocation_totals(
        invocations: list[dict[str, object]], missing: bool
    ) -> dict[str, object]:
        """Keep known subtotals while withholding complete totals after a membership gap."""
        totals = aggregate_model_calls(invocations)
        if missing:
            for flag in (
                "membership_complete",
                "required_usage_complete",
                "input_tokens_complete",
                "output_tokens_complete",
                "billing_complete",
            ):
                totals[flag] = False
            for key in ("call_count", "input_tokens", "output_tokens", "cost"):
                totals[key] = None
        return totals

    def _action_counts(
        self,
        invocations: list[dict[str, object]],
        tools: list[dict[str, object]],
        missing: bool,
    ) -> tuple[dict[str, object], bool]:
        """Disclose sticky write failures and sequence gaps separately from known counts."""
        tools.sort(
            key=lambda row: (row["monotonic_ns"], row["invocation_id"], row["sequence"])
        )
        counts = aggregate_tool_calls(tools)
        missing |= (
            self._tool_write_failed
            or any(
                row.get("tool_observation_write_failed") is True for row in invocations
            )
            or not tool_sequence_complete(tools)
        )
        if missing:
            counts = {**dict.fromkeys(counts), "known_counts": counts}
        return counts, missing

    def _collect(self) -> SourceResult:
        """Build the bounded participant artifact from this attempt's accepted sources."""
        invocations, missing = self._read(self._relative)
        expected, intent_missing = self._read(
            self._intents_relative, optional=True, intent=True
        )
        missing |= intent_missing or {row["invocation_id"] for row in expected} != {
            row["invocation_id"] for row in invocations
        }
        tools, tools_missing = self._read(self._tools_relative, optional=True)
        if not invocations and not tools:
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        totals = self._invocation_totals(invocations, missing)
        counts, tools_missing = self._action_counts(invocations, tools, tools_missing)
        truncated = any(row.get("truncated") is True for row in invocations)
        complete = all(
            (
                not missing,
                not truncated,
                not tools_missing,
                totals["membership_complete"],
                totals["required_usage_complete"],
                not counts["in_flight"],
                not counts["unsettled"],
            )
        )
        records = [
            {
                **self.grant.identity(),
                "invocations": invocations,
                "totals": totals,
                "tool_events": tools,
                "tool_capture_complete": not tools_missing,
                "action_counts": counts,
            }
        ]
        if (
            len(json.dumps(records, separators=(",", ":")).encode())
            > self.grant.binding.limits.max_bytes
        ):
            records = [
                _capture_prefix(
                    records[0],
                    self.grant.identity(),
                    self.grant.binding.limits.max_bytes,
                )
            ]
            truncated = True
        status = CollectorStatus.OK if complete else CollectorStatus.MID_RUN_LOSS
        if truncated:
            status = CollectorStatus.TRUNCATION
        return SourceResult(
            status=status,
            records=records,
            source_pipeline={"contract": _CAPTURE_SCHEMA, **self.grant.identity()},
        )

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        """Read this exact attempt; optional billing never changes capture status."""
        del start_iso, end_iso
        try:
            return self._collect()
        except BufferError:
            return SourceResult(status=CollectorStatus.TRUNCATION)
        except OSError, ValueError, KeyError, TypeError, PathContainmentError:
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
