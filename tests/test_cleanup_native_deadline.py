"""Direct recorder/native calls share the remaining authored cleanup budget."""

import pytest

from aptl.core.deployment._cleanup_budget import cleanup_budget
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.deployment import lilrae_docker_http as docker_http
from aptl.core.deployment.lilrae_docker_recorder import RecordingSession


def test_direct_native_reads_consume_one_shared_deadline(monkeypatch):
    elapsed = [0.0]
    timeouts = []

    class Connection:
        def __init__(self, path, timeout):
            timeouts.append(timeout)

        def request(self, method, path):
            pass

        def getresponse(self):
            return self

        status = 200

        def read(self, limit):
            elapsed[0] += 0.6
            return b"{}"

        def close(self):
            pass

    monkeypatch.setattr(docker_http, "_UnixConnection", Connection)
    monkeypatch.setattr(
        docker_http, "_local_docker_socket_identity", lambda path: (1, 2)
    )
    native = docker_http.NativeDocker("/test.sock", "daemon", identity=(1, 2))
    with cleanup_budget(1, clock=lambda: elapsed[0]):
        native.request("GET", "/info")
        with pytest.raises(BackendTimeoutError):
            native.request("GET", "/info")
    assert timeouts == pytest.approx([1.0, 0.4])


def test_late_recorder_drain_reply_does_not_extend_the_cleanup_budget(tmp_path):
    elapsed = [0.0]
    session = RecordingSession(None, tmp_path, {})

    def late_reply(command):
        elapsed[0] = 2
        return {"quiesced": True}

    session._control = late_reply
    with cleanup_budget(1, clock=lambda: elapsed[0]):
        with pytest.raises(BackendTimeoutError):
            session.quiesce()


def test_recorder_process_wait_uses_remaining_cleanup_time(tmp_path):
    elapsed = [0.0]
    waits = []

    class Process:
        def wait(self, timeout):
            waits.append(timeout)
            elapsed[0] = 2

    session = RecordingSession(None, tmp_path, {}, Process())
    session.quiesce = lambda: ()
    session._control = lambda command: {}
    with cleanup_budget(1, clock=lambda: elapsed[0]):
        with pytest.raises(BackendTimeoutError):
            session.shutdown()
    assert waits == [1]
