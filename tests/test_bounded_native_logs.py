"""The native log command enforces its byte budget while reading pipes."""

import sys
import pytest
from aptl.core.deployment._compose_log_capture import capture_logs


@pytest.mark.parametrize("timeout", [False, True])
def test_native_log_command_keeps_complete_prefix_and_reaps_child(tmp_path, timeout):
    script = (
        "import sys,time;print('accepted complete line',flush=True);time.sleep(20)"
        if timeout
        else "import sys;sys.stdout.write('accepted complete line\\n' + 'x'*10000000);sys.stdout.flush()"
    )
    result = capture_logs(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=None,
        timeout=0.5 if timeout else 10,
        max_bytes=4096,
    )
    assert result.stdout == "accepted complete line\n"
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 4096
    assert result.timed_out is timeout
    assert result.truncated is (not timeout)


def test_backend_bounded_logs_use_owned_identity_and_existing_transport(
    tmp_path, monkeypatch
):
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    import aptl.core.deployment._compose_log_capture as owner

    backend = DockerComposeBackend(project_dir=tmp_path, project_name="test")
    monkeypatch.setattr(
        backend, "_resolve_owned_container_id", lambda name: "owned-soc"
    )
    monkeypatch.setattr(
        backend,
        "_command_kwargs",
        lambda *a, **k: {"cwd": tmp_path, "env": {"DOCKER_HOST": "ssh://fixture"}},
    )
    seen = []

    def capture(command, **kwargs):
        seen.append((command, kwargs))
        return owner.LogCapture(command, 0, "accepted\n", "")

    monkeypatch.setattr(owner, "capture_logs", capture)
    result = backend.container_logs_capture(
        "soc", since="start", until="end", timeout=3, max_bytes=4096
    )
    assert result.stdout == "accepted\n"
    command, kwargs = seen[0]
    assert command == [
        "docker",
        "logs",
        "--since",
        "start",
        "--until",
        "end",
        "owned-soc",
    ]
    assert kwargs["max_bytes"] == 4096
    assert kwargs["timeout"] == 3
    assert kwargs["env"] == {"DOCKER_HOST": "ssh://fixture"}
