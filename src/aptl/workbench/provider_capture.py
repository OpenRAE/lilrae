"""Bounded reduction of native provider frames, before private state deletion."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
import re

from aptl.utils.redaction import redact_granted_secrets
from aptl.utils.strict_json import loads_strict

_IDENTITY = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_CONTROL_FIELDS = (
    "model",
    "temperature",
    "top_p",
    "top_k",
    "seed",
    "max_tokens",
    "max_completion_tokens",
    "reasoning",
    "provider",
    "usage",
    "stream_options",
)
_TERMINAL = {
    "request-finished",
    "request-failed",
    "response-failed",
    "response-cancelled",
}
_KINDS = _TERMINAL | {"capture-ready", "request", "response"}


@dataclass(frozen=True)
class ProviderCapture:
    """Accepted native rows and explicit completeness, separate from execution."""

    records: tuple[dict[str, object], ...] = field(repr=False)
    calls: tuple[dict[str, object], ...] = field(repr=False)
    complete: bool
    required_usage_complete: bool


def redact_capture_value(value: object, secrets: tuple[str, ...]) -> object:
    """Remove exact granted credentials before the shared recursive redactor."""
    return redact_granted_secrets(value, secrets)


def _count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value < 2**53 else None


def _identity(value: object) -> str | None:
    return value if isinstance(value, str) and _IDENTITY.fullmatch(value) else None


def _cost(value: object) -> str | None:
    if type(value) not in {str, int, Decimal}:
        return None
    try:
        number = Decimal(value)
        if number.is_finite() and 0 <= number <= 10**6:
            return str(number)
    except InvalidOperation, ValueError:
        pass
    return None


def _response_json(frame: Mapping[str, object]) -> dict[str, object]:
    """Keep the provider's decimal spelling; strict parsing rejects ambiguity."""
    original = frame["json"]
    parsed = loads_strict(original)
    if not isinstance(parsed, dict):
        raise ValueError("provider response is not an object")
    return json.loads(original, parse_float=Decimal)


def _call(rows: list[dict[str, object]]) -> dict[str, object]:
    request = rows[0]
    body = loads_strict(request["body"])
    if not isinstance(body, dict):
        raise ValueError("provider request is not an object")
    responses = [_response_json(row) for row in rows if row["kind"] == "response"]
    claims: dict[str, object] = {}
    inconsistent = False
    usage = None
    for response in responses:
        for source, target in (
            ("id", "generation_id"),
            ("model", "served_model"),
            ("provider", "served_provider"),
        ):
            candidate = response.get(source)
            if isinstance(candidate, str) and len(candidate) <= 256:
                if target in claims and claims[target] != candidate:
                    inconsistent = True
                claims[target] = candidate
        if response.get("usage") is not None:
            candidate = response["usage"]
            if not isinstance(candidate, dict) or (
                usage is not None and usage != candidate
            ):
                inconsistent = True
            else:
                usage = candidate
    usage = usage or {}
    final = rows[-1]
    completed = (
        final["kind"] == "request-finished"
        and type(final.get("status")) is int
        and 200 <= final["status"] < 300
    )
    inputs, outputs = (
        _count(usage.get("prompt_tokens")),
        _count(usage.get("completion_tokens")),
    )
    details = usage.get("completion_tokens_details") or {}
    cache = usage.get("prompt_tokens_details") or {}
    cost = _cost(usage.get("cost"))
    result = {
        "request_id": request["request_id"],
        "invocation_id": request["invocation_id"],
        "state": "completed"
        if completed
        else ("failed" if final["kind"] in _TERMINAL else "unsettled"),
        "request_controls": {key: body[key] for key in _CONTROL_FIELDS if key in body},
        "provider_claims": {
            key: claims.get(key)
            for key in ("generation_id", "served_model", "served_provider")
        },
        "identity_limit": "returned gateway claims; no independent model snapshot attestation",
        "effective_token_limit": None,
        "effective_limit_unavailable_reason": "not attested in the provider response",
        "input_tokens": inputs,
        "output_tokens": outputs,
        "reasoning_tokens": _count(details.get("reasoning_tokens"))
        if isinstance(details, dict)
        else None,
        "cache_read_tokens": _count(cache.get("cached_tokens"))
        if isinstance(cache, dict)
        else None,
        "cache_write_tokens": _count(cache.get("cache_write_tokens"))
        if isinstance(cache, dict)
        else None,
        "usage_convention": "gateway prompt/completion totals; reasoning and cache are breakdowns, never added to totals",
        "usage_unavailable_reason": "missing or invalid provider counts"
        if inputs is None or outputs is None
        else None,
        "cost": cost,
        "currency": "USD" if cost is not None else None,
        "billing_source": "gateway response usage.cost" if cost is not None else None,
        "billing_basis": "gateway-reported" if cost is not None else None,
        "cost_unavailable_reason": "missing or invalid optional gateway billing"
        if cost is None
        else None,
        "started_at": request["observed_at"],
        "finished_at": final["observed_at"] if final["kind"] in _TERMINAL else None,
        "duration_ms": final["monotonic_ms"] - request["monotonic_ms"],
        "required_usage_complete": not inconsistent
        and (not completed or (inputs is not None and outputs is not None)),
        "claims_consistent": not inconsistent,
    }
    result["unavailable_reasons"] = [
        {"field": key, "reason": "not disclosed in the provider response"}
        for key in ("generation_id", "served_model", "served_provider")
        if claims.get(key) is None
    ] + [
        {"field": key, "reason": "not exposed in provider usage"}
        for key in ("reasoning_tokens", "cache_read_tokens", "cache_write_tokens")
        if result[key] is None
    ]
    return result


def _validate_frame(row: object, index: int, invocation_id: str) -> None:
    if (
        not isinstance(row, dict)
        or row.get("sequence") != index
        or row.get("invocation_id") != invocation_id
        or row.get("kind") not in _KINDS
    ):
        raise ValueError("capture frame refused")
    if not isinstance(row.get("observed_at"), str) or type(
        row.get("monotonic_ms")
    ) not in {int, float}:
        raise ValueError("capture clock refused")


def reduce_provider_capture(
    data: bytes,
    *,
    invocation_id: str,
    secrets: tuple[str, ...],
    max_bytes: int,
) -> ProviderCapture:
    """Preserve accepted prefixes, never treating missing membership as empty success."""
    records: list[dict[str, object]] = []
    requests: dict[str, list[dict[str, object]]] = {}
    complete = bool(data) and len(data) <= max_bytes
    try:
        if not _identity(invocation_id):
            raise ValueError("capture bounds refused")
        for index, line in enumerate(data[:max_bytes].splitlines()):
            if index >= 4096:
                raise ValueError("capture item bound exceeded")
            row = loads_strict(line)
            _validate_frame(row, index, invocation_id)
            if row["kind"] == "capture-ready":
                if index != 0:
                    raise ValueError("capture readiness repeated")
            else:
                request_id = _identity(row.get("request_id"))
                if request_id is None or (index == 0):
                    raise ValueError("capture request identity refused")
                if row["kind"] == "request":
                    if request_id in requests or not isinstance(
                        loads_strict(row["body"]), dict
                    ):
                        raise ValueError("capture request repeated")
                    requests[request_id] = []
                elif (
                    request_id not in requests
                    or requests[request_id][-1]["kind"] in _TERMINAL
                ):
                    raise ValueError("capture response membership refused")
                if row["kind"] == "response":
                    _response_json(row)
                requests[request_id].append(row)
            records.append(row)
    except ValueError, KeyError, TypeError, RecursionError:
        complete = False
    calls = []
    for rows in requests.values():
        try:
            calls.append(_call(rows))
        except ValueError, TypeError, KeyError, RecursionError:
            complete = False
    complete = (
        complete
        and bool(requests)
        and len(calls) == len(requests)
        and all(
            call["state"] != "unsettled" and call["claims_consistent"] for call in calls
        )
    )
    from aptl.workbench.provider_content_redaction import redact_response_records

    safe_records, withheld = redact_response_records(records, calls, secrets)
    return ProviderCapture(
        records=tuple(safe_records),
        calls=tuple(redact_capture_value(call, secrets) for call in calls),
        complete=complete and not withheld,
        required_usage_complete=bool(calls)
        and all(call["required_usage_complete"] for call in calls),
    )
