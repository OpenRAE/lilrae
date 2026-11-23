"""Adapter-neutral escape-probe markers and verdicts."""

import pytest

from aptl.core.containment import (
    ProbeObservation,
    ProbeResult,
    ProbeVerdict,
    classify_probe,
    parse_probe_output,
)

ALLOWED = ProbeObservation(reached=True, result=ProbeResult.ALLOWED)
DENIED = ProbeObservation(reached=True, result=ProbeResult.DENIED)
REACHED_ONLY = ProbeObservation(reached=True, result=None)
ABSENT = ProbeObservation(reached=False, result=None)


def test_parse_reads_only_the_named_probe() -> None:
    stdout = (
        b"noise\n"
        b"LILRAE-PROBE reached other\n"
        b"LILRAE-PROBE result other allowed ok\n"
        b"LILRAE-PROBE reached host-file-read\n"
        b"LILRAE-PROBE result host-file-read denied ENOENT\n"
    )

    assert parse_probe_output(stdout, "host-file-read") == DENIED
    assert parse_probe_output(stdout, "missing") == ABSENT


def test_parse_ignores_a_result_without_a_reached_marker() -> None:
    stdout = b"LILRAE-PROBE result host-file-read denied EPERM\n"

    assert parse_probe_output(stdout, "host-file-read") == ProbeObservation(
        reached=False, result=ProbeResult.DENIED
    )


def test_parse_refuses_conflicting_results() -> None:
    stdout = (
        b"LILRAE-PROBE reached p\n"
        b"LILRAE-PROBE result p denied EPERM\n"
        b"LILRAE-PROBE result p allowed ok\n"
    )

    with pytest.raises(ValueError, match="conflicting"):
        parse_probe_output(stdout, "p")


@pytest.mark.parametrize(
    ("control", "contained", "verdict"),
    [
        (ALLOWED, DENIED, ProbeVerdict.CONTAINED),
        (ALLOWED, ALLOWED, ProbeVerdict.ESCAPED),
        (ALLOWED, ABSENT, ProbeVerdict.NOT_REACHED),
        (ALLOWED, REACHED_ONLY, ProbeVerdict.INCONCLUSIVE),
        (DENIED, DENIED, ProbeVerdict.CONTROL_FAILED),
        (ABSENT, DENIED, ProbeVerdict.CONTROL_FAILED),
        (REACHED_ONLY, DENIED, ProbeVerdict.CONTROL_FAILED),
    ],
)
def test_classify_requires_a_working_control_and_a_reached_denial(
    control: ProbeObservation, contained: ProbeObservation, verdict: ProbeVerdict
) -> None:
    assert classify_probe(control, contained) is verdict
