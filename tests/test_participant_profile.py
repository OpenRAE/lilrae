"""Contract tests for the versioned bounded participant profile (APP-2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aptl.validation.participant_profile import (
    ParticipantProfileError,
    load_participant_profile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = (
    PROJECT_ROOT / "participant-profiles" / "guided-purple-v1" / "profile.json"
)


def _write_modified_manifest(
    tmp_path: Path,
    mutate,
    *,
    copy_narrative: bool = False,
) -> Path:
    manifest = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    mutate(manifest)
    path = tmp_path / "participant-profiles" / "guided-purple-v1" / "profile.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    if copy_narrative:
        source = PROFILE_PATH.with_name("narrative.json")
        path.with_name("narrative.json").write_bytes(source.read_bytes())
    return path


def test_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    path = _write_modified_manifest(
        tmp_path,
        lambda manifest: manifest.update(event_name="black-hat"),
    )

    with pytest.raises(ParticipantProfileError, match="invalid participant profile"):
        load_participant_profile(tmp_path, path)


def test_manifest_rejects_digest_drift(tmp_path: Path) -> None:
    def mutate(manifest: dict) -> None:
        manifest["narrative"]["sha256"] = "0" * 64

    path = _write_modified_manifest(tmp_path, mutate, copy_narrative=True)

    with pytest.raises(ParticipantProfileError, match="digest mismatch"):
        load_participant_profile(tmp_path, path)


def test_manifest_rejects_reference_traversal(tmp_path: Path) -> None:
    def mutate(manifest: dict) -> None:
        manifest["narrative"]["path"] = "../outside.json"

    path = _write_modified_manifest(tmp_path, mutate)

    with pytest.raises(ParticipantProfileError, match="unsafe profile reference"):
        load_participant_profile(tmp_path, path)


def test_required_narrative_operations_have_readiness_checks() -> None:
    profile = load_participant_profile(PROJECT_ROOT, PROFILE_PATH)

    required_capabilities = {
        operation.capability_id
        for operation in profile.narrative.operations
        if operation.classification == "required"
    }
    checked_capabilities = {check.capability_id for check in profile.readiness.checks}
    assert required_capabilities <= checked_capabilities
    assert {
        "red.kali-command",
        "red.ssh-authentication-attack",
        "blue.indexer-investigation",
        "blue.wazuh-investigation",
        "browser.aptl-guide",
        "browser.kali-desktop",
        "browser.soc-wazuh",
    } <= required_capabilities
    assert {
        check.subject_id
        for check in profile.readiness.checks
        if check.kind == "browser-operation"
    } == set(profile.browser_refs)
