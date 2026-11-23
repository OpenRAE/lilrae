"""The shipped guided profile qualifies on TechVault attacker-target (#1700)."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aptl.cli.lab import app as lab_app
from aptl.validation.participant_profile import (
    ParticipantProfileError,
    load_participant_profile,
)
from aptl.validation.participant_qualification import (
    ParticipantQualificationError,
    ParticipantQualificationReport,
    load_participant_qualification_report,
    participant_qualification_attestation_payload,
)
from tests.test_participant_qualification import (
    _QUALIFICATION_PRIVATE_KEY,
    PROJECT_ROOT,
    _canonical_json_bytes,
    _passing_report_payload,
    _write_attested_bundle,
)


def _materialized_profile_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(
        PROJECT_ROOT / "participant-profiles",
        project / "participant-profiles",
    )
    (project / "scenarios").mkdir()
    shutil.copy2(
        PROJECT_ROOT / "scenarios" / "catalog.json",
        project / "scenarios" / "catalog.json",
    )
    shutil.copy2(
        PROJECT_ROOT / "scenarios" / "techvault-attacker-target.sdl.yaml",
        project / "scenarios" / "techvault-attacker-target.sdl.yaml",
    )
    shutil.copy2(PROJECT_ROOT / "docker-compose.yml", project / "docker-compose.yml")
    for source in (
        "src/aptl/workbench/profiles.py",
        "src/aptl/core/mcp_policy.py",
        "src/aptl/core/participant_mcp_policy.json",
    ):
        target = project / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / source, target)
    for package in ("mcp-red", "mcp-indexer", "mcp-wazuh"):
        for filename in (
            "package-lock.json",
            "docker-lab-config.json",
            "build/index.js",
        ):
            source = PROJECT_ROOT / "mcp" / package / filename
            target = project / "mcp" / package / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return project


def test_cli_qualifies_and_persists_a_contained_report(tmp_path: Path) -> None:
    project = _materialized_profile_project(tmp_path)
    report, public_key, _ = _write_attested_bundle(
        project,
        _passing_report_payload(),
    )

    result = CliRunner().invoke(
        lab_app,
        [
            "qualify-profile",
            "--project-dir",
            str(project),
            "--report",
            str(report),
            "--public-key",
            str(public_key),
            "--run-id",
            "profile-proof",
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["conforming"] is True
    assert (
        project
        / "runs"
        / "profile-proof"
        / "participant-profile"
        / "qualification.json"
    ).is_file()


def test_cli_fails_on_nonconforming_report(tmp_path: Path) -> None:
    project = _materialized_profile_project(tmp_path)
    payload = _passing_report_payload()
    payload["offline"]["download_attempts"] = 1
    report, public_key, _ = _write_attested_bundle(project, payload)

    result = CliRunner().invoke(
        lab_app,
        [
            "qualify-profile",
            "--project-dir",
            str(project),
            "--report",
            str(report),
            "--public-key",
            str(public_key),
            "--run-id",
            "profile-proof",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["conforming"] is False


def test_report_tampering_invalidates_attestation(tmp_path: Path) -> None:
    project = _materialized_profile_project(tmp_path)
    report_path, public_key_path, evidence = _write_attested_bundle(
        project,
        _passing_report_payload(),
    )
    tampered = evidence.report.model_dump(mode="json")
    tampered["offline"]["download_attempts"] = 1
    report_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(
        ParticipantQualificationError,
        match="attestation is invalid",
    ):
        load_participant_qualification_report(
            project,
            report_path,
            public_key_path,
        )


@pytest.mark.parametrize("artifact", ["run_record", "snapshot"])
def test_canonical_evidence_digest_drift_is_rejected(
    tmp_path: Path,
    artifact: str,
) -> None:
    project = _materialized_profile_project(tmp_path)
    report_path, public_key_path, evidence = _write_attested_bundle(
        project,
        _passing_report_payload(),
    )
    reference = getattr(evidence.report, f"{artifact}_ref")
    (project / reference).write_text("{}", encoding="utf-8")

    with pytest.raises(
        ParticipantQualificationError,
        match=f"{artifact.replace('_', ' ')} digest mismatch",
    ):
        load_participant_qualification_report(
            project,
            report_path,
            public_key_path,
        )


def test_run_record_and_snapshot_must_be_correlated(tmp_path: Path) -> None:
    project = _materialized_profile_project(tmp_path)
    payload = _passing_report_payload()
    report_path, public_key_path, evidence = _write_attested_bundle(project, payload)
    altered_run_record = json.loads(json.dumps(evidence.run_record))
    altered_run_record["backend_evidence"]["range_snapshot"] = {
        "containers": [],
        "networks": [],
    }
    run_record_bytes = _canonical_json_bytes(altered_run_record)
    (project / evidence.report.run_record_ref).write_bytes(run_record_bytes)
    payload["run_record_sha256"] = hashlib.sha256(run_record_bytes).hexdigest()
    payload["attestation"]["signature"] = "AA=="
    unsigned = ParticipantQualificationReport.model_validate(payload)
    payload["attestation"]["signature"] = base64.b64encode(
        _QUALIFICATION_PRIVATE_KEY.sign(
            participant_qualification_attestation_payload(unsigned)
        )
    ).decode("ascii")
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ParticipantQualificationError,
        match="evidence is not correlated",
    ):
        load_participant_qualification_report(
            project,
            report_path,
            public_key_path,
        )


def test_mcp_artifact_bytes_must_match_asset_lock(tmp_path: Path) -> None:
    project = _materialized_profile_project(tmp_path)
    artifact = project / "mcp" / "mcp-red" / "build" / "index.js"
    artifact.write_bytes(artifact.read_bytes() + b"\n// drift")

    with pytest.raises(
        ParticipantProfileError,
        match="profile reference digest mismatch",
    ):
        load_participant_profile(
            project,
            project / "participant-profiles" / "guided-purple-v1" / "profile.json",
        )
