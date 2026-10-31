"""Real local socket protocol, including lost responses and foreign authority."""

import json
import socket
from threading import Event
from unittest.mock import Mock

import pytest

from aptl.backends.participant_tools.session import LilraeToolSession
from aptl.backends.participant_tools.transport import LilraeToolTransport
from tests.test_lilrae_participant_tools import binding, port, result


def connect(environment):
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(5)
    client.connect(environment["LILRAE_TOOL_SOCKET"])
    return client, client.makefile("rwb")


def send(stream, value):
    stream.write(json.dumps(value).encode() + b"\n")
    stream.flush()


def proposal(environment, **changes):
    return {
        "version": 1,
        "token": environment["LILRAE_TOOL_TOKEN"],
        "call_id": "call",
        "tool": "kali_run_command",
        "arguments": {"command": "id"},
        "configuration": {},
    } | changes


def test_worker_start_failure_closes_socket_without_waiting_for_a_worker(monkeypatch):
    from aptl.backends.participant_tools import transport as module

    session = LilraeToolSession(port(), (binding(),), Event())
    transport = LilraeToolTransport(session)
    monkeypatch.setattr(
        module.Thread,
        "start",
        lambda self: (_ for _ in ()).throw(RuntimeError("start failed")),
    )
    # A shutdown request to a server that never ran blocks indefinitely.
    shutdown = Mock(
        side_effect=AssertionError("unstarted worker cannot acknowledge shutdown")
    )
    monkeypatch.setattr(module._Server, "shutdown", shutdown)
    with pytest.raises(RuntimeError, match="start failed"):
        with transport:
            pytest.fail("failed worker must not expose an active carrier")
    shutdown.assert_not_called()
    assert transport.tokens == {}


def test_socket_preserves_authority_and_redacts_completion(tmp_path):
    authority = port()
    session = LilraeToolSession(authority, (binding(),), Event())
    with LilraeToolTransport(session) as transport:
        env = transport.environment("aptl-red")
        client, stream = connect(env)
        with client, stream:
            send(stream, proposal(env))
            assert json.loads(stream.readline()) == {"accepted": True}
            send(
                stream,
                {
                    "result": result('{"success":true,"password":"canary-1418"}'),
                    "uncertain": False,
                },
            )
            response = json.loads(stream.readline())
            assert response["accepted"] is True
            assert "canary-1418" not in repr(response)
    assert authority.dispatch.call_count == authority.complete.call_count == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"token": "foreign"},
        {"participant_address": "peer"},
        {"tool": "unknown"},
        {"version": True},
        {"arguments": []},
        {"configuration": []},
    ],
)
def test_foreign_or_extended_proposal_has_no_dispatch(extra):
    authority = port()
    with LilraeToolTransport(
        LilraeToolSession(authority, (binding(),), Event())
    ) as transport:
        env = transport.environment("aptl-red")
        client, stream = connect(env)
        with client, stream:
            send(stream, proposal(env, **extra))
            assert json.loads(stream.readline()) == {"accepted": False}
    authority.dispatch.assert_not_called()


def test_disconnect_after_permission_reports_unknown_and_never_replays():
    authority = port()
    notified = Event()
    original = authority.report_unknown.side_effect

    def report(action, failure):
        notified.set()
        return original(action, failure)

    authority.report_unknown.side_effect = report
    session = LilraeToolSession(authority, (binding(),), Event())
    with LilraeToolTransport(session) as transport:
        env = transport.environment("aptl-red")
        client, stream = connect(env)
        send(stream, proposal(env))
        assert json.loads(stream.readline())["accepted"]
        stream.close()
        client.close()
        assert notified.wait(5)
        client, stream = connect(env)
        with client, stream:
            send(stream, proposal(env))
            assert not json.loads(stream.readline())["accepted"]
    assert authority.dispatch.call_count == 1


def test_caught_handler_uncertainty_cannot_be_reported_as_terminal_failure():
    authority = port()
    with LilraeToolTransport(
        LilraeToolSession(authority, (binding(),), Event())
    ) as transport:
        env = transport.environment("aptl-red")
        client, stream = connect(env)
        with client, stream:
            send(stream, proposal(env))
            assert json.loads(stream.readline())["accepted"]
            send(stream, {"result": result('{"success":false}'), "uncertain": True})
            assert not json.loads(stream.readline())["accepted"]
    authority.complete.assert_not_called()
    assert authority.report_unknown.call_count == 1
