"""Reduce process and native observations through the existing safe evidence sink."""

from collections.abc import Callable
from dataclasses import dataclass, replace
import hashlib

from aptl.core.opencode import NativeHistoryObservation, OpenCodeInvocationEvidence
from aptl.core.provider_observation import RequestObservation
from aptl.workbench.opencode_events import OpenCodeResponse, parse_opencode_response
from aptl.workbench.process import (
    AgentExecutionError,
    BoundedProcessError,
    ProcessResult,
)


@dataclass(repr=False)
class OpenCodeRunState:
    """Private invocation state; only the recorder's safe projection is retained."""

    result: ProcessResult | None = None
    error: BoundedProcessError | None = None
    partial: OpenCodeResponse | None = None
    tool_transport_cleanup: str | None = None
    native_history: NativeHistoryObservation | None = None
    request_observation: RequestObservation | None = None

    def retain_partial(self, output: bytes) -> None:
        """Reduce private failure output without retaining completion text."""
        self.partial = replace(parse_opencode_response(output), text="")


class OpenCodeEvidenceRecorder:
    """Keep selected identity separate from observations and sink failure state."""

    def __init__(
        self,
        identity: OpenCodeInvocationEvidence,
        sink: Callable[[OpenCodeInvocationEvidence], None] | None,
    ) -> None:
        self._identity = identity
        self._sink = sink
        self.last: OpenCodeInvocationEvidence | None = None

    def record(self, action_id: str, status: str, state: OpenCodeRunState) -> None:
        """Retain safe partial metadata after process and transport cleanup."""
        result, error, partial = state.result, state.error, state.partial
        native_history = state.native_history
        response = partial or parse_opencode_response(result.stdout if result else b"")
        cleanup = None
        stdout_sha256 = None
        stdout_bytes = stderr_bytes = 0
        if result is not None:
            cleanup = result.cleanup
            stdout_sha256 = hashlib.sha256(result.stdout).hexdigest()
            stdout_bytes, stderr_bytes = len(result.stdout), len(result.stderr)
        elif error is not None:
            cleanup = error.cleanup
            stdout_sha256 = error.stdout_sha256
            stdout_bytes, stderr_bytes = error.stdout_bytes, error.stderr_bytes
        self.last = replace(
            self._identity,
            action_id=action_id,
            status=status,
            stdout_sha256=stdout_sha256,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            partial_text_sha256=response.partial_text_sha256,
            session_id=response.session_id
            or (native_history.session_id if native_history is not None else None),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=response.cost,
            finish_reason=response.finish_reason,
            cleanup_residual=cleanup.residual if cleanup else None,
            tool_transport_cleanup=state.tool_transport_cleanup,
            native_history=native_history,
            request_observation=state.request_observation,
        )
        if self._sink is not None:
            try:
                self._sink(self.last)
            except Exception:
                self.last = replace(self.last, status="failed")
                raise AgentExecutionError(
                    "participant evidence could not be retained"
                ) from None
