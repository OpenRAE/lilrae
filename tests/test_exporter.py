"""Unit tests for run export functionality."""

import errno
import json
import os
import stat
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aptl.core.archival import SealVerificationError
from aptl.core.exporter import export_local, export_s3, _sha256_file
from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import PathContainmentError

posix_modes = pytest.mark.skipif(os.name != "posix", reason="POSIX modes only")


@pytest.fixture
def common_umask():
    """Run under the usual 022 umask, which leaves group and other read bits."""
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


class TestSha256File:
    """Tests for file hashing utility."""

    def test_hash_known_content(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        digest = _sha256_file(f)
        assert len(digest) == 64
        # Known SHA-256 of "hello world"
        assert digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


class TestExportLocal:
    """Tests for local export."""

    def _make_run(self, tmp_path, run_id="test-run"):
        store = LocalRunStore(tmp_path / "runs")
        store.create_run(run_id)
        store.write_json(run_id, "manifest.json", {
            "run_id": run_id,
            "scenario_id": "sc1",
            "scenario_name": "Test Scenario",
        })
        store.write_file(run_id, "data.txt", b"some test data")
        store.write_json(run_id, "wazuh/alerts.json", [{"alert": 1}])
        return store

    def test_export_creates_archive(self, tmp_path):
        store = self._make_run(tmp_path)
        output_dir = tmp_path / "export"

        archive = export_local(store, "test-run", output_dir)

        assert archive.exists()
        assert archive.name == "test-run.tar.gz"
        assert archive.parent == output_dir

    def test_export_archive_contains_files(self, tmp_path):
        store = self._make_run(tmp_path)
        output_dir = tmp_path / "export"

        archive = export_local(store, "test-run", output_dir)

        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            assert "test-run/manifest.json" in names
            assert "test-run/data.txt" in names
            assert "test-run/wazuh/alerts.json" in names
            assert "test-run/checksums.sha256" in names

    def test_export_checksums_travel_in_archive_without_mutating_run(self, tmp_path):
        # ADR-050: export is read-only over the run archive. The checksum
        # manifest lives inside the tarball; the source run directory is never
        # mutated (a sealed archive is immutable).
        store = self._make_run(tmp_path)
        output_dir = tmp_path / "export"

        archive = export_local(store, "test-run", output_dir)

        assert not (store.get_run_path("test-run") / "checksums.sha256").exists()

        with tarfile.open(archive, "r:gz") as tar:
            content = tar.extractfile("test-run/checksums.sha256").read().decode()
        assert "manifest.json" in content
        assert "data.txt" in content
        # Each line should have a 64-char hash + two spaces + filename
        for line in content.strip().splitlines():
            parts = line.split("  ", 1)
            assert len(parts) == 2
            assert len(parts[0]) == 64

    def test_export_nonexistent_run(self, tmp_path):
        store = LocalRunStore(tmp_path / "runs")
        import pytest
        with pytest.raises(FileNotFoundError):
            export_local(store, "nonexistent", tmp_path / "export")

    def test_sealed_run_exports_exactly_the_verified_inventory(self, tmp_path):
        # A sealed run is packaged as exactly its verified seal inventory; a
        # non-inventory file left in the run dir does not travel.
        import json
        import tarfile as _tarfile

        from tests.archival_fixtures import completed_context
        from aptl.core.archival.coordinator import finalize_terminal_attempt
        from aptl.core.archival.layout import RUN_MANIFEST_RELPATH, SEAL_MARKER_RELPATH

        store = LocalRunStore(tmp_path / "runs")
        context = completed_context()
        finalize_terminal_attempt(context, store=store)
        # A stray non-inventory file (not part of the seal).
        (store.get_run_path(context.attempt_id) / "stray.txt").write_text("not sealed")

        archive = export_local(store, context.attempt_id, tmp_path / "export")
        with _tarfile.open(archive, "r:gz") as tar:
            names = set(tar.getnames())
            marker = json.loads(
                tar.extractfile(f"{context.attempt_id}/{SEAL_MARKER_RELPATH}").read()
            )
        expected = {f"{context.attempt_id}/{RUN_MANIFEST_RELPATH}",
                    f"{context.attempt_id}/{SEAL_MARKER_RELPATH}",
                    f"{context.attempt_id}/checksums.sha256"}
        for entry in marker["inventory"]:
            expected.add(f"{context.attempt_id}/{entry['path']}")
        assert names == expected
        assert f"{context.attempt_id}/stray.txt" not in names

    def test_export_creates_output_dir(self, tmp_path):
        store = self._make_run(tmp_path)
        output_dir = tmp_path / "deeply" / "nested" / "dir"

        archive = export_local(store, "test-run", output_dir)
        assert archive.exists()
        assert output_dir.exists()

    @posix_modes
    @pytest.mark.usefixtures("common_umask")
    def test_export_creates_owner_only_directory_and_archive(self, tmp_path):
        store = self._make_run(tmp_path)
        output_dir = tmp_path / "exports"

        archive = export_local(store, "test-run", output_dir)

        assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(archive.stat().st_mode) == 0o600

    @posix_modes
    @pytest.mark.usefixtures("common_umask")
    def test_export_keeps_existing_directory_mode_and_tightens_old_archive(
        self, tmp_path
    ):
        # An existing directory keeps the mode its owner chose; an archive an
        # earlier export left with the umask's mode is rewritten owner-only.
        store = self._make_run(tmp_path)
        output_dir = tmp_path / "shared"
        output_dir.mkdir(mode=0o755)
        (output_dir / "test-run.tar.gz").write_bytes(b"older export")

        archive = export_local(store, "test-run", output_dir)

        assert stat.S_IMODE(output_dir.stat().st_mode) == 0o755
        assert stat.S_IMODE(archive.stat().st_mode) == 0o600
        with tarfile.open(archive, "r:gz") as tar:
            assert "test-run/manifest.json" in tar.getnames()

    @posix_modes
    @pytest.mark.usefixtures("common_umask")
    def test_export_refuses_a_symlink_at_the_archive_path(self, tmp_path):
        # A link planted in a shared output directory must not redirect the
        # export, its truncation or its mode change to the file it points to.
        store = self._make_run(tmp_path)
        output_dir = tmp_path / "shared"
        output_dir.mkdir(mode=0o777)
        unrelated = tmp_path / "unrelated.txt"
        unrelated.write_text("keep me")
        (output_dir / "test-run.tar.gz").symlink_to(unrelated)

        with pytest.raises(OSError) as raised:
            export_local(store, "test-run", output_dir)

        assert raised.value.errno == errno.ELOOP
        assert unrelated.read_text() == "keep me"
        assert stat.S_IMODE(unrelated.stat().st_mode) == 0o644


class TestExportThenExportBundle:
    """``aptl runs export`` and ``export-bundle`` share ``./exports`` (#1282)."""

    @posix_modes
    @pytest.mark.usefixtures("common_umask")
    def test_bundle_accepts_the_default_directory_export_created(
        self, tmp_path, monkeypatch
    ):
        from typer.testing import CliRunner

        from aptl.cli.main import app
        from tests._bundle_fixtures import build_ready_to_seal_run

        project = tmp_path / "project"
        build_ready_to_seal_run(project / "runs" / "run-1", run_id="run-1")
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        exported = runner.invoke(app, ["runs", "export", "run-1", "-d", str(project)])
        bundled = runner.invoke(
            app, ["runs", "export-bundle", "run-1", "-d", str(project)]
        )

        assert exported.exit_code == 0, exported.output
        assert bundled.exit_code == 0, bundled.output
        assert sorted(path.name for path in (tmp_path / "exports").iterdir()) == [
            "run-1.evidence-bundle.tar",
            "run-1.tar.gz",
        ]


def _sealed_project(tmp_path: Path) -> tuple[Path, LocalRunStore, str]:
    """Seal one run under ``project/runs``; return the project, store and run id."""
    from aptl.core.archival.coordinator import finalize_terminal_attempt
    from tests.archival_fixtures import completed_context

    project = tmp_path / "project"
    store = LocalRunStore(project / "runs")
    context = completed_context()
    finalize_terminal_attempt(context, store=store)
    return project, store, context.attempt_id


def _rewrite_manifest(run_path: Path) -> None:
    """Change the sealed manifest's bytes, so its digest no longer matches."""
    manifest = run_path / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")


def _symlink_manifest(run_path: Path) -> None:
    """Swap the sealed manifest for a symlink to a copy of its own bytes."""
    manifest = run_path / "manifest.json"
    copy = run_path.parents[1] / "manifest-copy.json"
    copy.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(copy)


def _reported(result) -> str:
    """What the command printed, plus the error that ended it, if any."""
    return f"{result.output}{result.exception!r}"


class TestRefusedExportCreatesNoDirectory:
    """A run that export refuses leaves no new output directory (#1334)."""

    @pytest.mark.parametrize(
        ("tamper", "error"),
        [
            (_rewrite_manifest, SealVerificationError),
            (_symlink_manifest, PathContainmentError),
        ],
        ids=["rewritten-manifest", "symlinked-manifest"],
    )
    def test_export_local_checks_the_seal_before_creating_the_directory(
        self, tmp_path, tamper, error
    ):
        _, store, run_id = _sealed_project(tmp_path)
        tamper(store.get_run_path(run_id))

        with pytest.raises(error):
            export_local(store, run_id, tmp_path / "exports" / "nested")

        assert not (tmp_path / "exports").exists()

    @pytest.mark.parametrize(
        "extra_args",
        [[], ["-o", "out/nested"], ["--s3-bucket", "bucket"]],
        ids=["default-output-dir", "missing-output-dir", "s3"],
    )
    def test_runs_export_refusal_creates_no_output_directory(
        self, tmp_path, monkeypatch, extra_args
    ):
        from typer.testing import CliRunner

        from aptl.cli.main import app

        project, store, run_id = _sealed_project(tmp_path)
        _rewrite_manifest(store.get_run_path(run_id))
        boto3 = MagicMock()
        monkeypatch.setattr("aptl.core.exporter.boto3", boto3)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(
            app, ["runs", "export", run_id, "-d", str(project), *extra_args]
        )

        assert result.exit_code == 1
        assert "manifest does not match the marker digest" in _reported(result)
        # Neither ./exports, ./out nor anything else appeared beside the project.
        assert [path.name for path in tmp_path.iterdir()] == ["project"]
        boto3.client.assert_not_called()


class TestExportS3:
    """Tests for S3 export (mocked)."""

    def _make_run(self, tmp_path, run_id="test-run"):
        store = LocalRunStore(tmp_path / "runs")
        store.create_run(run_id)
        store.write_json(run_id, "manifest.json", {
            "run_id": run_id,
            "scenario_id": "sc1",
            "scenario_name": "Test Scenario",
        })
        store.write_file(run_id, "data.txt", b"some data")
        return store

    @patch("aptl.core.exporter.boto3", create=True)
    def test_export_s3_returns_uri(self, mock_boto3, tmp_path):
        store = self._make_run(tmp_path)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uri = export_s3(store, "test-run", "my-bucket", "runs/", tmp_path / "export")

        assert uri == "s3://my-bucket/runs/test-run.tar.gz"

    @patch("aptl.core.exporter.boto3", create=True)
    def test_export_s3_uploads_archive_and_manifest(self, mock_boto3, tmp_path):
        store = self._make_run(tmp_path)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        export_s3(store, "test-run", "my-bucket", "runs", tmp_path / "export")

        # Should have called upload_file twice (archive + manifest)
        assert mock_client.upload_file.call_count == 2

        # Check archive upload
        archive_call = mock_client.upload_file.call_args_list[0]
        assert archive_call[0][1] == "my-bucket"
        assert archive_call[0][2] == "runs/test-run.tar.gz"

        # Check manifest upload
        manifest_call = mock_client.upload_file.call_args_list[1]
        assert manifest_call[0][1] == "my-bucket"
        assert manifest_call[0][2] == "runs/test-run/manifest.json"

    @patch("aptl.core.exporter.boto3", create=True)
    def test_export_s3_tags(self, mock_boto3, tmp_path):
        store = self._make_run(tmp_path)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        export_s3(store, "test-run", "my-bucket", "runs/", tmp_path / "export")

        archive_call = mock_client.upload_file.call_args_list[0]
        extra_args = archive_call[1].get("ExtraArgs", archive_call[0][3] if len(archive_call[0]) > 3 else {})
        assert "Tagging" in extra_args
        assert "run_id=test-run" in extra_args["Tagging"]

    def test_export_s3_without_boto3(self, tmp_path):
        store = self._make_run(tmp_path)
        import pytest
        import aptl.core.exporter as exporter_mod

        original = exporter_mod.boto3
        exporter_mod.boto3 = None
        try:
            with pytest.raises(ImportError, match="pipx inject aptl-labs boto3"):
                export_s3(store, "test-run", "bucket", "prefix", tmp_path / "export")
        finally:
            exporter_mod.boto3 = original

    @patch("aptl.core.exporter.boto3", create=True)
    def test_export_s3_creates_local_archive(self, mock_boto3, tmp_path):
        store = self._make_run(tmp_path)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        output_dir = tmp_path / "export"

        export_s3(store, "test-run", "my-bucket", "runs/", output_dir)

        archive = output_dir / "test-run.tar.gz"
        assert archive.exists()


class TestExportRedactionChain:
    """Exporter is packaging-only (ADR-029): it must not be the first
    place secrets are sanitized. These tests pin the chain — secrets
    written through the runstore arrive in the exported archive already
    redacted, with no raw secret left for the exporter to leak."""

    def test_export_archive_contains_redacted_json(self, tmp_path):
        store = LocalRunStore(tmp_path / "runs")
        store.create_run("rx")
        store.write_json("rx", "manifest.json", {"run_id": "rx", "scenario_name": "s"})
        # A control-plane-shaped secret routed through the runstore
        # must arrive on disk redacted.
        store.write_json(
            "rx",
            "soc/wazuh.json",
            {"api_key": "SECRET_AK", "host": "wazuh.indexer.lab"},
        )
        store.write_jsonl(
            "rx",
            "soc/events.jsonl",
            [{"trace_id": "tx", "log": "boot ok; Authorization: Bearer XYZ.TOKEN"}],
        )
        archive = export_local(store, "rx", tmp_path / "export")
        with tarfile.open(archive, "r:gz") as tar:
            wazuh_member = tar.getmember("rx/soc/wazuh.json")
            extracted = tar.extractfile(wazuh_member)
            assert extracted is not None
            wazuh_text = extracted.read().decode("utf-8")
            events_member = tar.getmember("rx/soc/events.jsonl")
            extracted_e = tar.extractfile(events_member)
            assert extracted_e is not None
            events_text = extracted_e.read().decode("utf-8")
        wazuh_data = json.loads(wazuh_text)
        assert wazuh_data == {"api_key": "[REDACTED]", "host": "wazuh.indexer.lab"}
        assert "SECRET_AK" not in wazuh_text
        # Inline-secret form inside a string value is masked too.
        assert "XYZ.TOKEN" not in events_text
        assert "Bearer [REDACTED]" in events_text
