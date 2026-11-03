"""Bounded observation of existing native owners, with fixed diagnostics."""

from collections.abc import Callable
from threading import local

from raes_contracts.diagnostics import Diagnostic, Severity
from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

from aptl.core.readiness_record import MAX_READINESS_RECORD_BYTES
from aptl.utils.probe_execution import ProbeProcessRunner, bounded_probe_commands


class ReadinessObserver:
    """Limit owner calls and retain uncertainty about native process cessation."""

    def __init__(
        self,
        budget_ms: int,
        adapter: LocalExecutionAdapter | None,
        runner: ProbeProcessRunner | None,
        *,
        require_runner: bool,
    ) -> None:
        self.budget_ms = budget_ms
        self._adapter = adapter or LocalExecutionAdapter(control_capacity=1)
        self._own_adapter = adapter is None
        self._runner, self._require_runner = runner, require_runner
        self._context = local()
        self._probe_residue = False

    def call[T](self, method: Callable[..., T], *args: object, **kwargs: object) -> T:
        """Run an owner under one bounded control call, preserving nested scope."""
        if getattr(self._context, "active", False):
            return method(*args, **kwargs)

        def invoke() -> T:
            """Mark the adapter worker while it observes one native owner."""
            self._context.active = True
            try:
                return self._invoke_scoped(method, *args, **kwargs)
            finally:
                self._context.active = False

        return self._adapter.call("control", invoke, timeout_ms=self.budget_ms)

    def _invoke_scoped[T](
        self, method: Callable[..., T], *args: object, **kwargs: object
    ) -> T:
        """Bind process limits and retain cleanup uncertainty even on exceptions."""
        if self._runner is None:
            if self._require_runner:
                raise ValueError("trial-readiness-bounded-runner-unavailable")
            return method(*args, **kwargs)
        with bounded_probe_commands(self._runner, MAX_READINESS_RECORD_BYTES) as scope:
            try:
                return method(*args, **kwargs)
            finally:
                self._probe_residue |= not scope.cessation_confirmed

    def check(
        self, checks: list[Diagnostic], name: str, operation: Callable[[], bool] | None
    ) -> bool:
        """Retain only a fixed diagnostic and a strict positive owner result."""
        reason, passed = "unavailable", False
        if operation is not None:
            try:
                result = self.call(operation)
                passed = result is True
                reason = "malformed"
                if type(result) is bool:
                    reason = "passed" if passed else "failed"
            except TimeoutError:
                reason = "timeout"
            except Exception:
                # Foreign owner code and failures never supply diagnostic text.
                reason = "crashed"
        checks.append(
            Diagnostic(
                code=f"lilrae.readiness.{name}.{reason}",
                domain="trial-readiness",
                address=f"readiness.{name}",
                message=f"Required {name} check {reason}.",
                severity=Severity.INFO if passed else Severity.ERROR,
            )
        )
        return passed

    @property
    def has_pending(self) -> bool:
        """Report pending calls or unresolved process cessation."""
        return self._adapter.pending_calls != 0 or self._probe_residue

    def close(self) -> None:
        """Drain the bounded adapter when this observer owns it."""
        if self._own_adapter:
            self._adapter.close(timeout_ms=self.budget_ms)
