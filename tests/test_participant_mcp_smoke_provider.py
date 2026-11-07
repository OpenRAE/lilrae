"""Admitted-input participant MCP smoke providers (issue #1707)."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from aptl.core.mcp_policy import McpRunAdmission
from aptl.core.scenario_bundle import PackIdentity
from aptl.validation import participant_mcp_smoke as smoke
from aptl.validation.participant_mcp_smoke import (
    AdmittedAddress,
    AdmittedNode,
    AdmittedServicePort,
    McpRegistration,
    McpSmokeCheck,
    McpSmokeContext,
    McpSmokeOperation,
    ParticipantMcpSmokeError,
    admitted_mcp_server_ids,
    discover_participant_mcp_smoke_checks,
    resolve_participant_mcp_smoke_operations,
    resolve_participant_mcp_smoke_plan,
    run_participant_mcp_smoke,
)
from aptl.validation.participant_profile import load_participant_profile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = PROJECT_ROOT / "participant-profiles/guided-purple-v1/profile.json"
SELECTOR = "guided-purple.techvault-attacker-target"
PACK = PackIdentity("techvault", "1.0.0", "sha256:" + "a" * 64)
RUN_ID = "a" * 32
ALL_SERVERS = ("aptl-red", "aptl-indexer", "aptl-wazuh")

_SERVER = r"""
import json
import pathlib
import sys

pathlib.Path(sys.argv[1]).touch()
TOOLS = json.loads(sys.argv[2])
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    if message["method"] == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}}
    elif message["method"] == "tools/list":
        result = {"tools": [{"name": name} for name in TOOLS]}
    else:
        text = json.dumps({"ok": True})
        result = {"content": [{"type": "text", "text": text}]}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""

_PROFILE = None


def _profile():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = load_participant_profile(PROJECT_ROOT, PROFILE_PATH)
    return _PROFILE


def _optional(profile, *capabilities: str):
    """Return the profile with the named narrative capabilities optional."""

    operations = tuple(
        operation.model_copy(update={"classification": "optional"})
        if operation.capability_id in capabilities
        else operation
        for operation in profile.narrative.operations
    )
    return replace(
        profile,
        narrative=profile.narrative.model_copy(update={"operations": operations}),
    )


def _node(name: str, network: str, address: str) -> AdmittedNode:
    return AdmittedNode(
        name=name,
        services=(AdmittedServicePort(name="ssh", port=22, protocol="tcp"),),
        addresses=(AdmittedAddress(network=network, address=address),),
    )


def _admission(
    servers=ALL_SERVERS, nodes=None, run_id: str = RUN_ID
) -> McpRunAdmission:
    return McpRunAdmission(
        run_id=run_id,
        pack=PACK,
        server_ids=tuple(servers),
        container_aliases=(),
        nodes=(
            (_node("victim", "range", "10.9.0.20"),) if nodes is None else tuple(nodes)
        ),
    )


def _accept(_result) -> bool:
    return True


class _Provider:
    """A provider outside the TechVault package."""

    extension_api_version = "1"
    checks = (
        McpSmokeCheck("mcp.red.kali-command", "aptl-red", "kali_run_command"),
        McpSmokeCheck(
            "mcp.red.ssh-authentication-attack", "aptl-red", "kali_run_command"
        ),
        McpSmokeCheck(
            "mcp.blue.indexer-investigation", "aptl-indexer", "indexer_query"
        ),
        McpSmokeCheck(
            "mcp.blue.wazuh-investigation", "aptl-wazuh", "wazuh_query_alerts"
        ),
    )

    def __init__(self, extra=(), override=None):
        self.extra = tuple(extra)
        self.override = override
        self.contexts: list[McpSmokeContext] = []
        self.arguments: list[dict] = []

    def resolve(self, context: McpSmokeContext):
        self.contexts.append(context)
        if self.override is not None:
            return self.override(context)
        granted = {grant.server_id for grant in context.grants}
        wanted = {check.check_id for check in context.checks}
        operations = []
        for check in self.checks:
            if check.server_id not in granted or check.check_id not in wanted:
                continue
            arguments: dict = {"command": "id"}
            if check.check_id == "mcp.red.ssh-authentication-attack":
                target = context.address("victim", "range")
                arguments = {"command": f"ssh probe@{target} true; echo done"}
            self.arguments.append(arguments)
            operations.append(
                McpSmokeOperation(
                    check.check_id,
                    check.server_id,
                    check.tool_name,
                    arguments,
                    _accept,
                )
            )
        return (*operations, *self.extra)


class _EntryPoint:
    name = SELECTOR

    def __init__(self, loaded):
        self.loaded = loaded

    def load(self):
        return self.loaded


def _install(monkeypatch, loaded) -> None:
    monkeypatch.setattr(
        smoke, "_installed_plan_entry_points", lambda: [_EntryPoint(loaded)]
    )


def _registrations(tmp_path: Path, servers) -> dict[str, McpRegistration]:
    profile = _profile()
    tools = {
        server.server_id: server.tool_names
        for workbench in profile.workbench_profiles
        for server in workbench.servers
    }
    return {
        server_id: McpRegistration(
            argv=(
                sys.executable,
                "-c",
                _SERVER,
                str(tmp_path / f"started-{server_id}"),
                json.dumps(list(tools[server_id])),
            ),
            cwd=tmp_path,
            env={},
        )
        for server_id in servers
    }


def _started(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob("started-*"))


def test_provider_selects_operations_from_the_admitted_inventory(
    monkeypatch, tmp_path: Path
) -> None:
    provider = _Provider()
    _install(monkeypatch, provider)

    evidence = run_participant_mcp_smoke(
        _profile(),
        _registrations(tmp_path, ALL_SERVERS),
        admission=_admission(),
    )

    assert [item.check_id for item in evidence] == [
        check.check_id for check in _Provider.checks
    ]
    assert {item.status for item in evidence} == {"passed"}
    context = provider.contexts[0]
    assert context.extension_api_version == "1"
    assert context.profile_id == "guided-purple"
    assert context.scenario_id == "techvault-attacker-target"
    assert context.pack == PACK
    assert {grant.server_id for grant in context.grants} == set(ALL_SERVERS)
    assert context.node("victim") is not None
    assert context.node("misp") is None


def test_changed_admitted_address_reaches_the_operation(monkeypatch) -> None:
    _install(monkeypatch, _Provider())

    first = resolve_participant_mcp_smoke_operations(_profile(), _admission())
    moved = resolve_participant_mcp_smoke_operations(
        _profile(), _admission(nodes=(_node("victim", "range", "10.9.0.77"),))
    )

    attack = "mcp.red.ssh-authentication-attack"
    assert "10.9.0.20" in next(o for o in first if o.check_id == attack).arguments[
        "command"
    ]
    assert "10.9.0.77" in next(o for o in moved if o.check_id == attack).arguments[
        "command"
    ]


def test_selected_out_optional_service_has_no_operation_or_connection(
    monkeypatch, tmp_path: Path
) -> None:
    _install(monkeypatch, _Provider())
    profile = _optional(_profile(), "blue.wazuh-investigation")
    admission = _admission(servers=("aptl-red", "aptl-indexer"))

    servers = admitted_mcp_server_ids(profile, admission)
    evidence = run_participant_mcp_smoke(
        profile, _registrations(tmp_path, servers), admission=admission
    )

    assert servers == ("aptl-red", "aptl-indexer")
    assert "mcp.blue.wazuh-investigation" not in {item.check_id for item in evidence}
    assert not (tmp_path / "started-aptl-wazuh").exists()
    with pytest.raises(ParticipantMcpSmokeError, match="registration surface"):
        run_participant_mcp_smoke(
            profile, _registrations(tmp_path, ALL_SERVERS), admission=admission
        )


def test_present_optional_service_keeps_its_operation(monkeypatch) -> None:
    _install(monkeypatch, _Provider())
    profile = _optional(_profile(), "blue.wazuh-investigation")

    operations = resolve_participant_mcp_smoke_operations(profile, _admission())

    assert "mcp.blue.wazuh-investigation" in {o.check_id for o in operations}


def test_missing_required_service_stops_before_resolution(monkeypatch) -> None:
    provider = _Provider()
    _install(monkeypatch, provider)

    with pytest.raises(ParticipantMcpSmokeError, match="required MCP server"):
        resolve_participant_mcp_smoke_operations(
            _profile(), _admission(servers=("aptl-red", "aptl-indexer"))
        )
    assert provider.contexts == []


def test_empty_admitted_selection_never_qualifies(monkeypatch) -> None:
    _install(monkeypatch, _Provider())
    profile = _optional(
        _profile(),
        "red.kali-command",
        "red.ssh-authentication-attack",
        "blue.indexer-investigation",
        "blue.wazuh-investigation",
    )

    with pytest.raises(ParticipantMcpSmokeError, match="no admitted"):
        resolve_participant_mcp_smoke_operations(profile, _admission(servers=()))


def test_missing_target_stops_before_any_mcp_process(
    monkeypatch, tmp_path: Path
) -> None:
    _install(monkeypatch, _Provider())

    with pytest.raises(ParticipantMcpSmokeError, match="target is not admitted"):
        run_participant_mcp_smoke(
            _profile(),
            _registrations(tmp_path, ALL_SERVERS),
            admission=_admission(nodes=(_node("victim", "other", "10.9.1.20"),)),
        )
    assert _started(tmp_path) == []


def test_late_denied_tool_stops_before_any_mcp_process(
    monkeypatch, tmp_path: Path
) -> None:
    class Denied(_Provider):
        checks = (
            *_Provider.checks[:-1],
            replace(_Provider.checks[-1], tool_name="wazuh_delete_agent"),
        )

        def resolve(self, context):
            operations = _Provider().resolve(context)
            last = operations[-1]
            return (*operations[:-1], replace(last, tool_name="wazuh_delete_agent"))

    _install(monkeypatch, Denied())

    with pytest.raises(ParticipantMcpSmokeError, match="not granted"):
        run_participant_mcp_smoke(
            _profile(),
            _registrations(tmp_path, ALL_SERVERS),
            admission=_admission(),
        )
    assert _started(tmp_path) == []


def test_duplicate_check_cannot_hide_behind_set_comparison(monkeypatch) -> None:
    def duplicated(context):
        operations = _Provider().resolve(context)
        return (*operations, operations[0])

    _install(monkeypatch, _Provider(override=duplicated))

    with pytest.raises(ParticipantMcpSmokeError, match="malformed"):
        resolve_participant_mcp_smoke_operations(_profile(), _admission())


def test_provider_cannot_emit_an_undeclared_check(monkeypatch) -> None:
    class Narrow(_Provider):
        checks = _Provider.checks[:-1]

        def resolve(self, context):
            return _Provider().resolve(context)

    _install(monkeypatch, Narrow())

    with pytest.raises(ParticipantMcpSmokeError, match="undeclared"):
        resolve_participant_mcp_smoke_operations(_profile(), _admission())


@pytest.mark.parametrize(
    "arguments",
    [{"value": object()}, {"value": float("nan")}, {"value": "x" * 70_000}],
)
def test_non_json_or_oversized_arguments_are_refused(monkeypatch, arguments) -> None:
    def bad(context):
        operations = _Provider().resolve(context)
        return (replace(operations[0], arguments=arguments), *operations[1:])

    _install(monkeypatch, _Provider(override=bad))

    with pytest.raises(ParticipantMcpSmokeError, match="malformed"):
        resolve_participant_mcp_smoke_operations(_profile(), _admission())


def test_provider_mutation_after_return_does_not_change_the_plan(
    monkeypatch,
) -> None:
    provider = _Provider()
    _install(monkeypatch, provider)

    operations = resolve_participant_mcp_smoke_operations(_profile(), _admission())
    provider.arguments[0]["command"] = "rm -rf /"

    assert operations[0].arguments["command"] == "id"


def test_provider_failure_is_normalized_without_its_message(monkeypatch) -> None:
    def fail(_context):
        raise RuntimeError("secret detail")

    _install(monkeypatch, _Provider(override=fail))

    with pytest.raises(ParticipantMcpSmokeError) as raised:
        resolve_participant_mcp_smoke_operations(_profile(), _admission())
    assert "secret detail" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_provider_requires_a_run_admission(monkeypatch) -> None:
    provider = _Provider()
    _install(monkeypatch, provider)

    with pytest.raises(ParticipantMcpSmokeError, match="admitted inputs"):
        resolve_participant_mcp_smoke_operations(_profile())
    with pytest.raises(ParticipantMcpSmokeError, match="admitted inputs"):
        resolve_participant_mcp_smoke_plan(SELECTOR)
    assert provider.contexts == []


@pytest.mark.parametrize(
    "change",
    [
        {"extension_api_version": "2"},
        {"checks": []},
        {"checks": (McpSmokeCheck("bad id", "aptl-red", "kali_run_command"),)},
        {"checks": (_Provider.checks[0], _Provider.checks[0])},
        {"resolve": None},
    ],
)
def test_malformed_provider_declarations_are_refused(monkeypatch, change) -> None:
    provider = _Provider()
    for name, value in change.items():
        setattr(provider, name, value)
    _install(monkeypatch, provider)

    with pytest.raises(ParticipantMcpSmokeError, match="malformed"):
        discover_participant_mcp_smoke_checks(SELECTOR)


def test_conflicting_grants_for_one_server_are_refused(monkeypatch) -> None:
    _install(monkeypatch, _Provider())
    profile = _profile()
    workbench = profile.workbench_profiles[0]
    narrowed = replace(
        workbench,
        servers=tuple(
            replace(server, tool_names=server.tool_names[:1])
            for server in workbench.servers
        ),
    )
    conflicted = replace(
        profile, workbench_profiles=(*profile.workbench_profiles, narrowed)
    )

    with pytest.raises(ParticipantMcpSmokeError, match="conflicting"):
        resolve_participant_mcp_smoke_operations(conflicted, _admission())


def test_validator_exception_records_a_failed_check(tmp_path: Path) -> None:
    def crash(_result):
        raise KeyError("raw backend output")

    operations = tuple(
        McpSmokeOperation(
            check.check_id,
            check.server_id,
            check.tool_name,
            {"command": "id"},
            crash if index == 0 else _accept,
        )
        for index, check in enumerate(_Provider.checks)
    )

    evidence = run_participant_mcp_smoke(
        _profile(), _registrations(tmp_path, ALL_SERVERS), operations
    )

    assert evidence[0].status == "failed"
    assert "raw backend output" not in evidence[0].summary
    assert {item.status for item in evidence[1:]} == {"passed"}


def test_caller_supplied_operations_get_the_same_validation(tmp_path: Path) -> None:
    operations = tuple(
        McpSmokeOperation(c.check_id, c.server_id, c.tool_name, {}, _accept)
        for c in _Provider.checks
    )
    duplicated = (*operations, operations[0])

    with pytest.raises(ParticipantMcpSmokeError, match="malformed"):
        run_participant_mcp_smoke(
            _profile(), _registrations(tmp_path, ALL_SERVERS), duplicated
        )
    assert _started(tmp_path) == []


def test_installed_provider_is_discovered_from_package_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    package = tmp_path / "site"
    package.mkdir()
    (package / "fixture_smoke_adapter.py").write_text(
        "from aptl.validation.participant_mcp_smoke import McpSmokeCheck\n"
        "class Provider:\n"
        "    extension_api_version = '1'\n"
        "    checks = (McpSmokeCheck('fixture.check', 'aptl-red', 'kali_run_command'),)\n"
        "    def resolve(self, context):\n"
        "        raise AssertionError('discovery must not resolve')\n"
        "PROVIDER = Provider()\n"
    )
    dist = package / "fixture_smoke_adapter-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fixture-smoke-adapter\nVersion: 1.0\n"
    )
    (dist / "entry_points.txt").write_text(
        "[aptl.participant_mcp_smoke_plans]\n"
        "fixture-profile.fixture-scenario = fixture_smoke_adapter:PROVIDER\n"
    )
    monkeypatch.syspath_prepend(str(package))

    checks = discover_participant_mcp_smoke_checks("fixture-profile.fixture-scenario")

    assert checks == (
        McpSmokeCheck("fixture.check", "aptl-red", "kali_run_command"),
    )


def test_static_plan_discovery_keeps_its_declared_checks() -> None:
    checks = discover_participant_mcp_smoke_checks("techvault-full.techvault")
    static = resolve_participant_mcp_smoke_plan("techvault-full.techvault")

    assert checks == tuple(
        McpSmokeCheck(o.check_id, o.server_id, o.tool_name) for o in static
    )


def test_context_address_refuses_missing_and_ambiguous_assignments() -> None:
    context = McpSmokeContext(
        extension_api_version="1",
        profile_id="p",
        scenario_id="s",
        pack=None,
        nodes=(
            AdmittedNode(
                name="victim",
                services=(),
                addresses=(
                    AdmittedAddress("range", "10.0.0.1"),
                    AdmittedAddress("range", "10.0.0.2"),
                ),
            ),
        ),
        grants=(),
        checks=(),
    )

    with pytest.raises(ParticipantMcpSmokeError, match="target is not admitted"):
        context.address("victim", "range")
    with pytest.raises(ParticipantMcpSmokeError, match="target is not admitted"):
        context.address("absent", "range")
