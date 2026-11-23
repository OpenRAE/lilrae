"""The native read command streams complete output and reaps its child."""

import sys
import tempfile

import pytest

from aptl.core.deployment._compose_log_capture import StreamExit, stream_command


def _run(tmp_path, script: str, progress_timeout: float):
    stdout, stderr = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    result = stream_command(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=None,
        stdout=stdout,
        stderr=stderr,
        progress_timeout=progress_timeout,
    )
    stdout.seek(0)
    return result, stdout.read()


def test_native_read_command_keeps_every_byte(tmp_path):
    script = (
        "import sys;sys.stdout.write('accepted complete line\\n' + 'x'*10000000);"
        "sys.stdout.flush()"
    )
    result, output = _run(tmp_path, script, 10)
    assert result == StreamExit(0, timed_out=False, failed_pipe=False)
    assert output == b"accepted complete line\n" + b"x" * 10_000_000


def test_stalled_read_times_out_and_keeps_accepted_output(tmp_path):
    script = "import time;print('accepted complete line',flush=True);time.sleep(20)"
    result, output = _run(tmp_path, script, 0.5)
    assert result.timed_out is True
    assert output == b"accepted complete line\n"


def test_steady_read_longer_than_the_progress_timeout_completes(tmp_path):
    script = (
        "import time\n"
        "for n in range(6):\n"
        "    print(n, flush=True); time.sleep(0.2)\n"
    )
    result, output = _run(tmp_path, script, 0.5)
    assert result == StreamExit(0, timed_out=False, failed_pipe=False)
    assert output.split() == [b"0", b"1", b"2", b"3", b"4", b"5"]


@pytest.mark.parametrize("method", ["logs", "exec"])
def test_backend_streams_use_owned_identity_and_existing_transport(
    tmp_path, monkeypatch, method
):
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    import aptl.core.deployment._compose_queries as owner

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

    def stream(command, **kwargs):
        seen.append((command, kwargs))
        return StreamExit(0, timed_out=False, failed_pipe=False)

    monkeypatch.setattr(owner, "stream_command", stream)
    out, err = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    if method == "logs":
        backend.container_logs_stream(
            "soc", since="start", until="end", stdout=out, stderr=err
        )
        expected = ["docker", "logs", "--since", "start", "--until", "end", "owned-soc"]
    else:
        backend.container_exec_stream("soc", ["cat", "--", "/f"], stdout=out, stderr=err)
        expected = ["docker", "exec", "owned-soc", "cat", "--", "/f"]
    command, kwargs = seen[0]
    assert command == expected
    assert kwargs["stdout"] is out
    assert kwargs["stderr"] is err
    assert kwargs["progress_timeout"] > 0
    assert kwargs["env"] == {"DOCKER_HOST": "ssh://fixture"}
