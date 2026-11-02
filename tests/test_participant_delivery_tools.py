"""Real control-plane action admission during the incumbent delivery flow."""

from contextlib import nullcontext
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model

from aptl.backends._raes_participant_crossing import participant_runtime_options
from aptl.backends._raes_participant_execution import (
    _participant_control_identity,
    _control_intent_fields,
    _participant_crossing_evidence,
)
from aptl.backends._raes_participant_planning import build_participant_delivery_plan
from aptl.backends.participant_tools.delivery import (
    DeliveryToolSession,
    DeliveryActionAuthority,
)
from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.raes_participant_runtime import AptlParticipantRuntime
from aptl.backends.raes_planning_compat import AptlRuntimeManager
from aptl.core.agent_errors import AgentExecutionError
from aptl.workbench.profiles import profile_for
from tests.lilrae_concurrent_fixture import scenario
from tests.test_lilrae_participant_tools import result
from tests.test_raes_participant_delivery import _scenario_and_model


def delivery_runtime():
    authored, deliveries = _scenario_and_model()
    neutral = scenario()
    neutral.action_contracts["blue"] = neutral.action_contracts["red"].model_copy(
        deep=True
    )
    neutral.agents["blue"].actions = ["blue"]
    neutral.objectives["blue"].actions = ["blue"]
    red = neutral.behavior_specifications["duel"]
    blue = red.model_copy(deep=True)
    red.participant_refs = ["red"]
    red.participant_role_refs = ["red"]
    red.autonomous_execution.evaluation_authority.objective_refs = ["red"]
    blue.participant_refs = ["blue"]
    blue.participant_role_refs = ["blue"]
    blue.action_contract_refs = ["blue"]
    blue.autonomous_execution.action_order = ["blue"]
    blue.autonomous_execution.evaluation_authority.objective_refs = ["blue"]
    neutral.behavior_specifications["blue"] = blue
    compiled = compile_runtime_model(neutral)
    participants = {}
    for role in ("red", "blue"):
        original = compiled.participant_behaviors["participant.behavior." + role]
        participant = replace(
            original,
            address=f"participant.behavior.{role}-operator",
            authority_anchor_refs=("entities.study-control",),
            authority_anchor_addresses=("entity.study-control",),
            observation_boundary_addresses=(
                f"participant.observation-boundary.{role}-view",
            ),
        )
        participants[participant.address] = participant
        key = f"participant.behavior-specification.{role}-study"
        deliveries.behavior_specifications[key] = replace(
            deliveries.behavior_specifications[key],
            action_contract_addresses=participant.action_contract_addresses,
        )
    deliveries.participant_behaviors = participants
    plan = build_participant_delivery_plan(authored, deliveries)
    runtime = AptlParticipantRuntime(deployment_backend=Mock())
    target = replace(
        create_stub_target(),
        participant_runtime=runtime,
        manifest=replace(
            create_aptl_manifest(participant_inject_delivery=True),
            supported_contract_versions=create_aptl_manifest(
                participant_inject_delivery=True
            ).supported_contract_versions
            - {
                "backend-runtime-descendants-v1",
                "backend-materialization-attestation-v1",
            },
        ),
    )
    manager = AptlRuntimeManager(target, **participant_runtime_options(plan, target))
    return manager, runtime, target, plan


def session_for(manager, runtime, target, plan, role):
    turn = next(turn for turn in plan.turns if turn.profile.value == role)
    identity = _participant_control_identity(turn, target)
    episode = manager.initialize_participant_episode(
        turn.participant_address, identity=identity
    )
    assert manager.get_operation(episode.operation_id).state.value == "succeeded"
    from raes_runtime.participant_control_intents import (
        ParticipantProposalControlIntent,
    )

    proposal = ParticipantProposalControlIntent(
        declaration_ref=turn.proposal_transition_address,
        **_control_intent_fields(
            turn,
            run_id="fixture",
            suffix="proposal",
            expected_state_revision=turn.proposal_expected_state_revision,
        ),
        proposal_id=turn.proposal_id,
        proposal_revision=turn.proposal_revision,
        action_contract_ref=turn.inject_address,
        payload_ref=turn.source_item_ref,
    )
    receipt = manager.record_participant_control(
        turn.participant_address,
        proposal,
        identity=identity,
        crossing_evidence=_participant_crossing_evidence(turn),
    )
    assert manager.get_operation(receipt.operation_id).state.value == "succeeded"
    return DeliveryToolSession(
        control_plane=manager,
        runtime=runtime,
        behavior=plan.participant_behaviors[turn.participant_address],
        turn=turn,
        authority=DeliveryActionAuthority(
            identity, _participant_crossing_evidence(turn)
        ),
        tools={
            server.server_id: server.tool_names
            for server in profile_for(turn.profile).servers
        },
        timeout_seconds=5,
    )


def test_real_admission_retains_red_and_blue_tool_outcomes():
    manager, runtime, target, plan = delivery_runtime()
    for role in ("red", "blue"):
        session = session_for(manager, runtime, target, plan, role)
        server, tool = (
            ("aptl-red", "kali_run_command")
            if role == "red"
            else ("aptl-wazuh", "wazuh_query_alerts")
        )
        try:
            for index in range(3):
                call = session.begin(server, tool, {"command": "id"}, str(index))
                assert call.dispatched
                native_result = result() if index < 2 else result('{"success":false}')
                assert session.complete(call, native_result) == native_result
            history = manager.snapshot.participant_behavior_history[
                session.turn.participant_address
            ]
            assert len(history) == 9
            assert history[-1]["action_result"]["status"] == "failed"
            assert all(
                row["action_contract_address"]
                == session.behavior.action_contract_addresses[0]
                for row in history
            )
        finally:
            session.close()


def test_refusal_replay_and_unknown_never_authorize_another_effect():
    manager, runtime, target, plan = delivery_runtime()
    session = session_for(manager, runtime, target, plan, "red")
    try:
        with pytest.raises(AgentExecutionError):
            session.begin("aptl-wazuh", "wazuh_api_request", {}, "foreign")
        call = session.begin("aptl-red", "kali_run_command", {}, "one")
        with pytest.raises(AgentExecutionError):
            session.begin("aptl-red", "kali_run_command", {}, "parallel")
        session.complete(call, result())
        with pytest.raises(AgentExecutionError):
            session.begin("aptl-red", "kali_run_command", {"command": "changed"}, "one")
        uncertain = session.begin("aptl-red", "kali_run_command", {}, "two")
        session.unknown(uncertain)
        with pytest.raises(AgentExecutionError):
            session.begin("aptl-red", "kali_run_command", {}, "three")
        history = list(
            manager.snapshot.participant_behavior_history[
                session.turn.participant_address
            ]
        )
        assert len(history) == 6
        assert history[-1]["action_result"]["status"] == "unknown"
    finally:
        session.close()
    assert runtime.delivery_tools is None


def test_raes_crossing_refusal_is_observed_before_dispatch():
    manager, runtime, target, plan = delivery_runtime()
    session = session_for(manager, runtime, target, plan, "red")
    session.crossing_evidence = session.crossing_evidence.model_copy(
        update={"evidence_refs": ["unselected-evidence"]}
    )
    try:
        with pytest.raises(AgentExecutionError):
            session.begin("aptl-red", "kali_run_command", {}, "refused")
        assert not session._active.dispatched
        assert not manager.snapshot.participant_behavior_history.get(
            session.turn.participant_address
        )
    finally:
        session.close()


@pytest.mark.parametrize("uncertain", [False, True])
def test_delivery_turns_install_live_carriers_and_keep_one_episode(
    tmp_path, monkeypatch, uncertain
):
    import json
    import socket
    from aptl.backends.raes_participant_delivery import (
        ParticipantDeliveryExecutionContext,
        bind_participant_delivery_capture,
        execute_participant_delivery_plan,
    )
    from aptl.core.runstore import LocalRunStore
    from tests.test_raes_participant_delivery import (
        _binding,
        _Runner,
        _admitted_fixture_executable,
    )

    manager, runtime, target, plan = delivery_runtime()
    plan = bind_participant_delivery_capture(
        plan,
        SimpleNamespace(
            runtime_bindings=lambda: tuple(
                _binding(role, phase)
                for role in ("red", "blue")
                for phase in ("start", "stop")
            ),
        ),
    )
    project = tmp_path / "project"
    project.mkdir()
    (project / ".mcp.json").write_text('{"mcpServers": {}}')
    manager.advance_time = lambda *args, **kwargs: SimpleNamespace(
        success=True, snapshot=manager.snapshot
    )
    credentials = []

    def render(**kwargs):
        profile = kwargs["profile"]
        server = "aptl-red" if profile.value == "red" else "aptl-wazuh"
        tool = "kali_run_command" if profile.value == "red" else "wazuh_query_alerts"
        path = kwargs["output_dir"] / f"{profile.value}.json"
        path.write_text(
            json.dumps(
                {"mcpServers": {server: {"command": "node", "args": [], "env": {}}}}
            )
        )
        path.chmod(0o600)
        return path, (f"mcp__{server}__{tool}",)

    class ToolRunner(_Runner):
        def run(self, argv, **kwargs):
            config = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
            server, selected = next(iter(config["mcpServers"].items()))
            env = selected["env"]
            credentials.append(env["LILRAE_TOOL_TOKEN"])
            tool = "kali_run_command" if server == "aptl-red" else "wazuh_query_alerts"
            for index in range(2):
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.settimeout(10)
                    connection.connect(env["LILRAE_TOOL_SOCKET"])
                    stream = connection.makefile("rwb")
                    proposal = {
                        "version": 1,
                        "token": env["LILRAE_TOOL_TOKEN"],
                        "call_id": str(index),
                        "tool": tool,
                        "arguments": {},
                        "configuration": {},
                    }
                    stream.write(json.dumps(proposal).encode() + b"\n")
                    stream.flush()
                    assert json.loads(stream.readline())["accepted"]
                    stream.write(
                        json.dumps(
                            {"result": result(), "uncertain": uncertain}
                        ).encode()
                        + b"\n"
                    )
                    stream.flush()
                    assert json.loads(stream.readline())["accepted"] is not uncertain
                    if uncertain:
                        return super().run(argv, **kwargs)
            return super().run(argv, **kwargs)

    monkeypatch.setattr(
        "aptl.backends._raes_participant_execution._render_runtime_profile_config",
        render,
    )
    monkeypatch.setattr(
        "aptl.backends._raes_participant_execution._which_executable",
        lambda name: _admitted_fixture_executable(tmp_path),
    )
    runner = ToolRunner()
    expectation = (
        pytest.raises(AgentExecutionError, match="outcome is unknown")
        if uncertain
        else nullcontext()
    )
    with expectation:
        final = execute_participant_delivery_plan(
            plan,
            context=ParticipantDeliveryExecutionContext(
                project_dir=project,
                model="fixture",
                run_store=LocalRunStore(tmp_path / "runs"),
                run_id="fixture",
                target=target,
                runtime_manager=manager,
                initial_snapshot=manager.snapshot,
                runner=runner,
            ),
        )
    if uncertain:
        assert len(credentials) == 1
        assert runtime.delivery_tools is None
        history = list(
            manager.snapshot.participant_behavior_history[
                plan.turns[0].participant_address
            ]
        )
        assert len(history) == 3
        assert history[-1]["action_result"]["status"] == "unknown"
        return
    assert len(set(credentials)) == 4
    assert runtime.delivery_tools is None
    for role in ("red", "blue"):
        participant = f"participant.behavior.{role}-operator"
        history = list(final.participant_behavior_history[participant])
        assert len(history) == 12
        assert len({row["episode_id"] for row in history}) == 1
        assert len(final.participant_control_history[participant]) == 4
