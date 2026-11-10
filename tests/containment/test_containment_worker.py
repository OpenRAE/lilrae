"""Per-run worker logic against a fake engine; real enforcement runs in CI."""

import base64
import itertools
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from aptl.containment import _worker as worker
from aptl.core.containment import RequiredProperty

ALL_PROPERTIES = tuple(item.value for item in RequiredProperty)


class FakeSetupError(BaseException):
    def __init__(self, category: str) -> None:
        super().__init__(f"setup failed: /secret/path {category}")
        self.setup_category = category


@dataclass
class FakeEngine:
    """The engine surface the worker uses; each probe can fail or raise."""

    mount: object = True
    net: object = True
    landlock: object = True
    seccomp: object = True
    pidns: object = True
    spawn: object = True
    result: object = None
    raises: BaseException | None = None
    calls: list[dict[str, object]] = field(default_factory=list)
    SandboxSetupError: type[BaseException] = FakeSetupError

    @staticmethod
    def _answer(value: object) -> bool:
        if isinstance(value, BaseException):
            raise value
        return bool(value)

    def check_mount_available(self) -> bool:
        return self._answer(self.mount)

    def check_net_available(self) -> bool:
        return self._answer(self.net)

    def check_landlock_available(self) -> bool:
        return self._answer(self.landlock)

    def check_seccomp_available(self) -> bool:
        return self._answer(self.seccomp)

    def check_pidns_supervision_available(self) -> tuple[bool | None, str]:
        if isinstance(self.pidns, BaseException):
            raise self.pidns
        return (self.pidns if self.pidns is None else bool(self.pidns), "probe detail")

    def spawn_backend_available(self) -> bool:
        return self._answer(self.spawn)

    def run_untrusted(self, cmd: list[str], **kwargs: object) -> object:
        self.calls.append({"cmd": cmd, **kwargs})
        if self.raises is not None:
            raise self.raises
        return self.result


class FakeConfig:
    @staticmethod
    def is_dangerous_env_name(name: str) -> bool:
        return name.startswith("LD_")


def _completed(
    returncode: int = 0,
    stdout: bytes = b"out",
    stderr: bytes = b"err",
    sandbox_info: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.CompletedProcess(["/bin/true"], returncode, stdout, stderr)
    result.sandbox_info = (  # type: ignore[attr-defined]
        {"containment_tier": "mount-ns", "mount_ns_active": True, "restrict_reads": True}
        if sandbox_info is None
        else sandbox_info
    )
    return result


def _message(tmp_path: Path, **request_overrides: object) -> worker.WorkerMessage:
    request: dict[str, object] = {
        "label": "fixture",
        "argv": ["/usr/bin/python3", "-c", "print(1)"],
        "env": {"FIXTURE_MODE": "proof"},
        "stdin": base64.b64encode(b"payload").decode(),
        "input_dir": str(tmp_path / "input"),
        "limits": {
            "deadline_seconds": 5,
            "max_output_bytes": 64,
            "cpu_seconds": 30,
            "max_file_mb": None,
            "address_space_mb": None,
        },
    }
    request.update(request_overrides)
    return worker.WorkerMessage.from_document(
        {
            "schema_version": worker.WORKER_MESSAGE_SCHEMA,
            "engine_root": str(tmp_path / "engine"),
            "output_dir": str(tmp_path / "output"),
            "log_path": str(tmp_path / "engine.log"),
            "request": request,
        }
    )


def _states(report: dict[str, object]) -> dict[str, str]:
    properties = report["properties"]
    assert isinstance(properties, list)
    return {item["property"]: item["state"] for item in properties}


def test_all_properties_delivered_runs_the_strict_untrusted_contract(tmp_path: Path) -> None:
    engine = FakeEngine(result=_completed())

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    assert report["status"] == "completed"
    assert report["failure_origin"] == "none"
    assert set(_states(report).values()) == {"delivered"}
    assert report["containment_tier"] == "mount-ns"
    (call,) = engine.calls
    assert call["cmd"] == ["/usr/bin/python3", "-c", "print(1)"]
    assert call["profile"] == "strict"
    assert call["input"] == b"payload"
    assert call["timeout"] == 5
    assert call["target"] == str(tmp_path / "input")
    assert call["output"] == str(tmp_path / "output")
    assert call["env"] == {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "FIXTURE_MODE": "proof"}
    assert call["limits"] == {"cpu_seconds": 30}
    target = report["target"]
    assert isinstance(target, dict)
    assert base64.b64decode(target["stdout"]) == b"out"
    assert target["exit_code"] == 0


PROBE_FIELDS = ("mount", "net", "landlock", "seccomp", "pidns", "spawn")


def _failing_combinations() -> Iterable[tuple[str, ...]]:
    for size in (1, 2, len(PROBE_FIELDS)):
        yield from itertools.combinations(PROBE_FIELDS, size)


@pytest.mark.parametrize("failing", list(_failing_combinations()))
@pytest.mark.parametrize("failure", [False, None, RuntimeError("probe broke")])
def test_any_failed_or_unknown_property_refuses_before_the_payload(
    tmp_path: Path, failing: tuple[str, ...], failure: object
) -> None:
    engine = FakeEngine(result=_completed())
    for name in failing:
        setattr(engine, name, failure)

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    assert engine.calls == []
    assert report["status"] == "refused"
    assert report["failure_origin"] == "setup"
    assert report["reason"] == "property_unavailable"
    assert report["target"] is None
    assert "delivered" not in {_states(report)[name] for name in _affected(failing)}


def _affected(failing: tuple[str, ...]) -> set[str]:
    owners = {
        "mount": {"namespaces"},
        "net": {"namespaces"},
        "landlock": {"filesystem_policy"},
        "seccomp": {"syscall_socket_filter"},
        "pidns": {"namespaces", "supervision"},
        "spawn": {"supervision"},
    }
    return set().union(*(owners[name] for name in failing))


def test_a_dangerous_environment_name_refuses_before_the_payload(tmp_path: Path) -> None:
    engine = FakeEngine(result=_completed())

    report = worker.execute(
        _message(tmp_path, env={"LD_PRELOAD": "/tmp/x.so"}), engine, FakeConfig()
    )

    assert engine.calls == []
    assert report["reason"] == "environment_name_denied"
    assert _states(report)["descriptor_environment_hygiene"] == "refused"
    assert "LD_PRELOAD" not in str(report["detail"])


def test_engine_setup_error_is_a_setup_refusal_without_engine_text(tmp_path: Path) -> None:
    engine = FakeEngine(raises=FakeSetupError("L"))

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    assert report["status"] == "refused"
    assert report["failure_origin"] == "setup"
    assert report["reason"] == "engine_setup_failed"
    assert report["detail"] == "engine setup category L"
    assert report["target"] is None


def test_target_failure_is_attributed_to_the_target(tmp_path: Path) -> None:
    engine = FakeEngine(result=_completed(returncode=126, stdout=b'{"status": "refused"}'))

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    assert report["status"] == "completed"
    assert report["failure_origin"] == "target"
    target = report["target"]
    assert isinstance(target, dict)
    assert target["exit_code"] == 126


def test_signal_exit_reports_the_signal(tmp_path: Path) -> None:
    engine = FakeEngine(result=_completed(returncode=-9))

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    target = report["target"]
    assert isinstance(target, dict)
    assert (target["exit_code"], target["signal"]) == (None, 9)
    assert report["failure_origin"] == "target"


def test_deadline_is_a_target_timeout_with_partial_output(tmp_path: Path) -> None:
    timeout = subprocess.TimeoutExpired(["/bin/sleep"], 5, output=b"partial", stderr=None)
    engine = FakeEngine(raises=timeout)

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    assert report["status"] == "timed_out"
    assert report["failure_origin"] == "target"
    assert report["reason"] == "deadline_exceeded"
    states = _states(report)
    assert states.pop("descriptor_environment_hygiene") == "delivered"
    assert set(states.values()) == {"unknown"}
    target = report["target"]
    assert isinstance(target, dict)
    assert base64.b64decode(target["stdout"]) == b"partial"


def test_aggregate_output_bound_truncates_and_flags(tmp_path: Path) -> None:
    engine = FakeEngine(result=_completed(stdout=b"o" * 50, stderr=b"e" * 50))

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    assert report["status"] == "output_limit_exceeded"
    assert report["failure_origin"] == "target"
    target = report["target"]
    assert isinstance(target, dict)
    kept = base64.b64decode(target["stdout"]) + base64.b64decode(target["stderr"])
    assert len(kept) == 64
    assert (target["stdout_bytes"], target["stderr_bytes"], target["truncated"]) == (50, 50, True)


@pytest.mark.parametrize(
    "posture",
    [
        {"containment_tier": "mountless-ns", "mount_ns_active": False, "restrict_reads": True},
        {"containment_tier": "mount-ns", "mount_ns_active": False, "restrict_reads": True},
        {"containment_tier": "mount-ns", "mount_ns_active": True, "restrict_reads": False},
        {},
    ],
)
def test_an_unconfirmed_posture_downgrades_the_properties(
    tmp_path: Path, posture: dict[str, object]
) -> None:
    engine = FakeEngine(result=_completed(sandbox_info=posture))

    report = worker.execute(_message(tmp_path), engine, FakeConfig())

    assert report["reason"] == "containment_unconfirmed"
    states = _states(report)
    assert states["namespaces"] == "unknown"
    assert states["descriptor_environment_hygiene"] == "delivered"


def test_without_input_the_engine_gets_only_the_output_grant(tmp_path: Path) -> None:
    engine = FakeEngine(result=_completed())

    worker.execute(_message(tmp_path, input_dir=None), engine, FakeConfig())

    assert engine.calls[0]["target"] is None


def test_message_refuses_an_unknown_schema(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="schema"):
        worker.WorkerMessage.from_document({"schema_version": "other"})


def test_main_writes_one_report_and_logs_to_the_run_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    message = _message(tmp_path)
    engine = FakeEngine(result=_completed())
    monkeypatch.setattr(worker, "_load_engine", lambda root: (engine, FakeConfig()))
    document = {
        "schema_version": worker.WORKER_MESSAGE_SCHEMA,
        "engine_root": str(message.engine_root),
        "output_dir": str(message.output_dir),
        "log_path": str(message.log_path),
        "request": {
            "label": "fixture",
            "argv": ["/bin/true"],
            "env": {},
            "stdin": "",
            "input_dir": None,
            "limits": {"deadline_seconds": 1, "max_output_bytes": 8},
        },
    }

    assert worker.main(worker.json.dumps(document).encode()) == 0
    printed = worker.json.loads(capsys.readouterr().out)
    assert printed["schema_version"] == worker.WORKER_REPORT_SCHEMA
    assert message.log_path.exists()


def test_load_engine_imports_the_snapshot_after_the_standard_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = tmp_path / "snapshot"
    (snapshot / "core" / "sandbox").mkdir(parents=True)
    (snapshot / "core" / "config").mkdir()
    (snapshot / "core" / "__init__.py").write_text("")
    (snapshot / "core" / "sandbox" / "__init__.py").write_text("MARK = 'snapshot'\n")
    (snapshot / "core" / "config" / "__init__.py").write_text("class RaptorConfig:\n    pass\n")
    (snapshot / "json.py").write_text("raise SystemExit('shadowed the standard library')\n")
    monkeypatch.setattr(worker.sys, "path", list(worker.sys.path))
    monkeypatch.setattr(worker.sys, "dont_write_bytecode", False)
    for name in [name for name in worker.sys.modules if name == "core" or name.startswith("core.")]:
        monkeypatch.delitem(worker.sys.modules, name)
    monkeypatch.delitem(worker.sys.modules, "json")

    engine, config = worker._load_engine(snapshot)

    assert worker.sys.path[-1] == str(snapshot)
    assert worker.sys.dont_write_bytecode is True
    assert engine.MARK == "snapshot"  # type: ignore[attr-defined]
    assert config.__name__ == "RaptorConfig"  # type: ignore[attr-defined]
    __import__("json")
    assert not list(snapshot.rglob("*.pyc"))
    for name in [name for name in worker.sys.modules if name == "core" or name.startswith("core.")]:
        del worker.sys.modules[name]
