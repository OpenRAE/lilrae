"""Native owner tests for the released TechVault evidence contracts."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from aptl_techvault.evidence import techvault_native

from aptl.core.deployment.realization import (
    DeploymentPublishedPort,
    DeploymentServicePort,
)
from aptl_techvault.evidence.techvault import TECHVAULT_LOCAL_SIDS
from aptl_techvault.evidence.techvault_native import (
    TechVaultNativeDependencies,
    TechVaultNativeEvidenceOwner,
)
from aptl.core.evidence.outcomes import CollectorStatus

_START = "2026-09-14T10:00:00Z"
_TRIGGER = "2026-09-14T10:00:05Z"
_FINISH = "2026-09-14T10:00:10Z"
_END = "2026-09-14T10:01:00Z"
_DIGEST = "sha256:" + "a" * 64


def _node(name, *, port=None, address=None, image=None, services=()):
    return SimpleNamespace(
        name=name,
        container_name=f"aptl-{name}",
        published_ports=(
            (DeploymentPublishedPort(container_port=port, host_port=port),)
            if port is not None
            else ()
        ),
        static_address_assignments=(
            (("dmz-net", address),) if address is not None else ()
        ),
        image=image,
        services=services,
    )


def _realization():
    image = SimpleNamespace(image_ref="jasonish/suricata@" + _DIGEST)
    content = (
        SimpleNamespace(
            content=SimpleNamespace(
                content_name="suricata-config",
                artifact_id="techvault-suricata-config",
                artifact_digest="sha256:" + "d" * 64,
            )
        ),
        SimpleNamespace(
            content=SimpleNamespace(
                content_name="suricata-local-rules",
                artifact_id="techvault-suricata-local-rules",
                artifact_digest="sha256:" + "e" * 64,
            )
        ),
    )
    return SimpleNamespace(
        nodes=(
            _node("wazuh-manager", port=55000),
            _node("wazuh-indexer", port=9200),
            _node("suricata", image=image),
            _node("kali", address="172.20.1.30"),
            _node(
                "webapp",
                address="172.20.1.20",
                services=(DeploymentServicePort(name="http", port=8080),),
            ),
        ),
        placements=content,
        generated_artifacts=(),
    )


class _Backend:
    def __init__(self):
        self.probe_payload = ""
        self.exec_calls = []

    @staticmethod
    def container_inspect(_name):
        return {"Image": _DIGEST}

    @staticmethod
    def container_image_digest(_name):
        return _DIGEST

    def container_exec_with_input(self, name, cmd, payload, *, timeout):
        assert cmd
        if name == "aptl-suricata":
            rows = [
                "d" * 64 + "  /etc/suricata/suricata.yaml",
                "e" * 64 + "  /etc/suricata/rules/local.rules",
                *(f"sid={sid}" for sid in sorted(TECHVAULT_LOCAL_SIDS)),
            ]
            return subprocess.CompletedProcess(cmd, 0, "\n".join(rows) + "\n", "")
        self.probe_payload = payload
        assert "UNION" not in " ".join(cmd)
        assert cmd[-1] == "http://172.20.1.20:8080/login"
        assert "-f" not in cmd[1]
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def container_exec(self, name, cmd, *, timeout):
        self.exec_calls.append((name, cmd, timeout))
        event = (
            {
                "timestamp": _FINISH,
                "rule": {"id": "303020"},
                "data": {
                    "flow_id": "42.000000",
                    "src_ip": "172.20.1.30",
                    "dest_ip": "172.20.1.20",
                    "alert": {"signature_id": 1000010},
                },
            }
            if name == "aptl-wazuh-manager"
            else {
                "timestamp": _FINISH,
                "src_ip": "172.20.1.30",
                "dest_ip": "172.20.1.20",
                "flow_id": 42,
                "alert": {"signature_id": 1000010},
            }
        )
        return subprocess.CompletedProcess(cmd, 0, json.dumps(event) + "\n", "")


def _owner(tmp_path, backend=None, *, may_prepare=True):
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
    from aptl.core.retained_enrollment import scenario_enrollment_retainer

    times = iter((_TRIGGER, _FINISH, _TRIGGER))
    realization = _realization()
    return TechVaultNativeEvidenceOwner(
        operations=AdmittedRuntimeOperations(backend or _Backend(), realization.nodes),
        realization=realization,
        retain_enrollment_ids=scenario_enrollment_retainer(tmp_path, establish=True),
        may_prepare=may_prepare,
        dependencies=TechVaultNativeDependencies(
            now=lambda: next(times),
            sleep=lambda _seconds: None,
        ),
    )


def test_native_owner_wires_exactly_the_native_registrations(tmp_path):
    """Every source the native owner offers can actually produce its evidence.

    A source without the state it compares against would accept whatever it
    observed, so the MISP readiness source is offered only when the plan admits
    MISP. This realization does not, and its absence leaves the demand
    uncovered rather than covered by something that cannot decide it.
    """

    assert set(_owner(tmp_path).sources()) == {
        "aptl.collector.suricata-rule-readiness",
        "aptl.collector.suricata-wazuh-sqli",
        "aptl.collector.wazuh-agent-readiness",
    }


def test_the_misp_source_appears_once_the_plan_admits_a_state_to_compare(tmp_path):
    """And it carries the admitted values, not defaults of its own."""

    from aptl_techvault.evidence.techvault_misp_readiness import AdmittedMispState
    from aptl_techvault.evidence.techvault_native_readiness import (
        admitted_misp_state,
    )

    owner = _owner(tmp_path)
    admitted = AdmittedMispState(
        canonical_url="https://misp.techvault.local",
        database_identity="misp",
        database_role="misp",
        cache_persistence_policy="no",
        cache_eviction_policy="noeviction",
    )
    with mock.patch.object(
        techvault_native, "admitted_misp_state", return_value=admitted
    ):
        sources = owner.sources()

    assert "aptl.collector.misp-authenticated-api-readiness" in sources
    # The helper reads the admitted plan; it invents nothing when MISP is absent.
    assert admitted_misp_state(owner._realization) is None


def test_suricata_owner_joins_native_success_with_admitted_and_realized_identity(
    tmp_path,
):
    import json

    result = (
        _owner(tmp_path)
        .sources()["aptl.collector.suricata-rule-readiness"]
        .fetch(_START, _END)
    )
    text = b"".join(result.chunks).decode()
    payload = json.loads(text)

    assert result.status is CollectorStatus.OK
    assert payload["image_ref"].startswith("jasonish/suricata@sha256:")
    assert payload["content_identities"]["suricata-local-rules"].startswith(
        "techvault-suricata-local-rules@sha256:"
    )
    assert payload["local_rule_count"] == 16
    assert len(payload["local_sids"]) == 16
    assert "/etc/" not in text


def test_sqli_owner_keeps_probe_body_off_argv_and_requires_flow_join(tmp_path):
    backend = _Backend()
    result = (
        _owner(tmp_path, backend)
        .sources()["aptl.collector.suricata-wazuh-sqli"]
        .fetch(_START, _END)
    )

    assert result.status is CollectorStatus.OK
    assert "UNION" in backend.probe_payload
    assert '"flow_id":"42"' in b"".join(result.chunks).decode()
    assert result.observer_effect == "one fixed POST /login containing UNION SELECT"


def test_sqli_owner_reads_wazuh_half_from_declared_manager_log_not_indexer(tmp_path):
    backend = _Backend()

    result = (
        _owner(tmp_path, backend)
        .sources()["aptl.collector.suricata-wazuh-sqli"]
        .fetch(_START, _END)
    )

    assert result.status is CollectorStatus.OK
    manager_reads = [
        call for call in backend.exec_calls if call[0] == "aptl-wazuh-manager"
    ]
    assert manager_reads == [
        (
            "aptl-wazuh-manager",
            [
                "tail",
                "-c",
                str(techvault_native.MAX_SOURCE_BYTES),
                "/var/ossec/logs/alerts/alerts.json",
            ],
            30,
        )
    ]


def test_wazuh_manager_log_discloses_loss_when_correlated_record_is_absent(tmp_path):
    backend = _Backend()
    backend.container_exec = lambda name, cmd, *, timeout: subprocess.CompletedProcess(
        cmd,
        0,
        "{partial\n"
        if name == "aptl-wazuh-manager"
        else _Backend().container_exec(name, cmd, timeout=timeout).stdout,
        "",
    )

    result = (
        _owner(tmp_path, backend)
        .sources()["aptl.collector.suricata-wazuh-sqli"]
        .fetch(_START, _END)
    )

    assert result.status is CollectorStatus.MID_RUN_LOSS


def test_suricata_query_reads_recent_events_from_a_large_native_log(tmp_path):
    log = tmp_path / "eve.json"
    event = {
        "timestamp": _FINISH,
        "src_ip": "172.20.1.40",
        "dest_ip": "172.20.1.20",
        "flow_id": 42,
        "alert": {"signature_id": 1000010},
    }
    # Exercise the real tail command, including a cut through an older line.
    log.write_text(
        "x" * (techvault_native.MAX_SOURCE_BYTES + 100)
        + "\n"
        + json.dumps(event)
        + "\n"
    )
    backend = _Backend()
    backend.container_exec = lambda _name, argv, *, timeout: subprocess.run(
        [*argv[:-1], str(log)], capture_output=True, text=True, timeout=timeout
    )

    assert _owner(tmp_path, backend).query_suricata(_START, _END) == [event]


def test_measurement_owner_sends_no_sqli_probe_or_misp_write(tmp_path):
    backend = _Backend()
    owner = _owner(tmp_path, backend, may_prepare=False)

    result = owner.sources()["aptl.collector.suricata-wazuh-sqli"].fetch(_START, _END)

    assert result.status is CollectorStatus.SOURCE_UNAVAILABLE
    assert result.observer_effect is None
    assert backend.probe_payload == ""
    assert backend.exec_calls == []
    assert owner.misp_readiness_query(_START, _END) is None


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess(["curl"], 7, "", ""),
        subprocess.TimeoutExpired("curl", 30),
        OSError("transport-canary"),
    ],
)
def test_a_started_sqli_request_that_fails_is_unconfirmed_not_absent(
    tmp_path, outcome
):
    from aptl_techvault.evidence.techvault import SQLI_DELIVERY_UNCONFIRMED

    backend = _Backend()

    def execute(name, cmd, payload, *, timeout):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    backend.container_exec_with_input = execute

    assert _owner(tmp_path, backend).trigger_sqli() == SQLI_DELIVERY_UNCONFIRMED


def test_a_refused_sqli_request_never_started(tmp_path):
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations

    owner = _owner(tmp_path)
    # The realization no longer admits the Kali container: core refuses first.
    owner._operations = AdmittedRuntimeOperations(_Backend(), ())

    assert owner.trigger_sqli() is None


@pytest.mark.parametrize(
    ("extra", "address"),
    [
        ({}, "172.20.0.135"),
        ({"bad\nname": {"IPAddress": "10.0.0.2"}}, None),
    ],
)
def test_misp_address_needs_one_whole_admitted_attachment(extra, address):
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
    from aptl_techvault.evidence.techvault_native_readiness import (
        _owned_attachment_address,
    )

    networks = {"range": {"IPAddress": "172.20.0.135", "Aliases": ["misp"]}, **extra}
    backend = SimpleNamespace(
        container_inspect=lambda _name: {"NetworkSettings": {"Networks": networks}}
    )
    node = SimpleNamespace(name="misp", container_name="aptl-misp", aliases=())
    operations = AdmittedRuntimeOperations(backend, (node,))

    assert _owned_attachment_address(operations, node, "misp") == address


def test_owner_operations_refuse_a_container_the_realization_did_not_admit(tmp_path):
    owner = _owner(tmp_path)

    with pytest.raises(ValueError, match="^runtime-node-not-admitted$"):
        owner._operations.container_exec("aptl-outside", ["true"], timeout=30)
