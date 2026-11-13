"""Adapter-neutral escape-probe protocol.

A probe payload prints ``LILRAE-PROBE reached <id>`` before it attempts its
denied operation and ``LILRAE-PROBE result <id> <denied|allowed> <detail>``
after it. A harness can supply the result from an independent observation.
"""

from dataclasses import dataclass
from enum import StrEnum

from aptl.core.containment.request import RequiredProperty

PROBE_MARKER = "LILRAE-PROBE"


class ProbeResult(StrEnum):
    """The observed outcome of the attempted operation."""

    DENIED = "denied"
    ALLOWED = "allowed"


class ProbeVerdict(StrEnum):
    """The verdict for one probe; only ``contained`` passes."""

    CONTAINED = "contained"
    ESCAPED = "escaped"
    NOT_REACHED = "not_reached"
    INCONCLUSIVE = "inconclusive"
    CONTROL_FAILED = "control_failed"


@dataclass(frozen=True)
class EscapeProbe:
    """One denied operation that tests one required property."""

    probe_id: str
    protected_property: RequiredProperty
    operation: str


@dataclass(frozen=True)
class ProbeObservation:
    """Whether the payload reached the operation, and the observed result."""

    reached: bool
    result: ProbeResult | None


def parse_probe_output(stdout: bytes, probe_id: str) -> ProbeObservation:
    """Read the markers of ``probe_id`` from payload output."""
    reached = False
    results: set[ProbeResult] = set()
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[0] != PROBE_MARKER or fields[2] != probe_id:
            continue
        if fields[1] == "reached":
            reached = True
        elif fields[1] == "result" and len(fields) >= 4:
            results.add(ProbeResult(fields[3]))
    if len(results) > 1:
        raise ValueError(f"probe {probe_id} printed conflicting results")
    return ProbeObservation(reached=reached, result=next(iter(results), None))


_CONTAINED_RESULTS = {ProbeResult.DENIED: ProbeVerdict.CONTAINED, ProbeResult.ALLOWED: ProbeVerdict.ESCAPED}


def classify_probe(
    control: ProbeObservation, contained: ProbeObservation
) -> ProbeVerdict:
    """Combine the unsandboxed control with the contained observation."""
    if not control.reached or control.result is not ProbeResult.ALLOWED:
        verdict = ProbeVerdict.CONTROL_FAILED
    elif not contained.reached:
        verdict = ProbeVerdict.NOT_REACHED
    elif contained.result is None:
        verdict = ProbeVerdict.INCONCLUSIVE
    else:
        verdict = _CONTAINED_RESULTS[contained.result]
    return verdict
