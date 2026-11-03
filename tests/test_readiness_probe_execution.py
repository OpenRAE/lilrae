"""The canonical process runner bounds native readiness before buffering."""

import sys

import pytest

from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.utils.curl_safe import curl_json
from aptl.utils.probe_execution import bounded_probe_commands, run_bounded_probe_command
from aptl.workbench.process import BoundedProcessRunner, ProcessCleanup, ProcessResult


@pytest.mark.parametrize(
    "program,timeout",
    [
        ("print('password=private-test-value' * 10000)", 30),
        ("import time; time.sleep(2)", 0.02),
    ],
)
def test_process_output_and_time_are_bounded_without_rendering_output(
    tmp_path, program, timeout
):
    with bounded_probe_commands(BoundedProcessRunner(), 1024):
        with pytest.raises(
            RuntimeError, match="^bounded-probe-command-failed$"
        ) as failure:
            run_bounded_probe_command(
                [sys.executable, "-c", program], cwd=tmp_path, timeout=timeout
            )
    assert "private-test-value" not in str(failure.value)
    assert run_bounded_probe_command(["unused"], cwd=tmp_path, timeout=1) is None


class Runner:
    def __init__(self, output=b"safe", residual=()):
        self.output, self.residual, self.calls = output, residual, []

    def run(self, argv, **options):
        self.calls.append((argv, options["cwd"], options["max_output_bytes"]))
        return ProcessResult(0, self.output, b"", ProcessCleanup(1, 0, self.residual))


def test_docker_and_http_owners_use_the_scoped_runner(tmp_path):
    backend = DockerComposeBackend(tmp_path)
    runner = Runner()
    with bounded_probe_commands(runner, 4096):
        assert backend._run(["docker", "info"], timeout=15).stdout == "safe"
    assert runner.calls[0] == (("docker", "info"), tmp_path, 4096)
    runner = Runner(b'{"ready":true}')
    with bounded_probe_commands(runner, 4096):
        assert curl_json(
            "https://approved.invalid", auth_header="synthetic-private-value"
        ) == {"ready": True}
    assert "synthetic-private-value" not in repr(runner.calls)
    assert runner.calls[0][2] == 4096


def test_unknown_process_cessation_is_not_a_completed_probe(tmp_path):
    runner = Runner(residual=("process-group-cleanup-unconfirmed",))
    with bounded_probe_commands(runner, 4096) as scope:
        with pytest.raises(RuntimeError, match="^bounded-probe-cessation-unverified$"):
            run_bounded_probe_command(["approved-probe"], cwd=tmp_path, timeout=30)
        assert not scope.cessation_confirmed


@pytest.mark.parametrize("split_files", [False, True])
def test_archive_readiness_bounds_acquisition_across_files(
    tmp_path, mocker, split_files
):
    from pathlib import Path

    from aptl.core.correlation.clock import FixedClockProvider
    from aptl.core.evidence.adapters.builtins import RunArchiveSource
    from aptl.core.evidence.adapters.sources import WindowedQueryCollector
    from aptl.core.runstore import LocalRunStore

    store = LocalRunStore(tmp_path / "runs")
    payload = b'{"event":"' + b"x" * 700 + b'"}\n'
    if split_files:
        store.write_file("run", "source/a.jsonl", payload)
        store.write_file("run", "source/b.jsonl", payload)
    else:
        store.write_file("run", "source/a.jsonl", payload * 10000)
    from aptl.core.evidence.adapters import builtins

    original_open = builtins.open_contained_nofollow
    acquired = 0
    sizes = []

    def tracked_open(*args):
        source = original_open(*args)
        original_read = source.read1

        def bounded_read(size):
            nonlocal acquired
            sizes.append(size)
            result = original_read(size)
            acquired += len(result)
            return result

        mocker.patch.object(source, "read1", side_effect=bounded_read)
        return source

    mocker.patch.object(builtins, "open_contained_nofollow", side_effect=tracked_open)
    whole_file_read = mocker.spy(Path, "read_text")
    collector = WindowedQueryCollector(
        "archive", RunArchiveSource(store, "run", "source")
    )
    with bounded_probe_commands(Runner(), 1024):
        assert not collector.check_readiness(
            FixedClockProvider(measurement_time="2026-11-03T04:00:00Z")
        )
    whole_file_read.assert_not_called()
    assert sizes and all(0 < size <= 1025 for size in sizes)
    assert acquired == 1025


def test_readiness_never_calls_acquisition_or_its_stimuli():
    from aptl.core.correlation.clock import FixedClockProvider
    from aptl.core.evidence.adapters.sources import (
        CallableWindowedSource,
        WindowedQueryCollector,
    )

    events = []

    def acquire(start, end):
        events.append("stimulus")
        raise AssertionError("acquisition must stay in the capture lifecycle")

    clock = FixedClockProvider(measurement_time="2026-11-03T04:00:00Z")
    with bounded_probe_commands(Runner(), 1024):
        assert not WindowedQueryCollector(
            "source", CallableWindowedSource(acquire)
        ).check_readiness(clock)
        owner = CallableWindowedSource(
            acquire, readiness=lambda at: events.append("read-only") or True
        )
        assert WindowedQueryCollector("source", owner).check_readiness(clock)
    assert events == ["read-only"]


def test_stimulating_native_source_is_refused_without_read_only_readiness():
    from aptl.core.correlation.clock import FixedClockProvider
    from aptl.core.evidence.adapters.sources import WindowedQueryCollector
    from aptl_techvault.evidence.techvault import SuricataWazuhSqliSource

    def forbidden(*args):
        pytest.fail("readiness invoked the target stimulus or acquisition query")

    source = SuricataWazuhSqliSource(forbidden, forbidden, forbidden)
    with bounded_probe_commands(Runner(), 1024):
        assert not WindowedQueryCollector("native", source).check_readiness(
            FixedClockProvider(measurement_time="2026-11-03T04:00:00Z")
        )
