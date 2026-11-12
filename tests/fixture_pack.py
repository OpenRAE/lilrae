"""Owned fixture pack for generic lab-machinery tests (issue #985).

Core admission, content, realization, and live-gate tests use this small pack.
They do not depend on a released pack's changing content.
The production resolver admits it from ``tests/fixtures/packs/``.
That resolver runs env-packs' ``validate_pack`` and content-manifest gates.

This module reads no project ``.env`` and runs no lab script at import time.
Test collection can import it without loading credentials.
Artifact digests come from checked-in bytes, independently of the pack manifest.
See ``docs/testing/lab-fixture-pack.md`` for maintenance instructions.

The filename lacks a ``test_`` prefix, so pytest does not collect it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from aptl.core.scenario_bundle import ScenarioBundle, env_pack_bundle

FIXTURE_PACK_IDENTITY = "materialization-envelope"
FIXTURE_PACK_SOURCE = (
    Path(__file__).resolve().parent / "fixtures" / "packs" / FIXTURE_PACK_IDENTITY
)
FIXTURE_SDL = FIXTURE_PACK_SOURCE / "sdl" / f"{FIXTURE_PACK_IDENTITY}.sdl.yaml"


@dataclass(frozen=True)
class FixtureArtifact:
    """One pack artifact, as a content placement names it."""

    artifact_id: str
    digest: str
    media_type: str


def _artifact(artifact_id: str, relpath: str, media_type: str) -> FixtureArtifact:
    data = (FIXTURE_PACK_SOURCE / relpath).read_bytes()
    return FixtureArtifact(
        artifact_id=artifact_id,
        digest="sha256:" + hashlib.sha256(data).hexdigest(),
        media_type=media_type,
    )


NOTICE = _artifact(
    "materialization-envelope-notice", "assets/content/notice.txt", "text/plain"
)
TREE = _artifact(
    "materialization-envelope-tree", "assets/content/tree.tar", "application/x-tar"
)


def admit_fixture_pack(staging_root: Path) -> ScenarioBundle:
    """Stage and validate the fixture pack under ``staging_root``."""

    return env_pack_bundle(
        staging_root, FIXTURE_PACK_IDENTITY, source_pack=FIXTURE_PACK_SOURCE
    )


__all__ = [
    "FIXTURE_PACK_IDENTITY",
    "FIXTURE_PACK_SOURCE",
    "FIXTURE_SDL",
    "FixtureArtifact",
    "NOTICE",
    "TREE",
    "admit_fixture_pack",
]
