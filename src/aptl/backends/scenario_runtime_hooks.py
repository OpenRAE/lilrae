"""Bounded invocation of one already-selected scenario startup provider."""

from __future__ import annotations

from collections.abc import Sequence, Mapping
from subprocess import CompletedProcess
from typing import TYPE_CHECKING, Protocol

from aptl.core.scenario_bundle import PackIdentity
from aptl.utils.logging import get_logger
from aptl.core.lab_types import LabResult

log = get_logger("scenario-runtime-hooks")

if TYPE_CHECKING:
    from aptl.backends.scenario_family import AdmittedFamilyTrial


def _valid_command(cmd: list[str]) -> bool:
    """Check the argument count and each bounded command argument."""

    return (
        isinstance(cmd, list)
        and 1 <= len(cmd) <= 64
        and all(
            isinstance(item, str) and bool(item) and len(item) <= 4096 and "\0" not in item
            for item in cmd
        )
    )


class ScenarioRuntimeOperations(Protocol):
    """Container-only operations delegated for admitted scenario nodes."""

    def container_exec(
        self, name: str, cmd: list[str], *, timeout: int
    ) -> CompletedProcess[str]: ...
    def container_exec_with_input(
        self, name: str, cmd: list[str], payload: str, *, timeout: int
    ) -> CompletedProcess[str]: ...
    def container_image_digest(self, name: str) -> str | None: ...
    def container_inspect(self, name: str) -> Mapping[str, object]: ...
    def container_restart(self, name: str) -> LabResult: ...


class AdmittedRuntimeOperations:
    """Delegate container operations without exposing the deployment backend."""

    def __init__(self, backend: object, nodes: Sequence[object]) -> None:
        self.__backend = backend
        self.__names = frozenset(
            name
            for node in nodes
            for name in (
                getattr(node, "name", None),
                getattr(node, "container_name", None),
                *getattr(node, "aliases", ()),
            )
            if isinstance(name, str) and name
        )

    def _validate(self, name: str, cmd: list[str], timeout: int) -> None:
        if not isinstance(name, str) or name not in self.__names:
            raise ValueError("runtime-node-not-admitted")
        if (
            not _valid_command(cmd)
            or isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or not 1 <= timeout <= 300
        ):
            raise ValueError("runtime-operation-invalid")

    def container_exec(
        self, name: str, cmd: list[str], *, timeout: int = 30
    ) -> CompletedProcess[str]:
        self._validate(name, cmd, timeout)
        try:
            return self.__backend.container_exec(name, list(cmd), timeout=timeout)
        except Exception:
            raise ValueError("runtime-operation-failed") from None

    def container_exec_with_input(
        self, name: str, cmd: list[str], payload: str, *, timeout: int = 30
    ) -> CompletedProcess[str]:
        self._validate(name, cmd, timeout)
        if not isinstance(payload, str) or len(payload.encode()) > 2 * 1024 * 1024:
            raise ValueError("runtime-operation-invalid")
        try:
            return self.__backend.container_exec_with_input(
                name, list(cmd), payload, timeout=timeout
            )
        except Exception:
            raise ValueError("runtime-operation-failed") from None

    def container_image_digest(self, name: str) -> str | None:
        self._validate(name, ["inspect"], 30)
        try:
            return self.__backend.container_image_digest(name)
        except Exception:
            raise ValueError("runtime-operation-failed") from None

    def container_inspect(self, name: str) -> Mapping[str, object]:
        """Expose bounded process state without environment or host configuration."""

        self._validate(name, ["inspect"], 30)
        try:
            info = self.__backend.container_inspect(name)
            raw_state = info.get("State") or {}
            state = {}
            status = raw_state.get("Status")
            if status in {
                "created",
                "running",
                "paused",
                "restarting",
                "removing",
                "exited",
                "dead",
            }:
                state["Status"] = status
            for key in ("Running", "Paused", "Restarting", "OOMKilled", "Dead"):
                value = raw_state.get(key)
                if isinstance(value, bool):
                    state[key] = value
            result = {"State": state}
            for owner, key, destination in (
                (raw_state, "ExitCode", state),
                (info, "RestartCount", result),
            ):
                value = owner.get(key)
                if (
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and -255 <= value <= 1_000_000_000
                ):
                    destination[key] = value
            return result
        except Exception:
            raise ValueError("runtime-operation-failed") from None

    def container_restart(self, name: str) -> LabResult:
        self._validate(name, ["restart"], 30)
        try:
            return self.__backend.container_restart(name)
        except Exception:
            raise ValueError("runtime-operation-failed") from None


def disclose_runtime_concern(
    concern_kind: str, observed_value: object
) -> object | None:
    """Project a native observation through the owner's secret-safe validator."""

    from aptl.backends._runtime_concern_disclosure import _disclose

    return _disclose(concern_kind, observed_value)


def _runtime_failures(failures: object, *, family: bool) -> list[str]:
    """Validate adapter failures and bound family diagnostics to a stable code."""

    if not isinstance(failures, list) or any(
        not isinstance(item, str) or not item for item in failures
    ):
        return ["scenario runtime provider returned an invalid result"]
    return ["family-runtime-failed"] if family and failures else failures


def invoke_runtime_provider(
    provider: object,
    identity: PackIdentity | None,
    backend: object,
    nodes: tuple[object, ...],
    *,
    trial: AdmittedFamilyTrial | None = None,
) -> list[str]:
    """Invoke post-start work and normalize its bounded failure list."""

    runner = getattr(provider, "realize_runtime", None)
    if runner is None:
        return []
    if not callable(runner):
        return ["scenario runtime provider is malformed"]
    try:
        if trial is not None:
            from copy import deepcopy

            failures = runner(
                AdmittedRuntimeOperations(backend, nodes),
                deepcopy(nodes),
                trial=trial,
            )
        else:
            failures = runner(backend, nodes)
    except Exception as exc:
        log.warning(
            "scenario runtime provider failed: selector=%s exception=%s",
            getattr(identity, "pack_id", ""),
            type(exc).__name__,
        )
        result = ["scenario runtime provider failed"]
    else:
        result = _runtime_failures(failures, family=trial is not None)
    return result


def invoke_runtime_observer(
    provider: object | None,
    identity: PackIdentity | None,
    backend: object,
    node: object,
    *,
    trial: AdmittedFamilyTrial | None = None,
) -> object | None:
    """Read one qualified adapter result, leaving projection to the caller."""

    try:
        observer = getattr(provider, "observe_runtime", None) if provider else None
        if observer is None:
            return None
        if not callable(observer):
            raise TypeError("scenario runtime observer is malformed")
        if trial is not None:
            from copy import deepcopy

            result = observer(
                AdmittedRuntimeOperations(backend, (node,)), deepcopy(node), trial=trial
            )
        else:
            result = observer(backend, node)
    except Exception as exc:
        log.warning(
            "scenario runtime observation failed: selector=%s exception=%s",
            getattr(identity, "pack_id", ""),
            type(exc).__name__,
        )
        result = None
    return result
