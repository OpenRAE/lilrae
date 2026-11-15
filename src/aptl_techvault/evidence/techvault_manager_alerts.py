"""TechVault-owned native reader for the declared Wazuh manager alert log."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import IO

from aptl_techvault.evidence.techvault_native_support import (
    find_node,
    inside_window,
    spool_lines,
    stream_container_file,
)

_TIMESTAMP_FIELD = "@timestamp"
_MANAGER_ALERT_PATH = "/var/ossec/logs/alerts/alerts.json"


@dataclass(frozen=True)
class WazuhManagerAlertRead:
    """Typed result from the single admitted manager-alert source operation."""

    records: tuple[Mapping[str, object], ...] = ()
    loss_category: str | None = None

    @property
    def complete(self) -> bool:
        """Return whether the declared source was read and parsed successfully."""

        return self.loss_category is None


def _parse_alerts(
    spool: IO[bytes], start_iso: str, end_iso: str
) -> WazuhManagerAlertRead:
    """Parse the complete NDJSON log, tolerating only a torn final line."""

    normalized: list[Mapping[str, object]] = []
    loss: str | None = None
    for line, terminated in spool_lines(spool):
        try:
            source = json.loads(line)
        except json.JSONDecodeError:
            if terminated:
                loss = "source-ndjson-malformed"
                break
            continue
        if not isinstance(source, Mapping):
            loss = "source-record-invalid"
            break
        item = dict(source)
        item["timestamp"] = source.get("timestamp", source.get(_TIMESTAMP_FIELD))
        if inside_window(item["timestamp"], start_iso, end_iso):
            normalized.append(item)
    records = tuple(normalized) if loss is None else ()
    return WazuhManagerAlertRead(records=records, loss_category=loss)


def read_wazuh_manager_alerts(
    backend: object,
    realization: object,
    start_iso: str,
    end_iso: str,
) -> WazuhManagerAlertRead:
    """Read the complete NDJSON log of the realization-declared manager."""

    manager = find_node(realization, "wazuh-manager")
    container = getattr(manager, "container_name", None)
    result = WazuhManagerAlertRead(loss_category="declared-manager-unavailable")
    if isinstance(container, str) and container:
        spool, loss = stream_container_file(backend, container, _MANAGER_ALERT_PATH)
        if spool is None:
            return WazuhManagerAlertRead(loss_category=loss)
        with spool:
            result = _parse_alerts(spool, start_iso, end_iso)
    return result


__all__ = ["WazuhManagerAlertRead", "read_wazuh_manager_alerts"]
