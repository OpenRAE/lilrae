"""Host checks for the Bubblewrap engine."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

import pytest

from aptl.containment import host
from aptl.containment.host import HostInspector
from aptl.core.agent_errors import AgentExecutionError


@dataclass(frozen=True)
class _Result:
    returncode: int
    stdout: bytes
    stderr: bytes = b""
    cleanup: None = None


@dataclass
class _Runner:
    version: bytes = b"bubblewrap 0.9.0\n"
    probe_code: int = 0
    fail_probe: bool = False
    calls: list[tuple[str, ...]] = field(default_factory=list)
    controls: list[tuple[float, Event | None]] = field(default_factory=list)

    def run(
        self, argv: tuple[str, ...], *, env: dict[str, str], cwd: Path, stdin: bytes,
        timeout_seconds: float, max_output_bytes: int, cancel_event: Event | None = None,
        pass_fds: tuple[int, ...] = (),
    ) -> _Result:
        self.calls.append(argv)
        self.controls.append((timeout_seconds, cancel_event))
        if argv[1] == "--version":
            return _Result(0, self.version)
        if self.fail_probe:
            raise AgentExecutionError("probe failed")
        return _Result(self.probe_code, b"")


@pytest.fixture
def bwrap(tmp_path: Path) -> Path:
    path = tmp_path / "bwrap"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_landlock_and_libseccomp_probes_answer_on_this_host() -> None:
    abi = host.landlock_abi()
    version = host.libseccomp_version()

    assert abi is None or abi >= 1
    assert version is None or len(version) == 3


def test_supported_bubblewrap_runs_the_namespace_probe(bwrap: Path, tmp_path: Path) -> None:
    runner = _Runner()

    facts = HostInspector(runner, bwrap, cwd=tmp_path).observe()

    assert facts.bubblewrap_version == "0.9.0"
    assert facts.bubblewrap_supported is True
    assert facts.namespaces is True
    assert runner.calls[1][-1] == "/usr/bin/true"
    assert facts.launcher_python == os.access("/usr/bin/python3", os.X_OK)


@pytest.mark.parametrize(("version", "supported"), [(b"bubblewrap 0.7.0\n", False), (b"garbage", False)])
def test_old_or_unreadable_bubblewrap_skips_the_probe(bwrap: Path, tmp_path: Path, version: bytes, supported: bool) -> None:
    runner = _Runner(version=version)

    facts = HostInspector(runner, bwrap, cwd=tmp_path).observe()

    assert facts.bubblewrap_supported is supported
    assert facts.namespaces is None
    assert len(runner.calls) == 1


def test_missing_bubblewrap_is_unsupported(tmp_path: Path) -> None:
    runner = _Runner()

    facts = HostInspector(runner, tmp_path / "absent", cwd=tmp_path).observe()

    assert facts.bubblewrap_version is None
    assert facts.bubblewrap_supported is False
    assert runner.calls == []


@pytest.mark.parametrize(("probe_code", "fail_probe", "expected"), [(1, False, False), (0, True, None)])
def test_namespace_probe_failure_is_refused_or_unknown(
    bwrap: Path, tmp_path: Path, probe_code: int, fail_probe: bool, expected: bool | None
) -> None:
    facts = HostInspector(_Runner(probe_code=probe_code, fail_probe=fail_probe), bwrap, cwd=tmp_path).observe()

    assert facts.namespaces is expected


def test_old_libseccomp_is_unsupported(bwrap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host, "libseccomp_version", lambda: (2, 4, 0))

    facts = HostInspector(_Runner(), bwrap, cwd=tmp_path).observe()

    assert facts.libseccomp_version == "2.4.0"
    assert facts.libseccomp_supported is False


def test_host_checks_use_the_remaining_budget_and_cancellation(bwrap: Path, tmp_path: Path) -> None:
    runner = _Runner()
    cancel = Event()
    inspector = HostInspector(runner, bwrap, cwd=tmp_path, clock=lambda: 100.0)

    inspector.observe(deadline=102.0, cancel_event=cancel)

    assert runner.controls == [(2.0, cancel), (2.0, cancel)]


def test_host_checks_skip_probes_without_budget(bwrap: Path, tmp_path: Path) -> None:
    runner = _Runner()

    facts = HostInspector(runner, bwrap, cwd=tmp_path, clock=lambda: 100.0).observe(deadline=100.0)

    assert runner.calls == []
    assert facts.bubblewrap_version is None and facts.namespaces is None
