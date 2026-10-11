"""CLI tests for ``aptl runs export-bundle`` and ``aptl runs verify-bundle``, and
for ``aptl runs export`` refusing a sealed run that fails verification."""

from __future__ import annotations

import errno
import json
import sys
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent))
import _bundle_fixtures as fixtures  # noqa: E402

from aptl.cli.main import app  # noqa: E402
from aptl.core.archival.coordinator import finalize_terminal_attempt  # noqa: E402
from aptl.core.archival.layout import SEAL_MARKER_RELPATH  # noqa: E402
from aptl.core.archival.seal import SealedArtifactSpec  # noqa: E402
from aptl.core.runstore import LocalRunStore  # noqa: E402
from tests.archival_fixtures import completed_context  # noqa: E402

runner = CliRunner()

_SEALED_ARTIFACT = "provenance/run-provenance.json"


def _project_with_run(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    run_dir = project / "runs" / "run-1"
    fixtures.build_ready_to_seal_run(run_dir, run_id="run-1", evidence_count=2)
    return project


def _missing_bundle(tmp_path: Path) -> Path:
    return tmp_path / "missing.tar"


def _truncated_bundle(tmp_path: Path) -> Path:
    """Export a bundle, then keep it only up to the middle of its first member's data."""
    project = _project_with_run(tmp_path)
    out = tmp_path / "exports"
    runner.invoke(
        app, ["runs", "export-bundle", "run-1", "-d", str(project), "-o", str(out)]
    )
    bundle = out / "run-1.evidence-bundle.tar"
    with tarfile.open(bundle, "r:") as tar:
        member = next(m for m in tar.getmembers() if m.size > 1)
    truncated = tmp_path / "truncated.tar"
    truncated.write_bytes(bundle.read_bytes()[: member.offset_data + member.size // 2])
    return truncated


def _sealed_project(tmp_path: Path) -> tuple[Path, Path]:
    """Seal one run under ``project/runs``; return the project and the run directory."""
    store = LocalRunStore(tmp_path / "project" / "runs")
    context = completed_context(
        sealed_artifacts=(
            SealedArtifactSpec(_SEALED_ARTIFACT, "application/json", "provenance"),
        )
    )
    store.write_json(
        context.attempt_id, _SEALED_ARTIFACT, {"seal_state": "ready-to-seal"}
    )
    finalize_terminal_attempt(context, store=store)
    return tmp_path / "project", store.get_run_path(context.attempt_id)


def _rewrite_artifact(run_dir: Path) -> None:
    (run_dir / _SEALED_ARTIFACT).write_text('{"tampered": true}')


def _symlink_artifact(run_dir: Path) -> None:
    """Swap the sealed artifact for a symlink to a copy of its own bytes."""
    artifact = run_dir / _SEALED_ARTIFACT
    copy = run_dir.parents[1] / "copy.json"
    copy.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(copy)


def _forge_marker_path(run_dir: Path) -> None:
    """Put a newline and a terminal escape into a path the seal marker lists."""
    marker_file = run_dir / SEAL_MARKER_RELPATH
    marker = json.loads(marker_file.read_text())
    marker["inventory"][0]["path"] = "evidence/x\n\x1b[31mforged"
    marker_file.write_text(json.dumps(marker))


class TestExportBundleCommand:
    def test_exports_and_reports_unsealed(self, tmp_path: Path) -> None:
        project = _project_with_run(tmp_path)
        out = tmp_path / "exports"
        result = runner.invoke(
            app,
            [
                "runs",
                "export-bundle",
                "run-1",
                "-d",
                str(project),
                "-o",
                str(out),
                "-p",
                "jsonl",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Exported evidence bundle" in result.output
        assert "root identity" in result.output
        assert "UNSEALED" in result.output
        assert (out / "run-1.evidence-bundle.tar").exists()

    def test_unknown_projection_is_rejected(self, tmp_path: Path) -> None:
        project = _project_with_run(tmp_path)
        result = runner.invoke(
            app,
            ["runs", "export-bundle", "run-1", "-d", str(project), "-p", "yaml"],
        )
        assert result.exit_code == 1
        assert "Unknown projection format" in result.output


class TestVerifyBundleCommand:
    def test_verifies_a_freshly_exported_bundle(self, tmp_path: Path) -> None:
        project = _project_with_run(tmp_path)
        out = tmp_path / "exports"
        runner.invoke(
            app, ["runs", "export-bundle", "run-1", "-d", str(project), "-o", str(out)]
        )
        bundle = out / "run-1.evidence-bundle.tar"
        result = runner.invoke(app, ["runs", "verify-bundle", str(bundle)])
        assert result.exit_code == 0, result.output
        assert "OK: bundle verified" in result.output

    def test_reports_failure_on_a_non_bundle(self, tmp_path: Path) -> None:
        bogus = tmp_path / "bogus.tar"
        bogus.write_bytes(b"not a tar archive")
        result = runner.invoke(app, ["runs", "verify-bundle", str(bogus)])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    @pytest.mark.parametrize(
        ("make_input", "reason"),
        [
            (_missing_bundle, f"cannot read bundle: [Errno {errno.ENOENT}] "),
            (_truncated_bundle, "archive is truncated or corrupt: unexpected end of data"),
        ],
        ids=["missing-path", "truncated"],
    )
    def test_reports_unreadable_input_without_a_traceback(
        self, tmp_path: Path, make_input, reason: str
    ) -> None:
        result = runner.invoke(app, ["runs", "verify-bundle", str(make_input(tmp_path))])
        assert result.exit_code == 1
        # A clean typer.Exit, not an exception that escaped the command.
        assert isinstance(result.exception, SystemExit), result.exception
        lines = result.stdout.splitlines()
        assert lines[:3] == ["root identity: None", "members: 0  seal: None", "FAILED:"]
        assert len(lines) == 4
        assert lines[3].startswith(f"  - {reason}")


class TestExportCommand:
    @pytest.mark.parametrize(
        ("tamper", "extra_args", "reason"),
        [
            (
                _rewrite_artifact,
                [],
                f"inventory artifact {_SEALED_ARTIFACT} does not match its checksum",
            ),
            (_symlink_artifact, [], "rejected path component 'run-provenance.json': "),
            (
                _forge_marker_path,
                [],
                "inventory artifact is absent: evidence/x\\n\\x1b[31mforged",
            ),
            (_rewrite_artifact, ["--s3-bucket", "bucket"], "does not match its checksum"),
        ],
        ids=["rewritten-artifact", "symlinked-artifact", "control-characters", "s3"],
    )
    def test_refuses_a_tampered_sealed_run_on_one_line(
        self, tmp_path: Path, monkeypatch, tamper, extra_args: list[str], reason: str
    ) -> None:
        project, run_dir = _sealed_project(tmp_path)
        tamper(run_dir)
        boto3 = MagicMock()
        monkeypatch.setattr("aptl.core.exporter.boto3", boto3)
        out = tmp_path / "exports"
        result = runner.invoke(
            app,
            ["runs", "export", run_dir.name, "-d", str(project), "-o", str(out)]
            + extra_args,
        )
        assert result.exit_code == 1
        # A clean typer.Exit, not an exception that escaped the command.
        assert isinstance(result.exception, SystemExit), result.exception
        assert result.stdout == ""
        assert result.stderr.startswith(f"Error: refused to export run {run_dir.name}: ")
        assert reason in result.stderr
        assert result.stderr.count("\n") == 1
        assert "\x1b" not in result.stderr
        # Nothing is written: no archive, and nothing is uploaded.
        assert not [path for path in out.rglob("*") if path.is_file()]
        boto3.client.assert_not_called()
