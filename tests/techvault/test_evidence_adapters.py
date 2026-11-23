"""The TechVault capture fleet wires into the generic collector registry (#1700)."""

from __future__ import annotations

import pytest

from aptl.core.evidence.adapters.sources import SourceResult
from aptl.core.evidence.adapters.wiring import build_collectors
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import (
    CollectorRegistry,
)
from aptl_techvault.capture_registrations import BUILTIN_REGISTRATIONS
from tests.test_evidence_adapters import _FakeSource


class TestWiring:
    def test_builds_collectors_for_known_ids(self):
        source = _FakeSource(SourceResult(status=CollectorStatus.EMPTY_OK))
        registry = CollectorRegistry(BUILTIN_REGISTRATIONS)
        collectors = build_collectors(
            {"aptl.collector.mcp-red": source}, registry=registry
        )
        assert (
            collectors["aptl.collector.mcp-red"].registration_id
            == "aptl.collector.mcp-red"
        )

    def test_unknown_registration_id_is_rejected(self):
        source = _FakeSource(SourceResult(status=CollectorStatus.EMPTY_OK))
        with pytest.raises(ValueError, match="unknown collector registration id"):
            build_collectors({"aptl.collector.NOPE": source})

    def test_all_builtins_are_registered(self):
        assert frozenset(
            registration.registration_id
            for registration in BUILTIN_REGISTRATIONS
        ) == frozenset(
            {
                "aptl.collector.mcp-red",
                "aptl.collector.container-logs",
                "aptl.collector.suricata-eve",
                "aptl.collector.wazuh-alerts",
                "aptl.collector.tempo-traces",
                "aptl.collector.misp-authenticated-api-readiness",
                "aptl.collector.redteam-session-transcript",
                "aptl.collector.suricata-rule-readiness",
                "aptl.collector.suricata-wazuh-sqli",
                "aptl.collector.wazuh-agent-readiness",
            }
        )
