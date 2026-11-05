"""Adapter-owned native sources for the released TechVault evidence demands."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from aptl.core.evidence.adapters.sources import SourceResult
from aptl_techvault.evidence.techvault_transcript import (
    RedteamSessionTranscriptSource,
    TranscriptFrame,
    TranscriptSession,
    transcript_chain_digest,
)
from aptl_techvault.evidence.techvault_readiness import (
    TECHVAULT_LOCAL_SIDS,
    SuricataRuleReadinessSource,
)
from aptl.core.evidence.outcomes import CollectorStatus

SQLI_PROBE_SOURCE_IP = "172.20.1.30"  # NOSONAR S1313: admitted synthetic lab IP
SURICATA_SQLI_SID = 1000010
WAZUH_SQLI_RULE_ID = "303020"
_MAX_NATIVE_JSON_BYTES = 2 * 1024 * 1024
_UTC_OFFSET = "+00:00"


def _bounded_json(value: object) -> bytes | None:
    """Encode one native response only when it fits the admitted byte bound."""

    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError, RecursionError):
        return None
    return raw if len(raw) <= _MAX_NATIVE_JSON_BYTES else None


def _failure(status: CollectorStatus = CollectorStatus.MID_RUN_LOSS) -> SourceResult:
    """Build a source result that retains no unvalidated native payload."""

    return SourceResult(status=status)


class SuricataWazuhSqliSource:
    """Generate a fresh fixed probe and require exact flow-lineage correlation."""

    def __init__(
        self,
        trigger: Callable[[], Mapping[str, object] | None],
        query_suricata: Callable[[str, str], Sequence[Mapping[str, object]] | None],
        query_wazuh: Callable[[str, str], Sequence[Mapping[str, object]] | None],
        *,
        poll_attempts: int = 1,
        poll_interval_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind the trigger and two native alert-query owners."""

        self._trigger = trigger
        self._query_suricata = query_suricata
        self._query_wazuh = query_wazuh
        self._poll_attempts = max(1, poll_attempts)
        self._poll_interval_seconds = max(0.0, poll_interval_seconds)
        self._sleep = sleep

    def fetch(self, start_iso: str, end_iso: str) -> SourceResult:
        trigger = self._trigger()
        if trigger is None or not _valid_trigger(trigger, start_iso, end_iso):
            return _failure(CollectorStatus.SOURCE_UNAVAILABLE)
        pair, unavailable = self._poll_pair(trigger, end_iso)
        if pair is None:
            status = (
                CollectorStatus.SOURCE_UNAVAILABLE
                if unavailable
                else CollectorStatus.MID_RUN_LOSS
            )
            return _failure(status)
        return _sqli_result(trigger, pair)

    def _poll_pair(
        self, trigger: Mapping[str, object], end_iso: str
    ) -> tuple[
        tuple[Mapping[str, object], Mapping[str, object]] | None,
        bool,
    ]:
        """Poll both native stores for one exact correlated alert pair."""

        pair = None
        unavailable = False
        for attempt in range(self._poll_attempts):
            suricata = self._query_suricata(str(trigger["triggered_at"]), end_iso)
            wazuh = self._query_wazuh(str(trigger["triggered_at"]), end_iso)
            if suricata is None or wazuh is None:
                unavailable = True
            else:
                pair = _exact_correlated_pair(trigger, suricata, wazuh, end_iso)
            if pair is not None:
                break
            if attempt + 1 < self._poll_attempts and self._poll_interval_seconds:
                self._sleep(self._poll_interval_seconds)
        return pair, unavailable


def _sqli_result(
    trigger: Mapping[str, object],
    pair: tuple[Mapping[str, object], Mapping[str, object]],
) -> SourceResult:
    """Project one correlated native alert pair into portable NDJSON."""

    suricata_event, wazuh_event = pair
    rows = (
        _sqli_projection("suricata", trigger, suricata_event),
        _sqli_projection("wazuh", trigger, wazuh_event),
    )
    document = {
        "schema_version": "aptl-techvault-sqli-correlation/v1",
        "records": list(rows),
    }
    return SourceResult(
        status=CollectorStatus.OK,
        records=list(rows),
        chunks=(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode(),
        ),
        media_type="application/json",
        source_min_time=str(suricata_event["timestamp"]),
        source_max_time=str(wazuh_event["timestamp"]),
        observer_effect="one fixed POST /login containing UNION SELECT",
        source_pipeline={
            "source_refs": [
                {
                    "ref_kind": "other",
                    "ref_id": (
                        "nodes.suricata.runtime.network_detection_engines."
                        "suricata-engine.output_streams.eve-json"
                    ),
                },
                {
                    "ref_kind": "other",
                    "ref_id": (
                        "nodes.wazuh-manager.runtime.security_monitoring_managers."
                        "wazuh-manager.content_sets.suricata-rules"
                    ),
                },
            ],
            "correlation": "shared-suricata-flow-id",
        },
    )


def _valid_trigger(trigger: Mapping[str, object], start_iso: str, end_iso: str) -> bool:
    """Validate the fixed probe identity, shape, and time bound."""

    return (
        bool(trigger.get("trigger_id"))
        and trigger.get("method") == "POST"
        and trigger.get("path") == "/login"
        and trigger.get("source_ip") == SQLI_PROBE_SOURCE_IP
        and bool(trigger.get("destination_ip"))
        and trigger.get("contains_union_select") is True
        and _inside_window(trigger.get("triggered_at"), start_iso, end_iso)
    )


def _exact_correlated_pair(
    trigger: Mapping[str, object],
    suricata: Sequence[Mapping[str, object]],
    wazuh: Sequence[Mapping[str, object]],
    end_iso: str,
) -> tuple[Mapping[str, object], Mapping[str, object]] | None:
    """Return exactly one pair joined by flow identity, or no evidence."""

    start_iso = str(trigger["triggered_at"])
    sensor = [
        event
        for event in suricata
        if _suricata_sid(event) == SURICATA_SQLI_SID
        and _event_matches_trigger(event, trigger, start_iso, end_iso)
    ]
    manager = [
        event
        for event in wazuh
        if _wazuh_rule_id(event) == WAZUH_SQLI_RULE_ID
        and _embedded_suricata_sid(event) == SURICATA_SQLI_SID
        and _event_matches_trigger(event, trigger, start_iso, end_iso)
    ]
    pairs = [
        (left, right)
        for left in sensor
        for right in manager
        if _canonical_flow_id(left.get("flow_id"))
        and _canonical_flow_id(left.get("flow_id"))
        == _canonical_flow_id(_nested(right, "data", "flow_id"))
    ]
    return pairs[0] if len(pairs) == 1 else None


def _event_matches_trigger(
    event: Mapping[str, object],
    trigger: Mapping[str, object],
    start_iso: str,
    end_iso: str,
) -> bool:
    """Bind an event to the probe endpoints and acquisition window."""

    source = event.get("src_ip", _nested(event, "data", "src_ip"))
    destination = event.get("dest_ip", _nested(event, "data", "dest_ip"))
    return (
        source == trigger["source_ip"]
        and destination == trigger["destination_ip"]
        and _inside_window(event.get("timestamp"), start_iso, end_iso)
    )


def _sqli_projection(
    source: str,
    trigger: Mapping[str, object],
    event: Mapping[str, object],
) -> dict[str, object]:
    """Project only the correlated fields required by the evidence contract."""

    flow_id = _canonical_flow_id(
        event.get("flow_id", _nested(event, "data", "flow_id"))
    )
    return {
        "source": source,
        "trigger_id": trigger["trigger_id"],
        "timestamp": event["timestamp"],
        "flow_id": flow_id,
        "source_ip": trigger["source_ip"],
        "destination_ip": trigger["destination_ip"],
        "suricata_signature_id": SURICATA_SQLI_SID,
        "wazuh_rule_id": WAZUH_SQLI_RULE_ID,
    }


def _nested(value: Mapping[str, object], *keys: str) -> object:
    """Read a bounded mapping path without accepting non-mapping intermediates."""

    current: object = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _canonical_flow_id(value: object) -> str:
    """Canonicalize Wazuh's lossless decimal rendering of an integer flow ID."""

    text = str(value)
    whole, separator, fraction = text.partition(".")
    if separator and fraction and not fraction.strip("0"):
        text = whole
    return text if text.isdecimal() else ""


def _suricata_sid(event: Mapping[str, object]) -> int | None:
    """Read a Suricata signature identifier as an integer."""

    value = _nested(event, "alert", "signature_id")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _embedded_suricata_sid(event: Mapping[str, object]) -> int | None:
    """Read the Suricata signature embedded in a Wazuh event."""

    value = _nested(event, "data", "alert", "signature_id")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _wazuh_rule_id(event: Mapping[str, object]) -> str:
    """Read a Wazuh rule identifier as text."""

    return str(_nested(event, "rule", "id") or "")


def _inside_window(value: object, start_iso: str, end_iso: str) -> bool:
    """Return whether an ISO timestamp lies inside the closed capture window."""

    try:
        instant = datetime.fromisoformat(str(value).replace("Z", _UTC_OFFSET))
        start = datetime.fromisoformat(start_iso.replace("Z", _UTC_OFFSET))
        end = datetime.fromisoformat(end_iso.replace("Z", _UTC_OFFSET))
    except (TypeError, ValueError):
        return False
    return start <= instant <= end


__all__ = (
    "RedteamSessionTranscriptSource",
    "SQLI_PROBE_SOURCE_IP",
    "SuricataRuleReadinessSource",
    "SuricataWazuhSqliSource",
    "TECHVAULT_LOCAL_SIDS",
    "TranscriptFrame",
    "TranscriptSession",
    "transcript_chain_digest",
)
