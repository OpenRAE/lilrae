"""Turn host facts and run evidence into property states and a run outcome."""

from dataclasses import dataclass
from threading import Event

from aptl.containment.bubblewrap import REQUIRED_NAMESPACES, BubblewrapStatus
from aptl.containment.host import HostFacts
from aptl.containment.launch_status import LaunchStatus
from aptl.core.agent_errors import BoundedStopReason
from aptl.core.containment import (
    CleanupObservation,
    FailureOrigin,
    PropertyObservation,
    PropertyState,
    ReasonCode,
    RequiredProperty,
    RunStatus,
    TargetOutcome,
    WorkerCleanup,
    WorkerResult,
    WorkerRunnerFailure,
)

_STDERR_LINE = 200


@dataclass(frozen=True)
class Evidence:
    """What one run observed: both status channels and the runner's answer."""

    launch: LaunchStatus
    bubblewrap: BubblewrapStatus
    result: WorkerResult | None
    failure: WorkerRunnerFailure | None
    error: BaseException | None


@dataclass(frozen=True)
class Outcome:
    """The report facts that depend on the run."""

    status: RunStatus
    origin: FailureOrigin
    properties: tuple[PropertyObservation, ...]
    reason: ReasonCode | None = None
    detail: str | None = None
    target: TargetOutcome | None = None
    cleanup: CleanupObservation | None = None


def _state(answer: bool | None) -> PropertyState:
    return {True: PropertyState.DELIVERED, False: PropertyState.REFUSED}.get(answer, PropertyState.UNKNOWN)


def _observation(item: RequiredProperty, answer: bool | None, basis: str) -> PropertyObservation:
    return PropertyObservation(property=item, state=_state(answer), basis=basis)


def _both(first: bool | None, second: bool | None) -> bool | None:
    if first is False or second is False:
        return False
    return None if first is None or second is None else True


def host_properties(facts: HostFacts, denied_names: tuple[str, ...]) -> tuple[PropertyObservation, ...]:
    """Check each property on the host before the run."""
    namespaces = _both(facts.bubblewrap_supported, facts.namespaces)
    return (
        _observation(RequiredProperty.NAMESPACES, namespaces, "Bubblewrap version and namespace probe"),
        _observation(RequiredProperty.FILESYSTEM_POLICY, facts.landlock_abi is not None, "kernel Landlock ABI"),
        _observation(RequiredProperty.SYSCALL_SOCKET_FILTER, facts.libseccomp_supported, "libseccomp version"),
        _observation(
            RequiredProperty.DESCRIPTOR_ENVIRONMENT_HYGIENE,
            facts.launcher_python and not denied_names,
            "launcher interpreter and environment names",
        ),
        _observation(RequiredProperty.SUPERVISION, namespaces, "Bubblewrap namespace probe"),
    )


def refusal(
    properties: tuple[PropertyObservation, ...],
    reason: ReasonCode | None = None,
    detail: str | None = None,
    *,
    denied_names: tuple[str, ...] = (),
) -> Outcome:
    """A setup refusal before the target starts."""
    if reason is None:
        failed = [item.property.value for item in properties if item.state is not PropertyState.DELIVERED]
        reason = ReasonCode.ENVIRONMENT_NAME_DENIED if denied_names else ReasonCode.PROPERTY_UNAVAILABLE
        detail = f"not delivered: {', '.join(failed)}"
    return Outcome(RunStatus.REFUSED, FailureOrigin.SETUP, properties, reason, detail)


def stopped_before_launch(
    properties: tuple[PropertyObservation, ...], remaining: float, cancel_event: Event | None
) -> Outcome | None:
    """A cancellation or a spent deadline during the host checks stops the run."""
    if cancel_event is not None and cancel_event.is_set():
        return Outcome(
            RunStatus.CANCELLED, FailureOrigin.SUPERVISOR, properties,
            ReasonCode.CANCELLED, "the consumer cancelled the run",
        )
    if remaining <= 0:
        return Outcome(
            RunStatus.TIMED_OUT, FailureOrigin.SETUP, properties,
            ReasonCode.DEADLINE_EXCEEDED, "the deadline passed during the host checks",
        )
    return None


def setup_failure(properties: tuple[PropertyObservation, ...], detail: str) -> Outcome:
    """The wrapper could not prepare the run; the target did not start."""
    return Outcome(
        RunStatus.SUPERVISOR_FAILED, FailureOrigin.SETUP, properties, ReasonCode.SUPERVISOR_FAILED, detail
    )


_LAYER_PROPERTY = {
    "descriptors": RequiredProperty.DESCRIPTOR_ENVIRONMENT_HYGIENE,
    "no_new_privs": RequiredProperty.SYSCALL_SOCKET_FILTER,
    "limits": RequiredProperty.SUPERVISION,
    "landlock": RequiredProperty.FILESYSTEM_POLICY,
    "seccomp": RequiredProperty.SYSCALL_SOCKET_FILTER,
}


def _confirmed(present: bool) -> bool | None:
    """Present evidence delivers a property; absent evidence leaves it unknown."""
    return True if present else None


def run_properties(evidence: Evidence, cleanup: CleanupObservation | None) -> tuple[PropertyObservation, ...]:
    """Confirm each property from the run's own status channels."""
    applied = evidence.launch.applied
    clean = cleanup is not None and not cleanup.residual
    answers = {
        RequiredProperty.NAMESPACES: _confirmed(REQUIRED_NAMESPACES <= evidence.bubblewrap.namespaces),
        RequiredProperty.FILESYSTEM_POLICY: _confirmed("landlock" in applied),
        RequiredProperty.SYSCALL_SOCKET_FILTER: _confirmed({"no_new_privs", "seccomp"} <= applied.keys()),
        RequiredProperty.DESCRIPTOR_ENVIRONMENT_HYGIENE: _confirmed("descriptors" in applied),
        RequiredProperty.SUPERVISION: _confirmed(
            "limits" in applied and evidence.bubblewrap.child_started and clean
        ),
    }
    failed = evidence.launch.failure
    if failed is not None and failed[0] in _LAYER_PROPERTY:
        answers[_LAYER_PROPERTY[failed[0]]] = False
    bases = {
        RequiredProperty.NAMESPACES: "Bubblewrap status names the namespaces",
        RequiredProperty.FILESYSTEM_POLICY: "launcher Landlock status",
        RequiredProperty.SYSCALL_SOCKET_FILTER: "launcher no_new_privs and seccomp status",
        RequiredProperty.DESCRIPTOR_ENVIRONMENT_HYGIENE: "launcher descriptor status",
        RequiredProperty.SUPERVISION: "launcher limits, Bubblewrap child, and runner cleanup",
    }
    return tuple(_observation(item, answers[item], bases[item]) for item in RequiredProperty)


def _cleanup(observed: WorkerCleanup | None) -> CleanupObservation | None:
    if observed is None:
        return None
    return CleanupObservation(residual=tuple(observed.residual), seconds=observed.seconds)


def _setup_detail(evidence: Evidence) -> str:
    if evidence.launch.failure is not None:
        layer, detail = evidence.launch.failure
        return f"launcher layer {layer} failed: {detail}"[:512]
    stderr = evidence.result.stderr if evidence.result is not None else b""
    first = stderr.decode("utf-8", errors="replace").strip().splitlines()[:1]
    return f"Bubblewrap setup failed: {first[0][:_STDERR_LINE] if first else 'no detail'}"


def _completed(evidence: Evidence, result: WorkerResult) -> Outcome:
    cleanup = _cleanup(result.cleanup)
    properties = run_properties(evidence, cleanup)
    if not evidence.launch.executed:
        return Outcome(
            RunStatus.REFUSED, FailureOrigin.SETUP, properties,
            ReasonCode.ENGINE_SETUP_FAILED, _setup_detail(evidence), cleanup=cleanup,
        )
    exit_code = evidence.bubblewrap.exit_code
    if exit_code is None:
        # Without Bubblewrap's exit record, no observed status belongs to the target.
        return Outcome(
            RunStatus.SUPERVISOR_FAILED, FailureOrigin.SUPERVISOR, properties, ReasonCode.SUPERVISOR_FAILED,
            f"Bubblewrap reported no target exit; the runner saw exit status {result.returncode}",
            cleanup=cleanup,
        )
    target = TargetOutcome(
        exit_code=exit_code, stdout=result.stdout, stderr=result.stderr,
        stdout_bytes=len(result.stdout), stderr_bytes=len(result.stderr), truncated=False,
    )
    confirmed = all(item.state is PropertyState.DELIVERED for item in properties)
    reason = None if confirmed else ReasonCode.CONTAINMENT_UNCONFIRMED
    origin = FailureOrigin.NONE if exit_code == 0 else FailureOrigin.TARGET
    return Outcome(RunStatus.COMPLETED, origin, properties, reason, target=target, cleanup=cleanup)


_STOPS = {
    BoundedStopReason.TIMEOUT: (RunStatus.TIMED_OUT, ReasonCode.DEADLINE_EXCEEDED),
    BoundedStopReason.OVERFLOW: (RunStatus.OUTPUT_LIMIT_EXCEEDED, ReasonCode.OUTPUT_LIMIT_EXCEEDED),
    BoundedStopReason.RESIDUE: (RunStatus.SUPERVISOR_FAILED, ReasonCode.CLEANUP_UNCONFIRMED),
}


def _stopped(evidence: Evidence, failure: WorkerRunnerFailure, cancel_event: Event | None) -> Outcome:
    cleanup = _cleanup(failure.cleanup)
    properties = run_properties(evidence, cleanup)
    started = evidence.launch.executed
    target = (
        TargetOutcome(
            exit_code=None, stdout=b"", stderr=b"",
            stdout_bytes=failure.stdout_bytes, stderr_bytes=failure.stderr_bytes, truncated=True,
        )
        if started else None
    )
    if cancel_event is not None and cancel_event.is_set():
        return Outcome(
            RunStatus.CANCELLED, FailureOrigin.SUPERVISOR, properties,
            ReasonCode.CANCELLED, "the consumer cancelled the run", target, cleanup,
        )
    status, reason = _STOPS.get(failure.reason, (RunStatus.SUPERVISOR_FAILED, ReasonCode.SUPERVISOR_FAILED))
    if status is RunStatus.SUPERVISOR_FAILED:
        origin = FailureOrigin.SUPERVISOR
    else:
        origin = FailureOrigin.TARGET if started else FailureOrigin.SETUP
    return Outcome(status, origin, properties, reason, str(failure.reason)[:512], target, cleanup)


def classify(evidence: Evidence, cancel_event: Event | None) -> Outcome:
    """Classify one run from its evidence."""
    if evidence.result is not None:
        return _completed(evidence, evidence.result)
    if evidence.failure is not None:
        return _stopped(evidence, evidence.failure, cancel_event)
    properties = run_properties(evidence, None)
    if cancel_event is not None and cancel_event.is_set():
        return Outcome(
            RunStatus.CANCELLED, FailureOrigin.SUPERVISOR, properties,
            ReasonCode.CANCELLED, "the consumer cancelled the run",
        )
    detail = type(evidence.error).__name__ if evidence.error is not None else "no runner result"
    return Outcome(
        RunStatus.SUPERVISOR_FAILED, FailureOrigin.SUPERVISOR, properties,
        ReasonCode.SUPERVISOR_FAILED, f"the runner failed: {detail}",
    )
