"""Reduce process and native observations through the existing safe evidence sink."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from copy import deepcopy
from typing import TYPE_CHECKING

from aptl.workbench.opencode_configuration import PROVIDER_CREDENTIAL_NAMES
from aptl.workbench.opencode_observation import OBSERVER_CREDENTIAL

if TYPE_CHECKING:
    from aptl.core.participant_tools.contracts import ToolSession
from dataclasses import dataclass, field, replace
import hashlib

from raes_contracts.contracts import ParticipantConfigurationResultModel

from aptl.core.opencode import NativeHistoryObservation, OpenCodeInvocationEvidence
from aptl.core.provider_observation import RequestObservation
from aptl.workbench.opencode_events import OpenCodeResponse, parse_opencode_response
from aptl.workbench.opencode_options import OpenCodeOptions
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
    failure_stdout: bytes = field(default=b"", repr=False)
    tool_transport_cleanup: str | None = None
    native_history: NativeHistoryObservation | None = None
    request_observation: RequestObservation | None = None

    def retain_partial(self, output: bytes) -> None:
        """Reduce private failure output without retaining completion text."""
        self.failure_stdout = output
        self.partial = replace(parse_opencode_response(output), text="")

    def require_observations(self, history_required: bool) -> None:
        """Refuse missing required evidence without confusing it with selected intent."""
        observation, history = self.request_observation, self.native_history
        if observation is not None and observation.status != "observed":
            raise AgentExecutionError(
                "participant provider request evidence is unavailable"
            )
        if history.status == "invalid" or (
            history_required and history.status != "observed"
        ):
            raise AgentExecutionError("participant native delivery evidence is invalid")


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


def invocation_recorder(
    options: OpenCodeOptions,
    model: str,
    prompt_sha256: str,
    configuration: ParticipantConfigurationResultModel | None,
) -> OpenCodeEvidenceRecorder:
    """Create the existing safe invocation identity from installed launch inputs."""
    return OpenCodeEvidenceRecorder(
        OpenCodeInvocationEvidence(
            action_id="",
            build=options.build,
            requested_model=model,
            endpoint=options.route.endpoint,
            requested_serving_provider=options.route.serving_provider,
            prompt_sha256=prompt_sha256,
            status="not-started",
            participant_address=configuration.participant_address
            if configuration is not None
            else None,
            configuration_digest=configuration.configuration_digest
            if configuration is not None
            else None,
            trial_scope=options.trial_scope,
        ),
        options.evidence_sink,
    )


def invocation_servers(
    stack: ExitStack,
    tools: ToolSession | None,
    configured_servers: dict[str, object],
    state: OpenCodeRunState,
    *,
    allowlisted: bool = False,
) -> dict[str, object]:
    """Open one scoped tool transport and retain its cleanup outcome.

    Without a tool session, an allowlisted executor runs its verified servers
    directly, and an ordinary executor runs none.
    """
    if tools is None:
        return _without_provider_credentials(deepcopy(configured_servers)) if allowlisted else {}
    state.tool_transport_cleanup = "uncertain"
    transport = tools.transport()
    carrier = transport.__enter__()

    def close_transport(*exc: object) -> bool | None:
        """Preserve native process failure if tool transport closure also fails."""
        if isinstance(exc[1], BoundedProcessError):
            state.error = exc[1]
        try:
            outcome = transport.__exit__(*exc)
        except Exception:
            raise AgentExecutionError(
                "participant tool transport cleanup failed"
            ) from None
        state.tool_transport_cleanup = "succeeded"
        return outcome

    stack.push(close_transport)
    servers = deepcopy(configured_servers)
    for name, server in servers.items():
        server["environment"].update(carrier.environment(name))
    return _without_provider_credentials(servers)


def _without_provider_credentials(servers: dict[str, object]) -> dict[str, object]:
    """Keep every provider credential and credential path out of MCP children."""
    for server in servers.values():
        server["environment"].update(
            dict.fromkeys(PROVIDER_CREDENTIAL_NAMES | {OBSERVER_CREDENTIAL}, "")
        )
    return servers
