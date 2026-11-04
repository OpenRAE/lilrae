"""Install one pinned observer and retain its data before private cleanup."""

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path

from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
from aptl.utils.pathsafe import create_exclusive_nofollow, open_contained_nofollow
from aptl.utils.strict_json import loads_strict
from aptl.workbench.provider_content_redaction import redact_cli_content
from aptl.workbench.provider_capture import (
    reduce_provider_capture,
)

_PLUGIN_SHA256 = "c96ada24572f13fc5cebf970a4103dc7f837652a865fb619f2198fbb7650cfbe"


class OpenCodeCaptureLease:
    """Private capture state receives no run-store path or write capability."""

    def __init__(
        self,
        work: Path,
        archive: ParticipantCaptureArchive,
        invocation_id: str,
        endpoint: str,
        credentials: Mapping[str, str],
        serving_provider: str,
        stdin_sha256: str,
        stdin_bytes: int,
        *,
        request_observer: bool = False,
    ) -> None:
        self.work, self.archive, self.invocation_id = work, archive, invocation_id
        self.endpoint = endpoint
        archive.expect_invocation(invocation_id)
        self._serving_provider = serving_provider
        self._stdin_sha256, self._stdin_bytes = stdin_sha256, stdin_bytes
        self._secrets = tuple(credentials.values())
        self._limit = archive.grant.binding.limits.max_bytes
        if not 1024 <= self._limit <= 64 * 1024 * 1024:
            raise ValueError("provider capture byte budget is unsupported")
        plugin = Path(__file__).with_name("provider_capture.mjs").read_bytes()
        if hashlib.sha256(plugin).hexdigest() != _PLUGIN_SHA256:
            raise ValueError("provider capture plugin differs from its pin")
        create_exclusive_nofollow(work, "provider-capture.mjs", plugin)
        create_exclusive_nofollow(work, "provider-capture.jsonl", b"")
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
            "path": str(self.work / "provider-capture.jsonl"),
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
        with open_contained_nofollow(self.work, "provider-capture.jsonl") as stream:
            data = stream.read(self._limit + 1)
        capture = reduce_provider_capture(
            data,
            invocation_id=self.invocation_id,
            secrets=self._secrets,
            max_bytes=self._limit,
        )
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
        completed_steps = sum(
            event.get("type") == "step_finish" for event in cli_events
        )
        completed_calls = sum(call["state"] == "completed" for call in capture.calls)
        cli_events = redact_cli_content(
            cli_events,
            self._secrets,
            complete=(
                failure_reason is None
                and cli_complete
                and capture.complete
                and completed_steps == completed_calls
            ),
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
                "complete": capture.complete
                and cli_complete
                and completed_steps == completed_calls,
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
