"""Bounded invocation of one already-selected scenario startup provider."""

from __future__ import annotations

from collections.abc import Sequence, Mapping
from subprocess import CompletedProcess, TimeoutExpired
from typing import TYPE_CHECKING, Protocol

from aptl.core.scenario_bundle import PackIdentity
from aptl.utils.logging import get_logger
from aptl.core.lab_types import LabResult
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.evidence.adapters.sources import capture_read_timeout

log = get_logger("scenario-runtime-hooks")

if TYPE_CHECKING:
    from aptl.backends.scenario_family import AdmittedFamilyTrial


def _raise_partial_read(exc: Exception, timeout: int) -> None:
    """Preserve accepted output while translating a bounded native read failure."""
    output = getattr(exc, "stdout", None)
    stderr = getattr(exc, "stderr", None)
    if isinstance(exc, TimeoutExpired):
        raise TimeoutExpired(
            "runtime-operation", timeout, output=output, stderr=stderr
        ) from None
    interrupted = InterruptedError("runtime-operation-interrupted")
    interrupted.stdout, interrupted.stderr = output, stderr
    raise interrupted from None


def _command_timeout_matches(cause: BaseException | None, cmd: list[str]) -> bool:
    """Accept partial command output only for this exact native command."""
    return (
        isinstance(cause, TimeoutExpired)
        and isinstance(cause.cmd, list)
        and cause.cmd[-len(cmd) :] == cmd
    )


def _valid_command(cmd: list[str]) -> bool:
    """Check the argument count and each bounded command argument."""

    return (
        isinstance(cmd, list)
        and 1 <= len(cmd) <= 64
        and all(
            isinstance(item, str)
            and bool(item)
            and len(item) <= 4096
            and "\0" not in item
            for item in cmd
        )
    )


def _validate_log_timestamp(value: str | None) -> None:
    """Require a bounded timestamp with an explicit time zone when selected."""
    from datetime import datetime

    if value is None:
        return
    try:
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError("timestamp is invalid")
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("timestamp has no time zone")
    except ValueError:
        raise ValueError("runtime-operation-invalid") from None


#: Admitted-operation refusals. Core raises them before it calls the backend,
#: so the operation never started.
RUNTIME_OPERATION_REFUSALS = frozenset(
    {"runtime-node-not-admitted", "runtime-operation-invalid"}
)

_MAX_NETWORKS = 16
_MAX_ALIASES = 32
_MAX_NAME_LENGTH = 253


def _bounded_name(value: object) -> bool:
    """Accept one bounded, printable network or alias name."""

    return (
        isinstance(value, str)
        and 0 < len(value) <= _MAX_NAME_LENGTH
        and value.isprintable()
    )


def _attachment(raw: object) -> dict[str, object]:
    """Keep only a valid IP address and bounded aliases of one attachment."""

    from ipaddress import ip_address

    projected: dict[str, object] = {}
    if not isinstance(raw, Mapping):
        return projected
    address = raw.get("IPAddress")
    try:
        if isinstance(address, str) and address:
            projected["IPAddress"] = str(ip_address(address))
    except ValueError:
        pass
    aliases = raw.get("Aliases")
    if isinstance(aliases, list):
        kept = [alias for alias in aliases if _bounded_name(alias)]
        if kept:
            projected["Aliases"] = kept[:_MAX_ALIASES]
    return projected


def _network_attachments(settings: object) -> dict[str, dict[str, object]] | None:
    """Project network attachments without endpoint, driver, or host fields.

    The projection is whole or absent. When a network name cannot be shown or
    the count exceeds the bound, it withholds every attachment, so a consumer
    cannot read a partial set as the complete set.
    """

    networks = settings.get("Networks") if isinstance(settings, Mapping) else None
    if (
        not isinstance(networks, Mapping)
        or len(networks) > _MAX_NETWORKS
        or not all(_bounded_name(name) for name in networks)
    ):
        return None
    return {name: _attachment(raw) for name, raw in networks.items()}


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
    def container_logs_capture(
        self,
        name: str,
        *,
        since: str | None = None,
        until: str | None = None,
        timeout: int = 30,
        max_bytes: int | None = None,
    ) -> CompletedProcess[str]: ...
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
            return self.__backend.container_exec(
                name, list(cmd), timeout=capture_read_timeout(timeout)
            )
        except BackendTimeoutError as exc:
            cause = exc.__cause__
            if _command_timeout_matches(cause, cmd):
                _raise_partial_read(cause, timeout)
            raise TimeoutExpired("runtime-operation", timeout) from None
        except (TimeoutExpired, InterruptedError) as exc:
            _raise_partial_read(exc, timeout)
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
                name, list(cmd), payload, timeout=capture_read_timeout(timeout)
            )
        except Exception:
            raise ValueError("runtime-operation-failed") from None

    def container_image_digest(self, name: str) -> str | None:
        self._validate(name, ["inspect"], 30)
        try:
            return self.__backend.container_image_digest(name)
        except Exception:
            raise ValueError("runtime-operation-failed") from None

    def container_logs_capture(
        self,
        name: str,
        *,
        since: str | None = None,
        until: str | None = None,
        timeout: int = 30,
        max_bytes: int | None = None,
    ) -> CompletedProcess[str]:
        """Read the existing log interface for an admitted scenario container."""
        self._validate(name, ["logs"], timeout)
        for value in (since, until):
            _validate_log_timestamp(value)
        try:
            return self.__backend.container_logs_capture(
                name,
                since=since,
                until=until,
                timeout=capture_read_timeout(timeout),
                **({"max_bytes": max_bytes} if max_bytes is not None else {}),
            )
        except (TimeoutExpired, InterruptedError) as exc:
            _raise_partial_read(exc, timeout)
        except Exception:
            raise ValueError("runtime-operation-failed") from None

    def container_inspect(self, name: str) -> Mapping[str, object]:
        """Expose bounded state and network attachments, without host configuration.

        Each attachment keeps only a valid IP address and bounded aliases. An
        ambiguous attachment set stays visible so the caller can refuse it.
        """

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
            networks = _network_attachments(info.get("NetworkSettings"))
            if networks is not None:
                result["NetworkSettings"] = {"Networks": networks}
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
