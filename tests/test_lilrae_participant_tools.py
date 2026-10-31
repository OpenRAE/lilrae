"""Behavioral enforcement at the installed tool boundary."""

from dataclasses import replace
from threading import Event
from unittest.mock import Mock

import pytest
from raes_backend_protocols.capabilities import ParticipantExecutionBinding
from raes_contracts.participant_tool_actions import (
    ParticipantToolActionDecision,
    ParticipantToolActionReceipt,
)
from raes_contracts.canonical import canonical_json_digest

from aptl.backends.participant_tools.session import LilraeToolBinding, LilraeToolSession
from aptl.core.participant_tools.model import Phase
from aptl.workbench.process import AgentExecutionError


def binding(*, server="aptl-red", tool="kali_run_command", matcher=None):
    return LilraeToolBinding(
        server_id=server,
        tool_name=tool,
        tool_affordance_address="participant.behavior-specification.duel.tool-affordance.native",
        observation_boundary_address="participant.observation-boundary.red",
        action_contract_digest="sha256:" + "a" * 64,
        configuration_digest=canonical_json_digest({}),
        execution_binding=ParticipantExecutionBinding(
            binding_id="tool-native",
            action_contract_address="participant.action-contract.native",
            target_addresses=("provision.node.target.service.http",),
            participant_implementation_ref="participant-implementation-manifests.fixture.v1",
            constraint_refs=("constraint:native",),
            evidence_refs=("evidence:native",),
            max_action_attempts=16,
            max_in_flight=4,
            timeout_seconds=30,
            max_retries=0,
        ),
        accepts_arguments=matcher or (lambda args: args == {"command": "id"}),
    )


def port():
    value = Mock()
    value.closed = False
    value.invocation_action_instance_id = "outer-red"
    value.participant_address = "participant.behavior.red"
    value.episode_id = "episode-red"
    value.participant_implementation_ref = (
        "participant-implementation-manifests.fixture.v1"
    )
    value.execution_scope_ref = "scope:trial"
    value.execution_generation = 1
    value.observation_point = "point:tool"
    value.admit.side_effect = lambda request: ParticipantToolActionDecision(
        tool_call_id=request.tool_call_id,
        admitted=True,
        action_instance_id="action-" + request.tool_call_id,
    )
    value.dispatch.side_effect = lambda action: ParticipantToolActionReceipt(
        action, True
    )
    value.complete.side_effect = lambda action, outcome: ParticipantToolActionReceipt(
        action, True
    )
    value.cancel.side_effect = lambda action: ParticipantToolActionReceipt(action, True)
    value.report_unknown.side_effect = lambda action, reason: (
        ParticipantToolActionReceipt(action, True)
    )
    return value


def result(text='{"success":true}'):
    return {"content": [{"type": "text", "text": text}]}


def test_effect_requires_admission_and_single_dispatch_and_accepted_outcome():
    authority = port()
    effects = []
    session = LilraeToolSession(authority, (binding(),), Event())

    def native(args):
        assert authority.admit.call_count == authority.dispatch.call_count == 1
        effects.append(args)
        return result()

    assert (
        session.invoke(
            "aptl-red", "kali_run_command", {"command": "id"}, "first", native
        )
        == result()
    )
    assert effects == [{"command": "id"}]
    assert authority.complete.call_args.args[1].status == "succeeded"
    for args in ({"command": "id"}, {"command": "changed"}):
        with pytest.raises(AgentExecutionError):
            session.invoke("aptl-red", "kali_run_command", args, "first", native)
    assert len(effects) == 1


@pytest.mark.parametrize(
    "failure", ["admission", "dispatch", "mapping", "ambiguous", "cancelled", "closed"]
)
def test_refusal_never_calls_native_handler(failure):
    authority, cancellation = port(), Event()
    bindings = (binding(),)
    if failure == "admission":
        authority.admit.side_effect = None
        authority.admit.return_value = ParticipantToolActionDecision("call", False)
    if failure == "dispatch":
        authority.dispatch.side_effect = None
        authority.dispatch.return_value = ParticipantToolActionReceipt(
            "action-call", False
        )
    if failure == "mapping":
        bindings = (replace(binding(), accepts_arguments=lambda args: False),)
    if failure == "ambiguous":
        bindings = (binding(), binding())
    if failure == "cancelled":
        cancellation.set()
    if failure == "closed":
        authority.closed = True
    native = Mock(return_value=result())
    session = LilraeToolSession(authority, bindings, cancellation)
    with pytest.raises(AgentExecutionError):
        session.invoke(
            "aptl-red", "kali_run_command", {"command": "id"}, "call", native
        )
    native.assert_not_called()


def test_uncertain_effects_and_failed_completion_cannot_deliver_success():
    for fail_completion in (False, True):
        authority, native = port(), Mock(return_value=result())
        if fail_completion:
            authority.complete.side_effect = None
            authority.complete.return_value = ParticipantToolActionReceipt(
                "action-call", False
            )
        else:
            native.side_effect = TimeoutError("private output")
        session = LilraeToolSession(authority, (binding(),), Event())
        with pytest.raises(AgentExecutionError, match="Participant tool") as error:
            session.invoke(
                "aptl-red", "kali_run_command", {"command": "id"}, "call", native
            )
        assert "private output" not in str(error.value)
        assert authority.report_unknown.call_count == 1
        assert session.states()[0].phase == Phase.INDETERMINATE
        assert native.call_count == 1


def test_error_payload_is_failed_and_secret_output_is_redacted(monkeypatch):
    monkeypatch.setenv("APTL_EXPERIMENT_NO_REDACT", "1")
    authority = port()
    session = LilraeToolSession(authority, (binding(),), Event())
    safe = session.invoke(
        "aptl-red",
        "kali_run_command",
        {"command": "id"},
        "call",
        lambda args: result('{"success":false,"password":"canary-1418"}'),
    )
    assert "canary-1418" not in str(safe)
    outcome = authority.complete.call_args.args[1]
    assert outcome.status == "failed"
    assert "canary-1418" not in str(outcome)


def test_argument_matcher_cannot_mutate_the_dispatched_call():
    def mutating(args):
        args["command"] = "changed"
        return True

    session = LilraeToolSession(port(), (binding(matcher=mutating),), Event())
    native = Mock(return_value=result())
    session.invoke("aptl-red", "kali_run_command", {"command": "id"}, "call", native)
    assert native.call_args.args[0] == {"command": "id"}


def test_ledger_failure_during_unknown_does_not_leak_or_skip_peer_cleanup():
    authority = port()
    authority.report_unknown.side_effect = RuntimeError("private-ledger-canary")
    session = LilraeToolSession(authority, (binding(),), Event())
    session.begin("aptl-red", "kali_run_command", {"command": "id"}, "one")
    session.begin("aptl-red", "kali_run_command", {"command": "id"}, "two")
    session.close()
    assert authority.report_unknown.call_count == 2
    assert all(state.phase == Phase.INDETERMINATE for state in session.states())


def test_effective_server_configuration_is_part_of_the_installed_authority():
    authority = port()
    native = Mock(return_value=result())
    session = LilraeToolSession(authority, (binding(),), Event())
    with pytest.raises(AgentExecutionError):
        session.invoke(
            "aptl-red",
            "kali_run_command",
            {"command": "id"},
            "changed-target",
            native,
            configuration={"target": "different-container"},
        )
    native.assert_not_called()
    authority.admit.assert_not_called()


def test_metadata_observation_does_not_need_a_fabricated_success_field():
    authority = port()
    metadata = result('{"target_name":"Declared target"}')
    session = LilraeToolSession(authority, (binding(),), Event())
    assert (
        session.invoke(
            "aptl-red",
            "kali_run_command",
            {"command": "id"},
            "info",
            lambda _: metadata,
        )
        == metadata
    )
    assert authority.complete.call_args.args[1].status == "succeeded"


def test_polymorphic_tool_selects_the_declared_action_for_its_complete_arguments():
    authority, effects = port(), []
    read = binding(matcher=lambda args: args == {"method": "GET", "endpoint": "/rules"})
    write = replace(
        read,
        accepts_arguments=lambda args: (
            args == {"method": "PUT", "endpoint": "/rules", "body": "rule"}
        ),
        execution_binding=replace(
            read.execution_binding,
            binding_id="write",
            action_contract_address="participant.action-contract.write",
        ),
    )
    session = LilraeToolSession(authority, (read, write), Event())
    for index, args in enumerate(
        (
            {"method": "GET", "endpoint": "/rules"},
            {"method": "PUT", "endpoint": "/rules", "body": "rule"},
        )
    ):
        session.invoke(
            "aptl-red",
            "kali_run_command",
            args,
            str(index),
            lambda call: effects.append(call) or result(),
        )
    assert [
        call.args[0].action_contract_address for call in authority.admit.call_args_list
    ] == [
        "participant.action-contract.native",
        "participant.action-contract.write",
    ]
    with pytest.raises(AgentExecutionError):
        session.invoke(
            "aptl-red",
            "kali_run_command",
            {"method": "PUT", "endpoint": "/different", "body": "rule"},
            "other",
            lambda call: effects.append(call) or result(),
        )
    assert len(effects) == 2
