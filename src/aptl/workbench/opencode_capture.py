"""Install one pinned observer and retain its data before private cleanup."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from aptl.core.opencode import OpenRouterRoute
from aptl.workbench.process import BoundedProcessError, REASON_TIMEOUT, REASON_CANCELLED
from aptl.workbench.opencode_history import read_native_history
from aptl.workbench.opencode_events import parse_opencode_response
from aptl.workbench.opencode_observation import read_request_observations

from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
from aptl.utils.pathsafe import create_exclusive_nofollow, open_contained_nofollow
from aptl.utils.strict_json import loads_strict
from aptl.workbench.provider_content_redaction import redact_cli_content
from aptl.workbench.provider_capture import (
    reduce_provider_capture,
    redact_capture_value,
)

if TYPE_CHECKING:
    from raes_contracts.contracts import ParticipantConfigurationResultModel
    from aptl.workbench.opencode_evidence import OpenCodeRunState

_PLUGIN_SHA256 = "dfe080c3aff2d08ca9beae8c13cacdd424b82579df3a4f8779fc762cb027ca67"

_CAPTURE_FILE = "provider-capture.jsonl"


class OpenCodeCaptureLease:
    """Private capture state receives no run-store path or write capability."""

    def __init__(
        self,
        work: Path,
        archive: ParticipantCaptureArchive,
        invocation_id: str,
        *,
        route: OpenRouterRoute,
        credentials: Mapping[str, str],
        prompt: bytes,
        request_observer: bool = False,
    ) -> None:
        self.work, self.archive, self.invocation_id = work, archive, invocation_id
        self.endpoint = route.endpoint
        archive.expect_invocation(invocation_id)
        self._serving_provider = route.serving_provider
        self._stdin_sha256, self._stdin_bytes = (
            hashlib.sha256(prompt).hexdigest(),
            len(prompt),
        )
        self._secrets = tuple(credentials.values())
        self._limit = archive.grant.binding.limits.max_bytes
        if not 1024 <= self._limit <= 64 * 1024 * 1024:
            raise ValueError("provider capture byte budget is unsupported")
        plugin = Path(__file__).with_name("provider_capture.mjs").read_bytes()
        if hashlib.sha256(plugin).hexdigest() != _PLUGIN_SHA256:
            raise ValueError("provider capture plugin differs from its pin")
        create_exclusive_nofollow(work, "provider-capture.mjs", plugin)
        create_exclusive_nofollow(work, _CAPTURE_FILE, b"")
        credential = credentials.get("OPENROUTER_API_KEY")
        if not credential:
            raise ValueError("provider capture requires the admitted credential grant")
        # OpenCode's documented auth.loader hook runs for a private auth entry.
        # This is the same granted key, never a new source or provider route.
        if not request_observer:
            create_exclusive_nofollow(
                work,
                "data/opencode/auth.json",
                json.dumps({"openrouter": {"type": "api", "key": credential}}).encode(),
            )

    @property
    def observer_options(self) -> dict[str, object]:
        """Private inputs used by either approved host-owned observer path."""
        return {
            "path": str(self.work / _CAPTURE_FILE),
            "maxBytes": self._limit,
            "endpoint": self.endpoint,
            "invocationId": self.invocation_id,
        }

    def configure(self, config: dict[str, object], environment: dict[str, str]) -> None:
        """Enable only this host-owned plugin; ambient discovery stays disabled."""
        if config.get("plugin") != [] or environment.get("OPENCODE_PURE") != "true":
            raise ValueError("provider capture isolation differs from its baseline")
        config["plugin"] = [
            [
                (self.work / "provider-capture.mjs").as_uri(),
                self.observer_options,
            ]
        ]
        environment.pop("OPENCODE_PURE")

    def retain(self, stdout: bytes, *, failure_reason: str | None = None) -> None:
        """Publish safe partial observations even after timeout or cancellation."""
        with open_contained_nofollow(self.work, _CAPTURE_FILE) as stream:
            data = stream.read(self._limit + 1)
        capture = reduce_provider_capture(
            data,
            invocation_id=self.invocation_id,
            secrets=self._secrets,
            max_bytes=self._limit,
        )
        cli_events, cli_complete = _cli_events(stdout)
        completed_steps = sum(
            event.get("type") == "step_finish" for event in cli_events
        )
        completed_calls = sum(call["state"] == "completed" for call in capture.calls)
        membership_complete = all(
            (capture.complete, cli_complete, completed_steps == completed_calls)
        )
        cli_events = redact_cli_content(
            cli_events,
            self._secrets,
            complete=failure_reason is None and membership_complete,
        )
        self.archive.record(
            {
                "invocation_id": self.invocation_id,
                "harness_failure_reason": failure_reason,
                "prompt_delivery": {
                    "stdin_sha256": self._stdin_sha256,
                    "stdin_bytes": self._stdin_bytes,
                    "provider_request_observed": bool(capture.calls),
                },
                "gateway_endpoint": self.endpoint,
                "capture_plugin_sha256": _PLUGIN_SHA256,
                "complete": membership_complete,
                "required_usage_complete": capture.required_usage_complete,
                "records": list(capture.records),
                "calls": [
                    {**call, "requested_provider": self._serving_provider}
                    for call in capture.calls
                ],
                "cli_events": cli_events,
                "observer_effect": "synchronous bounded local transport recording",
            }
        )


def _cli_events(stdout: bytes) -> tuple[list[dict[str, object]], bool]:
    """Keep an accepted prefix of supported CLI events and disclose parse failures."""
    cli_events = []
    cli_complete = True
    try:
        for line in stdout.splitlines():
            if not line.strip():
                continue
            event = loads_strict(line)
            if not isinstance(event, dict) or event.get("type") not in {
                "step_start",
                "step_finish",
                "tool_use",
                "text",
                "reasoning",
                "error",
            }:
                raise ValueError("participant event is unsupported")
            if event.get("type") == "error":
                # Provider errors are not transcript content.
                event = {"type": "error", "reason": "provider reported failure"}
            cli_events.append(event)
    except ValueError, TypeError, RecursionError:
        cli_complete = False
    return cli_events, cli_complete


def admitted_capture(
    archive: ParticipantCaptureArchive | None,
    configuration: ParticipantConfigurationResultModel | None,
) -> ParticipantCaptureArchive | None:
    """Require capture to match the already admitted participant configuration."""
    if archive is None:
        return None
    if (
        not isinstance(archive, ParticipantCaptureArchive)
        or configuration is None
        or archive.grant.configuration_digest != configuration.configuration_digest
        or archive.grant.participant_address != configuration.participant_address
    ):
        raise ValueError("participant capture differs from its admitted configuration")
    return archive


def prepare_capture(
    work: Path,
    archive: ParticipantCaptureArchive | None,
    invocation_id: str,
    *,
    route: OpenRouterRoute,
    credentials: Mapping[str, str],
    prompt: bytes,
    request_observer: bool,
) -> OpenCodeCaptureLease | None:
    """Install the admitted optional capture observer before any provider effects."""
    if archive is None:
        return None
    return OpenCodeCaptureLease(
        work,
        archive,
        invocation_id,
        route=route,
        credentials=credentials,
        prompt=prompt,
        request_observer=request_observer,
    )


def _capture_failure_reason(error: BoundedProcessError | None) -> str | None:
    """Keep native interruption reasons without exposing arbitrary harness diagnostics."""
    if error is None:
        return None
    return (
        error.reason
        if error.reason in {REASON_TIMEOUT, REASON_CANCELLED}
        else "harness-failed"
    )


def retain_native_observations(
    work: Path,
    state: OpenCodeRunState,
    prompt: bytes,
    model: str,
    expected_controls: Mapping[str, object] | None,
    request_observation_required: bool,
    capture_lease: OpenCodeCaptureLease | None,
) -> None:
    """Read native observations and finalize accepted capture even if another read fails."""
    try:
        response = state.partial or parse_opencode_response(
            state.result.stdout if state.result else b""
        )
        state.native_history = read_native_history(
            work,
            expected_prompt=prompt,
            expected_model=model,
            session_id=response.session_id,
        )
        if request_observation_required:
            state.request_observation = read_request_observations(
                work,
                expected_controls=expected_controls,
                expected_prompt_sha256=hashlib.sha256(prompt).hexdigest(),
            )
    finally:
        if capture_lease is not None:
            capture_lease.retain(
                state.result.stdout if state.result else state.failure_stdout,
                failure_reason=_capture_failure_reason(state.error),
            )


def retain_tool_event(
    archive: ParticipantCaptureArchive | None,
    event: Mapping[str, object],
    secrets: tuple[str, ...],
) -> None:
    """Retain tool observations after removing exactly the provider and MCP grants."""
    if archive is not None:
        archive.record_tool_event(redact_capture_value(dict(event), secrets))
