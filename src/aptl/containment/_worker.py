"""Per-run containment worker.

The adapter starts this file with ``python -I -S`` in a private directory, one
process for each run. It imports only the standard library and the pinned
engine, so engine singletons, logging and configuration stay inside one run.
It writes one JSON report on standard output; the target cannot reach that
channel. Engine diagnostics go to the run's bounded log file.
"""

import base64
import importlib
import json
import logging
import logging.handlers
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Self

WORKER_MESSAGE_SCHEMA = "lilrae.containment.worker-message/v1"
WORKER_REPORT_SCHEMA = "lilrae.containment.worker-report/v1"

_TARGET_BASE_ENVIRONMENT = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
_CONFIRMED_TIER = "mount-ns"
_LOG_BYTES = 1024 * 1024
_ENGINE_LIMIT_NAMES = {
    "cpu_seconds": "cpu_seconds",
    "max_file_mb": "max_file_mb",
    "address_space_mb": "memory_mb",
}
_HYGIENE = "descriptor_environment_hygiene"

type CompletedTarget = subprocess.CompletedProcess[bytes]


class SandboxEngine(Protocol):
    """The ``core.sandbox`` surface that the worker uses."""

    SandboxSetupError: type[BaseException]

    def check_mount_available(self) -> bool: ...
    def check_net_available(self) -> bool: ...
    def check_landlock_available(self) -> bool: ...
    def check_seccomp_available(self) -> bool: ...
    def check_pidns_supervision_available(self) -> tuple[bool | None, str]: ...
    def spawn_backend_available(self) -> bool: ...
    def run_untrusted(self, cmd: list[str], **kwargs: object) -> CompletedTarget: ...


class EngineConfig(Protocol):
    """The ``core.config.RaptorConfig`` surface that the worker uses."""

    def is_dangerous_env_name(self, name: str) -> bool: ...


def _field[T](document: Mapping[str, object], name: str, kind: type[T]) -> T:
    value = document[name]
    if not isinstance(value, kind):
        raise ValueError(f"worker message field {name} has the wrong type")
    return value


def _optional_path(value: object) -> Path | None:
    return None if value is None else Path(str(value))


@dataclass(frozen=True)
class WorkerMessage:
    """The adapter's validated request and the run's private paths."""

    engine_root: Path
    output_dir: Path
    log_path: Path
    label: str
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    stdin: bytes
    input_dir: Path | None
    deadline_seconds: float
    max_output_bytes: int
    limits: Mapping[str, int]

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> Self:
        """Read the message that the adapter wrote."""
        if document.get("schema_version") != WORKER_MESSAGE_SCHEMA:
            raise ValueError("unsupported worker message schema")
        request = _field(document, "request", dict)
        limits = _field(request, "limits", dict)
        return cls(
            engine_root=Path(_field(document, "engine_root", str)),
            output_dir=Path(_field(document, "output_dir", str)),
            log_path=Path(_field(document, "log_path", str)),
            label=_field(request, "label", str),
            argv=tuple(str(item) for item in _field(request, "argv", list)),
            environment={str(k): str(v) for k, v in _field(request, "env", dict).items()},
            stdin=base64.b64decode(_field(request, "stdin", str), validate=True),
            input_dir=_optional_path(request.get("input_dir")),
            deadline_seconds=float(limits["deadline_seconds"]),
            max_output_bytes=int(limits["max_output_bytes"]),
            limits={
                engine_name: int(limits[name])
                for name, engine_name in _ENGINE_LIMIT_NAMES.items()
                if limits.get(name) is not None
            },
        )


def _combine(*answers: bool | None) -> bool | None:
    """False when any check failed, None when any is unknown, else True."""
    if any(answer is False for answer in answers):
        return False
    return None if any(answer is None for answer in answers) else True


@dataclass(frozen=True)
class _Check:
    name: str
    basis: str
    probe: Callable[[], bool | None]


def _checks(engine: SandboxEngine, config: EngineConfig, names: tuple[str, ...]) -> tuple[_Check, ...]:
    def pidns() -> bool | None:
        return engine.check_pidns_supervision_available()[0]

    return (
        _Check(
            "namespaces",
            "engine mount, network and PID-namespace supervision probes",
            lambda: _combine(engine.check_mount_available(), engine.check_net_available(), pidns()),
        ),
        _Check("filesystem_policy", "engine Landlock probe", lambda: _combine(engine.check_landlock_available())),
        _Check("syscall_socket_filter", "engine seccomp probe", lambda: _combine(engine.check_seccomp_available())),
        _Check(
            _HYGIENE,
            "explicit target environment; engine descriptor closure",
            lambda: not any(config.is_dangerous_env_name(name) for name in names),
        ),
        _Check(
            "supervision",
            "engine spawn-backend and PID-namespace supervision probes",
            lambda: _combine(engine.spawn_backend_available(), pidns()),
        ),
    )


def _observe(check: _Check) -> dict[str, str]:
    try:
        answer = check.probe()
    except Exception:  # noqa: BLE001 - a broken probe is an unknown property
        answer = None
    state = {True: "delivered", False: "refused"}.get(answer, "unknown")
    return {"property": check.name, "state": state, "basis": check.basis}


def _target(returncode: int | None, stdout: bytes, stderr: bytes, limit: int) -> dict[str, object]:
    kept_stdout = stdout[:limit]
    kept_stderr = stderr[: limit - len(kept_stdout)]
    signal = -returncode if returncode is not None and returncode < 0 else None
    return {
        "exit_code": returncode if signal is None else None,
        "signal": signal,
        "stdout": base64.b64encode(kept_stdout).decode("ascii"),
        "stderr": base64.b64encode(kept_stderr).decode("ascii"),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "truncated": len(kept_stdout) + len(kept_stderr) < len(stdout) + len(stderr),
    }


def _report(
    status: str,
    origin: str,
    observations: list[dict[str, str]],
    *,
    reason: str | None = None,
    detail: str | None = None,
    target: dict[str, object] | None = None,
    tier: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": WORKER_REPORT_SCHEMA,
        "status": status,
        "failure_origin": origin,
        "reason": reason,
        "detail": detail,
        "properties": observations,
        "target": target,
        "containment_tier": tier,
    }


def _confirmed(info: Mapping[str, object]) -> bool:
    """Whether the engine's posture record shows the full profile."""
    return (
        info.get("containment_tier") == _CONFIRMED_TIER
        and info.get("mount_ns_active") is True
        and info.get("restrict_reads") is True
    )


def _unconfirmed(observations: list[dict[str, str]]) -> None:
    """Mark the engine-enforced properties unknown without a posture record."""
    for item in observations:
        if item["property"] != _HYGIENE:
            item["state"] = "unknown"


def _finish(message: WorkerMessage, result: CompletedTarget, observations: list[dict[str, str]]) -> dict[str, object]:
    info = getattr(result, "sandbox_info", None)
    posture = info if isinstance(info, dict) else {}
    tier = posture.get("containment_tier")
    reason = None
    if not _confirmed(posture):
        reason = "containment_unconfirmed"
        _unconfirmed(observations)
    target = _target(result.returncode, result.stdout or b"", result.stderr or b"", message.max_output_bytes)
    if target["truncated"]:
        status, origin, reason = "output_limit_exceeded", "target", "output_limit_exceeded"
    else:
        status, origin = "completed", "none" if result.returncode == 0 else "target"
    return _report(
        status, origin, observations, reason=reason, target=target,
        tier=str(tier)[:32] if tier is not None else None,
    )


def _refusal(observations: list[dict[str, str]]) -> dict[str, object]:
    hygiene = next(item for item in observations if item["property"] == _HYGIENE)
    if hygiene["state"] == "refused":
        return _report(
            "refused", "setup", observations, reason="environment_name_denied",
            detail="an environment name is on the engine's dangerous list",
        )
    failed = ", ".join(item["property"] for item in observations if item["state"] != "delivered")
    return _report(
        "refused", "setup", observations, reason="property_unavailable",
        detail=f"not delivered: {failed}",
    )


def execute(message: WorkerMessage, engine: SandboxEngine, config: EngineConfig) -> dict[str, object]:
    """Check every property, then run the target only when all are delivered."""
    observations = [_observe(check) for check in _checks(engine, config, tuple(message.environment))]
    if any(item["state"] != "delivered" for item in observations):
        return _refusal(observations)
    try:
        result = engine.run_untrusted(
            list(message.argv),
            target=str(message.input_dir) if message.input_dir is not None else None,
            output=str(message.output_dir),
            limits=dict(message.limits),
            profile="strict",
            env={**_TARGET_BASE_ENVIRONMENT, **message.environment},
            timeout=message.deadline_seconds,
            input=message.stdin,
            capture_output=True,
            caller_label=message.label,
        )
    except engine.SandboxSetupError as exc:
        category = getattr(exc, "setup_category", None) or "unspecified"
        return _report(
            "refused", "setup", observations, reason="engine_setup_failed",
            detail=f"engine setup category {str(category)[:16]}",
        )
    except subprocess.TimeoutExpired as exc:
        # A timeout carries no posture record, so containment is unconfirmed.
        _unconfirmed(observations)
        target = _target(None, exc.stdout or b"", exc.stderr or b"", message.max_output_bytes)
        return _report(
            "timed_out", "target", observations, reason="deadline_exceeded",
            detail="the engine posture record is absent after the deadline", target=target,
        )
    return _finish(message, result, observations)


def _configure_logging(path: Path) -> None:
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=_LOG_BYTES, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def _load_engine(root: Path) -> tuple[SandboxEngine, EngineConfig]:
    """Import the verified snapshot; the standard library keeps precedence."""
    sys.dont_write_bytecode = True
    sys.path.append(str(root))
    engine = importlib.import_module("core.sandbox")
    config = importlib.import_module("core.config").RaptorConfig
    return engine, config


def main(payload: bytes) -> int:
    """Run one message and print its report."""
    message = WorkerMessage.from_document(json.loads(payload))
    # Files that the worker and the engine create stay private to the owner.
    os.umask(0o077)
    _configure_logging(message.log_path)
    engine, config = _load_engine(message.engine_root)
    sys.stdout.write(json.dumps(execute(message, engine, config)))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.buffer.read()))
