"""Extracted production MCP -> real SSH broker -> harvested evidence.

Requires the built red MCP and Docker. The required MCP CI lane supplies both.
The SSH workload is the existing isolated broker fixture, not the full SOC.
"""

import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

import pytest

from aptl.core.evidence.outcomes import CollectorStatus
from aptl.utils.mcp_packaging import archive_project, flatten_common_dependencies
from aptl_techvault.evidence.techvault import (
    RedteamSessionTranscriptSource,
    TranscriptFrame,
    TranscriptSession,
)
from tests.test_kali_capture_compose import (  # noqa: F401 -- shared pytest fixtures
    capture_broker,
    capture_image,
)
from tests.test_mcp_payload_processes import _copy_readonly
from tests.test_mcp_transport_processes import initialize, request

pytestmark = [
    pytest.mark.integration,
    pytest.mark.parametrize("capture_broker", ["a" * 32], indirect=True),
]
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def red_payload(tmp_path_factory):
    """Use the shipping archive boundary, then delete the staging build tree."""
    assert shutil.which("node"), "The capture regression requires Node"
    root = tmp_path_factory.mktemp("red-capture-payload")
    project = root / "build-tree"
    for package in ("aptl-mcp-common", "mcp-red"):
        source = REPO / "mcp" / package
        target = project / "mcp" / package
        target.mkdir(parents=True)
        for name in ("build", "node_modules", "package.json", "package-lock.json"):
            path = source / name
            assert path.exists(), f"Build the production MCP before testing: {path}"
            if path.is_dir():
                shutil.copytree(
                    path, target / name, symlinks=True, copy_function=_copy_readonly
                )
            else:
                _copy_readonly(path, target / name)
        if package == "mcp-red":
            _copy_readonly(
                source / "docker-lab-config.json", target / "docker-lab-config.json"
            )
    flatten_common_dependencies(project)
    archive = root / "payload.tar"
    archive_project(project, archive)
    shutil.rmtree(project)
    extracted = root / "installed"
    with tarfile.open(archive) as payload:
        payload.extractall(extracted, filter="data")
    assert not project.exists()
    return extracted


class MCP:
    def __init__(self, root, payload, broker):
        self.archive = root / "retained-runs"
        self.run_id = broker["run_id"]
        home = root / "home"
        keys = home / ".ssh"
        keys.mkdir(parents=True, mode=0o700)
        shutil.copy2(broker["key"], keys / "aptl_lab_key")
        state = root / "state"
        state.mkdir(mode=0o700)
        (state / "trace-context.json").write_text(
            json.dumps(
                {
                    "trace_id": self.run_id,
                    "span_id": "b" * 16,
                    "trace_flags": "01",
                }
            )
        )
        self.log_path = root / "mcp.stderr"
        self.log = self.log_path.open("w")
        self.log_path.chmod(0o600)
        self.process = subprocess.Popen(
            [shutil.which("node"), str(payload / "mcp/mcp-red/build/index.js")],
            cwd=home,
            env={
                "PATH": os.defpath,
                "HOME": str(home),
                "APTL_MCP_DISABLE_DOTENV": "1",
                "APTL_STATE_DIR": str(state),
                "APTL_MCP_RUN_STORE_BASE": str(self.archive),
                "LILRAE_MCP_CAPTURE_CONTAINER": broker["container"],
                "APTL_HP_KALI_SSH_PROXY_2023": broker["port"],
            },
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
        )
        self.identifier = 1

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def tool(self, name, **arguments):
        self.identifier += 1
        result = request(
            self.process,
            "tools/call",
            self.identifier,
            {"name": name, "arguments": arguments},
        )
        assert not result.get("isError"), result
        return json.loads(result["content"][0]["text"])

    def open_session(self, session_id):
        result = self.tool("kali_background_session", session_id=session_id)
        assert result["success"], result
        result = self.tool(
            "kali_session_command",
            session_id=session_id,
            command=f"printf 'marker-{session_id}\\n'",
        )
        assert result["success"], result
        assert f"marker-{session_id}" in result["output"]

    def session_dir(self, session_id):
        return self.archive / self.run_id / "kali-side" / session_id

    def shutdown(self):
        self.process.terminate()
        status = self.process.wait(timeout=120)
        self.log.flush()
        return status

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=15)
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.close()


@pytest.fixture
def mcp(tmp_path, red_payload, capture_broker):
    client = MCP(tmp_path, red_payload, capture_broker)
    try:
        initialize(client.process)
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        yield client
    finally:
        client.close()


def _docker(*args):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True, timeout=45
    ).stdout


def _eventually(read, *, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = read()
        if result:
            return result
        time.sleep(0.2)
    pytest.fail("Capture lifecycle did not reach the required state")


def _accepted(broker):
    path = f"/var/log/aptl/captures/{broker['run_id']}/accepted-sessions.jsonl"
    return [
        json.loads(line)["session_id"]
        for line in _docker("exec", broker["container"], "cat", path).splitlines()
    ]


def _read_session(directory):
    metadata = json.loads((directory / "metadata.json").read_text())
    frames = tuple(
        TranscriptFrame(
            item["sequence"],
            item["timestamp"],
            item["direction"],
            base64.b64decode(item["data_b64"], validate=True),
        )
        for item in map(
            json.loads, (directory / "frames.jsonl").read_text().splitlines()
        )
    )
    assert metadata["session_id"] == directory.name
    assert metadata["frame_count"] == len(frames)
    assert metadata["plan_id"] == "capture-plan-1"
    assert metadata["binding_id"] == "aptl.collector.redteam-session-transcript"
    assert not (directory / "capture-harvest-failure.json").exists()
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())
    return TranscriptSession(
        session_id=metadata["session_id"],
        started_at=metadata["started_at"],
        finished_at=metadata["finished_at"],
        close_reason=metadata["close_reason"],
        frames=frames,
        final_chain_digest=metadata["final_chain_digest"],
        loss_count=metadata["loss_count"],
    )


def test_installed_mcp_harvests_agent_and_remote_closes(mcp, capture_broker):
    start = datetime.now(UTC).isoformat()
    mcp.open_session("agent-closed")
    assert mcp.tool("kali_close_session", session_id="agent-closed")["success"]
    assert (mcp.session_dir("agent-closed") / "metadata.json").is_file()

    mcp.open_session("remote-death")
    mcp.tool(
        "kali_session_command", session_id="remote-death", command="exit 7", raw=True
    )
    _eventually(lambda: (mcp.session_dir("remote-death") / "metadata.json").is_file())
    expected = {"agent-closed": "clean-exit", "remote-death": "remote-eof"}
    assert set(_accepted(capture_broker)) == set(expected)
    assert mcp.shutdown() == 0, mcp.log_path.read_text()[-4000:]
    _assert_archive(mcp, expected, start)


def test_installed_mcp_shutdown_harvests_active_shell_and_exec(mcp, capture_broker):
    start = datetime.now(UTC).isoformat()
    mcp.open_session("left-open")

    # Leave a one-shot exec in flight too; observe output at the real broker
    # before signalling the production MCP process. No close tool runs for it.
    mcp.send(
        {
            "jsonrpc": "2.0",
            "id": 1000,
            "method": "tools/call",
            "params": {
                "name": "kali_run_command",
                "arguments": {"command": "printf 'marker-exec\\n'; sleep 600"},
            },
        }
    )
    exec_id = _eventually(
        lambda: next(
            (value for value in _accepted(capture_broker) if value.startswith("exec-")),
            None,
        )
    )
    frames_path = f"/var/log/aptl/captures/{mcp.run_id}/sessions/{exec_id}/frames.jsonl"
    _eventually(
        lambda: any(
            b"marker-exec" in base64.b64decode(json.loads(line)["data_b64"])
            for line in _docker(
                "exec", capture_broker["container"], "cat", frames_path
            ).splitlines()
        )
    )
    expected = set(_accepted(capture_broker))
    assert expected == {"left-open", exec_id}
    assert mcp.shutdown() == 0, mcp.log_path.read_text()[-4000:]

    _assert_archive(
        mcp, {"left-open": "forced-teardown", exec_id: "forced-teardown"}, start
    )


def _assert_archive(mcp, reasons, start):
    expected = set(reasons)
    run = mcp.archive / mcp.run_id
    assert {path.name for path in (run / "kali-side").iterdir()} == expected
    assert {
        path.stem for path in (run / "mcp-side/sessions").glob("*.jsonl")
    } == expected
    sessions = [_read_session(mcp.session_dir(session_id)) for session_id in expected]
    assert {session.session_id: session.close_reason for session in sessions} == reasons
    for session in sessions:
        marker = (
            b"marker-exec"
            if session.session_id.startswith("exec-")
            else f"marker-{session.session_id}".encode()
        )
        assert marker in b"".join(frame.data for frame in session.frames)

    # Reuse the actual collector: a complete census, final metadata, and valid
    # custody hashes must be accepted together, rather than checking files only.
    result = RedteamSessionTranscriptSource(
        lambda: sorted(expected), lambda: sessions
    ).fetch(start, datetime.now(UTC).isoformat())
    assert result.status is CollectorStatus.OK
    assert result.source_pipeline["session_count"] == len(expected)


@pytest.mark.parametrize("fault", ["container-missing", "metadata-missing"])
def test_installed_mcp_fails_closed_when_capture_cannot_finalize(
    mcp, capture_broker, fault
):
    mcp.open_session("capture-failure")
    if fault == "container-missing":
        _docker("rm", "-f", capture_broker["container"])
        allowed = {
            "aptl.capture-harvest.container-missing",
            "aptl.capture-harvest.finalize-failed",
        }
    else:
        path = f"/var/log/aptl/captures/{mcp.run_id}/sessions/capture-failure"
        # A real writer failure: the unprivileged broker cannot create its
        # final metadata. Keep the frames readable for the real docker cp.
        _docker(
            "exec", "--user", "kali", capture_broker["container"], "chmod", "0500", path
        )
        allowed = {"aptl.capture-harvest.metadata-missing"}
    assert mcp.shutdown() == 1, mcp.log_path.read_text()[-4000:]
    directory = mcp.session_dir("capture-failure")
    failure = json.loads((directory / "capture-harvest-failure.json").read_text())
    assert failure["failure"] in allowed
    assert failure["run_id"] == mcp.run_id
    assert failure["session_id"] == "capture-failure"
    assert not (directory / "metadata.json").exists()
