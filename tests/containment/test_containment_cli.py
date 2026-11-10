"""The ``lilrae containment run`` standard-input and standard-output seam."""

import base64
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aptl.cli.main import app
from aptl.core.containment import REQUEST_SCHEMA, ExecutionReport

runner = CliRunner()


def _request(**overrides: object) -> str:
    document: dict[str, object] = {
        "schema_version": REQUEST_SCHEMA,
        "profile": "linux-full",
        "label": "cli",
        "argv": ["/bin/true"],
        "env": {},
        "stdin": base64.b64encode(b"").decode(),
        "input_dir": None,
        "limits": {"deadline_seconds": 1, "max_output_bytes": 64},
        "network": "none",
    }
    document.update(overrides)
    return json.dumps(document)


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    return root


def test_an_absent_engine_produces_a_refusal_report(state_root: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["containment", "run", "--state-root", str(state_root), "--engine-root", str(tmp_path / "none")],
        input=_request(),
    )

    assert result.exit_code == 0, result.output
    report = ExecutionReport.model_validate_json(result.stdout)
    assert report.status == "refused"
    assert report.reason == "engine_unavailable"
    assert report.run_dir is None


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        _request(network="relay"),
        _request()[:-1] + ', "label": "x"}',
    ],
)
def test_an_invalid_request_exits_with_status_two(state_root: Path, payload: str) -> None:
    result = runner.invoke(
        app, ["containment", "run", "--state-root", str(state_root)], input=payload
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "invalid containment request" in result.stderr
    assert "relay" not in result.stderr


def test_an_oversized_request_exits_with_status_two(
    state_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("aptl.cli.containment.MAX_REQUEST_BYTES", 16)

    result = runner.invoke(
        app, ["containment", "run", "--state-root", str(state_root)], input=_request()
    )

    assert result.exit_code == 2
    assert "exceeds" in result.stderr


def test_a_missing_state_root_exits_with_status_two(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["containment", "run", "--state-root", str(tmp_path / "absent")], input=_request()
    )

    assert result.exit_code == 2
    assert "state root" in result.stderr


def test_a_shared_state_root_exits_with_status_two(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)

    result = runner.invoke(
        app, ["containment", "run", "--state-root", str(shared)], input=_request()
    )

    assert result.exit_code == 2
    assert "state root" in result.stderr
