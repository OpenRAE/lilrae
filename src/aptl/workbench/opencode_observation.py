"""Install the approved local observer and reduce its private bounded journal."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from aptl.core.provider_observation import (
    Count,
    Digest,
    SafeObservation,
    ObservedContext,
    ObservedRequestControls,
    ProviderCallObservation,
    ProviderResponseObservation,
    RequestObservation,
)
from aptl.utils.pathsafe import (
    PathContainmentError,
    REASON_NOT_FOUND,
    create_exclusive_nofollow,
    open_contained_nofollow,
)
from aptl.utils.strict_json import loads_strict

OBSERVER_SHA256 = "ffbff358064493d84087d35a87f13cd74044ba864476194ee47f6caa901e7791"
OBSERVER_CREDENTIAL = "LILRAE_OPENCODE_PROVIDER_KEY"
MAX_OBSERVATION_BYTES = 16 * 1024 * 1024
OBSERVER_MODULE = "request_observer.mjs"


class Ready(SafeObservation):
    """Journal identity and native-turn declaration written before requests."""

    kind: Literal["ready"]
    observer_sha256: Digest
    native_turn_limit: Annotated[int, Field(ge=1, le=10_000)] | None = None


class Request(SafeObservation):
    """Safe request controls and context commitments for a new call."""

    kind: Literal["request"]
    call_id: Annotated[int, Field(ge=1, le=10_000)]
    timestamp_ms: Count
    controls: ObservedRequestControls
    context: Annotated[
        tuple[ObservedContext, ...], Field(min_length=1, max_length=4096)
    ]


class Response(SafeObservation):
    """Allowlisted response metadata for a previously dispatched call."""

    kind: Literal["response"]
    call_id: Annotated[int, Field(ge=1, le=10_000)]
    timestamp_ms: Count
    http_status: Annotated[int, Field(ge=100, le=599)]
    response: ProviderResponseObservation


class End(SafeObservation):
    """One terminal state for a dispatched call."""

    kind: Literal["end"]
    call_id: Annotated[int, Field(ge=1, le=10_000)]
    timestamp_ms: Count
    state: Literal["completed", "failed", "cancelled"]


_EVENT = TypeAdapter(
    Annotated[Ready | Request | Response | End, Field(discriminator="kind")]
)


def _validate_request(
    event: Request,
    expected_controls: ObservedRequestControls | None,
    expected_prompt_sha256: str | None,
) -> None:
    """Compare observed controls and authored-prefix membership with retained pins."""
    if expected_controls is not None:
        actual = event.controls.model_dump(exclude_unset=True)
        actual.pop("usage", None)
        actual.pop("stream_options", None)
        if actual != expected_controls.model_dump(exclude_unset=True):
            raise ValueError("request controls differ from their pin")
    if (
        expected_prompt_sha256 is not None
        and sum(
            item.authored_prefix_sha256 == expected_prompt_sha256
            for item in event.context
        )
        != 1
    ):
        raise ValueError("request prefix differs from its pin")


def _update_call(
    call: ProviderCallObservation, event: Response | End
) -> ProviderCallObservation:
    """Advance one call without changing its generation or request membership."""
    if call.state != "dispatched" or event.timestamp_ms < call.requested_at_ms:
        raise ValueError("observation order differs")
    if isinstance(event, End):
        return call.model_copy(
            update={"state": event.state, "completed_at_ms": event.timestamp_ms}
        )
    previous = call.response
    if (
        previous is not None
        and previous.generation_id is not None
        and event.response.generation_id != previous.generation_id
    ):
        raise ValueError("response membership differs")
    return call.model_copy(
        update={"response": event.response, "http_status": event.http_status}
    )


def _journal_calls(
    lines: list[bytes],
    observer_sha256: str,
    expected_controls: ObservedRequestControls | None,
    expected_prompt_sha256: str | None,
) -> tuple[Ready, tuple[ProviderCallObservation, ...]]:
    """Validate bounded event order and reduce it to safe call records."""
    if not lines or len(lines) > 50_000 or any(len(line) > 131_072 for line in lines):
        raise ValueError("invalid observation journal")
    loads_strict(lines[0])
    ready = _EVENT.validate_json(lines[0])
    if not isinstance(ready, Ready) or ready.observer_sha256 != observer_sha256:
        raise ValueError("observer identity differs")
    calls = {}
    for line in lines[1:]:
        loads_strict(line)
        event = _EVENT.validate_json(line)
        if isinstance(event, Request):
            calls[event.call_id] = _new_call(
                event,
                len(calls),
                expected_controls,
                expected_prompt_sha256,
            )
        else:
            if isinstance(event, Ready) or event.call_id not in calls:
                raise ValueError("request membership differs")
            calls[event.call_id] = _update_call(calls[event.call_id], event)
    return ready, tuple(calls.values())


def _new_call(
    event: Request,
    count: int,
    controls: ObservedRequestControls | None,
    prompt_sha256: str | None,
) -> ProviderCallObservation:
    """Admit exactly the next request with independently checked controls."""
    if event.call_id != count + 1:
        raise ValueError("request membership differs")
    _validate_request(event, controls, prompt_sha256)
    return ProviderCallObservation(
        call_id=event.call_id,
        requested_at_ms=event.timestamp_ms,
        controls=event.controls,
        context=event.context,
    )


def read_request_observations(
    work: Path,
    *,
    observer_sha256: str = OBSERVER_SHA256,
    max_bytes: int = MAX_OBSERVATION_BYTES,
    expected_controls: ObservedRequestControls | None = None,
    expected_prompt_sha256: str | None = None,
) -> RequestObservation:
    """Read only safe schema fields; missing and interrupted calls remain visible."""
    status = "invalid"
    try:
        with open_contained_nofollow(work, "provider-observations.jsonl") as source:
            payload = source.read(max_bytes + 1)
        if len(payload) > max_bytes:
            return RequestObservation(
                status="oversized", observer_sha256=observer_sha256
            )
        truncated = not payload.endswith(b"\n")
        if truncated:
            payload = payload.rsplit(b"\n", 1)[0] if b"\n" in payload else b""
        ready, calls = _journal_calls(
            payload.splitlines(),
            observer_sha256,
            expected_controls,
            expected_prompt_sha256,
        )
        status = (
            "observed"
            if calls
            and not truncated
            and all(c.state != "dispatched" for c in calls)
            and any(c.state == "completed" for c in calls)
            else "partial"
        )
        return RequestObservation(
            status=status,
            observer_sha256=observer_sha256,
            calls=calls,
            native_turn_limit=ready.native_turn_limit,
        )
    except PathContainmentError as exc:
        status = "missing" if exc.reason == REASON_NOT_FOUND else "invalid"
    except OSError, ValueError, TypeError, KeyError:
        status = "invalid"
    return RequestObservation(status=status, observer_sha256=observer_sha256)


def install_request_observer(
    work: Path, config: dict[str, object], environment: Mapping[str, str], prompt: bytes
) -> tuple[dict[str, str], ObservedRequestControls]:
    """Leave a failed plugin load unable to reach the admitted provider."""
    module = Path(__file__).with_name(OBSERVER_MODULE).read_bytes()
    if hashlib.sha256(module).hexdigest() != OBSERVER_SHA256:
        raise ValueError("participant observer differs from its pin")
    provider = config["provider"]["openrouter"]
    model = config["model"].removeprefix("openrouter/")
    options = provider["models"][model]["options"]
    expected = {
        "model": model,
        "provider": options["provider"],
        "max_tokens": int(environment["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"]),
        "stream": True,
    }
    if "reasoning" in options:
        expected["reasoning"] = options["reasoning"]
    agent = config.get("agent", {}).get("build", {})
    for name in ("temperature", "top_p"):
        if name in agent:
            expected[name] = agent[name]
    inputs = {
        "observer_sha256": OBSERVER_SHA256,
        "endpoint": provider["options"]["baseURL"],
        "controls": expected,
        "native_turn_limit": config.get("agent", {}).get("build", {}).get("steps"),
        "prompt_bytes": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
    }
    create_exclusive_nofollow(work, "observer-input.json", json.dumps(inputs).encode())
    create_exclusive_nofollow(work, OBSERVER_MODULE, module)
    config["plugin"] = [(work / OBSERVER_MODULE).as_uri()]
    provider["options"].update(baseURL="lilrae-observer-required://provider", apiKey="")
    child = dict(environment)
    child[OBSERVER_CREDENTIAL] = child.pop("OPENROUTER_API_KEY")
    child["OPENCODE_PURE"] = "false"
    child["npm_config_offline"] = "true"
    return child, ObservedRequestControls.model_validate_json(json.dumps(expected))
