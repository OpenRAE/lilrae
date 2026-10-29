"""The check record ``lilrae doctor`` reports, and the helpers its checks share.

:mod:`aptl.core.doctor` runs the workspace and host-tool checks, and
:mod:`aptl.core._doctor_runtime` runs the Docker engine checks (#1218). Both
build their results from this module, so the engine checks need nothing from
:mod:`aptl.core.doctor` and the two modules form no import cycle.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final

PROBE_TIMEOUT_SECONDS = 30
NO_PROJECT_DIRECTORY = "the project directory does not exist (see project-config)"
_VERSION_TEXT = re.compile(r"v?(\d+)\.(\d+)[0-9A-Za-z.+-]{0,40}")
_NODE_VERSION_TEXT = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")

# Node's supported release lines and the first releases containing the Brotli
# decoder fix for CVE-2026-111497. This allow-list deliberately rejects odd and
# retired majors rather than treating an ever-larger major as inherently safe.
SUPPORTED_NODE_RELEASES: Final = MappingProxyType(
    {
        22: (22, 23, 4),
        24: (24, 22, 1),
        26: (26, 12, 1),
    }
)

Which = Callable[[str], str | None]


class CheckStatus(str, Enum):
    """Verdict of one doctor check; the values are stable output words."""

    PASSED = "pass"
    WARNING = "warn"
    FAILED = "fail"
    SKIPPED = "skip"


@dataclass(frozen=True)
class DoctorCheck:
    """One observed prerequisite, with the fix when it is not met."""

    check_id: str
    status: CheckStatus
    summary: str
    fix: str = ""


def skipped(check_id: str, reason: str) -> DoctorCheck:
    """Return a check that could not run, and why."""

    return DoctorCheck(check_id, CheckStatus.SKIPPED, f"Not checked: {reason}.")


def version_text(raw: object) -> str | None:
    """Return a bounded version string, or ``None`` for anything else."""

    text = str(raw or "").strip()
    return text if _VERSION_TEXT.fullmatch(text) else None


def major_minor(raw: object) -> tuple[int, int] | None:
    """Parse ``major.minor`` from a version string such as ``v20.11.1``."""

    match = _VERSION_TEXT.fullmatch(str(raw or "").strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def node_version(raw: object) -> tuple[int, int, int] | None:
    """Parse one final Node release such as ``v22.23.4``.

    Partial, prerelease, and decorated versions fail closed because artifact
    admission needs to prove an exact upstream security floor.
    """

    match = _NODE_VERSION_TEXT.fullmatch(str(raw or "").strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def node_version_supported(
    raw: object, *, allowed_majors: Collection[int] | None = None
) -> bool:
    """Return whether ``raw`` is on an allowed, supported, patched Node line."""

    version = node_version(raw)
    if version is None:
        return False
    floor = SUPPORTED_NODE_RELEASES.get(version[0])
    if floor is None or (
        allowed_majors is not None and version[0] not in allowed_majors
    ):
        return False
    return version >= floor


def supported_node_releases_text() -> str:
    """Return the human-facing minimum supported Node releases."""

    floors = [
        ".".join(str(part) for part in version) + "+"
        for version in SUPPORTED_NODE_RELEASES.values()
    ]
    return ", ".join(floors[:-1]) + f", or {floors[-1]}"
