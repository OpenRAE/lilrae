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
    """Accept only exact nonnegative provider counts within the numeric bound."""
    return value if type(value) is int and 0 <= value < 2**53 else None


def _identity(value: object) -> str | None:
    """Accept a bounded opaque invocation or request identifier."""
    return value if isinstance(value, str) and _IDENTITY.fullmatch(value) else None


def _cost(value: object) -> str | None:
    """Accept finite nonnegative optional gateway billing."""
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


def _update_claims(response: Mapping[str, object], claims: dict[str, object]) -> bool:
    """Keep bounded returned claims and disclose contradictory frame identities."""
    inconsistent = False
    for source, target in (
        ("id", "generation_id"),
        ("model", "served_model"),
        ("provider", "served_provider"),
    ):
        candidate = response.get(source)
        if isinstance(candidate, str) and len(candidate) <= 256:
            inconsistent |= target in claims and claims[target] != candidate
            claims[target] = candidate
    return inconsistent


def _claims_and_usage(
    responses: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object], bool]:
    """Reconcile returned identity and the single exposed usage observation."""
    claims: dict[str, object] = {}
    usage = None
    inconsistent = False
    for response in responses:
        inconsistent |= _update_claims(response, claims)
        candidate = response.get("usage")
        if candidate is not None:
            if not isinstance(candidate, dict) or (
                usage is not None and usage != candidate
            ):
                inconsistent = True
            else:
                usage = candidate
    return claims, usage or {}, inconsistent


def _nested_count(usage: Mapping[str, object], details: str, field: str) -> int | None:
    """Read an optional numeric usage breakdown without inventing a total."""
    values = usage.get(details) or {}
    return _count(values.get(field)) if isinstance(values, dict) else None


def _usage_fields(usage: Mapping[str, object]) -> dict[str, object]:
    """Project token totals and optional breakdowns using the gateway convention."""
    inputs, outputs = (
        _count(usage.get("prompt_tokens")),
        _count(usage.get("completion_tokens")),
    )
    return {
        "input_tokens": inputs,
        "output_tokens": outputs,
        "reasoning_tokens": _nested_count(
            usage, "completion_tokens_details", "reasoning_tokens"
        ),
        "cache_read_tokens": _nested_count(
            usage, "prompt_tokens_details", "cached_tokens"
        ),
        "cache_write_tokens": _nested_count(
            usage, "prompt_tokens_details", "cache_write_tokens"
        ),
        "usage_convention": (
            "gateway prompt/completion totals; reasoning and cache are breakdowns, never added to totals"
        ),
        "usage_unavailable_reason": (
            "missing or invalid provider counts"
            if inputs is None or outputs is None
            else None
        ),
    }


def _billing_fields(usage: Mapping[str, object]) -> dict[str, object]:
    """Keep optional gateway billing separate from required token collection."""
    cost = _cost(usage.get("cost"))
    return {
        "cost": cost,
        "currency": "USD" if cost is not None else None,
        "billing_source": "gateway response usage.cost" if cost is not None else None,
        "billing_basis": "gateway-reported" if cost is not None else None,
        "cost_unavailable_reason": (
            "missing or invalid optional gateway billing" if cost is None else None
        ),
    }


def _call_state(final: Mapping[str, object], completed: bool) -> str:
    """Distinguish completed delivery, terminal failure, and unfinished membership."""
    if completed:
        return "completed"
    return "failed" if final["kind"] in _TERMINAL else "unsettled"


def _unavailable_fields(
    claims: Mapping[str, object], result: Mapping[str, object]
) -> list[dict[str, str]]:
    """Name each unexposed identity or optional usage field explicitly."""
    return [
        {"field": key, "reason": "not disclosed in the provider response"}
        for key in ("generation_id", "served_model", "served_provider")
        if claims.get(key) is None
    ] + [
        {"field": key, "reason": "not exposed in provider usage"}
        for key in ("reasoning_tokens", "cache_read_tokens", "cache_write_tokens")
        if result[key] is None
    ]


def _completed_call(final: Mapping[str, object]) -> bool:
    """Require a terminal request frame with a successful HTTP status."""
    return (
        final["kind"] == "request-finished"
        and type(final.get("status")) is int
        and 200 <= final["status"] < 300
    )


def _required_usage_complete(result: Mapping[str, object], completed: bool) -> bool:
    """Successful calls require both counts; failed requests keep their failure evidence."""
    return bool(result["claims_consistent"]) and (
        not completed
        or (result["input_tokens"] is not None and result["output_tokens"] is not None)
    )


def _call(rows: list[dict[str, object]]) -> dict[str, object]:
    """Reduce one provider request and its accepted response frames."""
    request = rows[0]
    body = loads_strict(request["body"])
    if not isinstance(body, dict):
        raise ValueError("provider request is not an object")
    responses = [_response_json(row) for row in rows if row["kind"] == "response"]
    claims, usage, inconsistent = _claims_and_usage(responses)
    final = rows[-1]
    completed = _completed_call(final)
    result = {
        "request_id": request["request_id"],
        "invocation_id": request["invocation_id"],
        "state": _call_state(final, completed),
        "request_controls": {key: body[key] for key in _CONTROL_FIELDS if key in body},
        "provider_claims": {
            key: claims.get(key)
            for key in ("generation_id", "served_model", "served_provider")
        },
        "identity_limit": "returned gateway claims; no independent model snapshot attestation",
        "effective_token_limit": None,
        "effective_limit_unavailable_reason": "not attested in the provider response",
        **_usage_fields(usage),
        **_billing_fields(usage),
        "started_at": request["observed_at"],
        "finished_at": final["observed_at"] if final["kind"] in _TERMINAL else None,
        "duration_ms": final["monotonic_ms"] - request["monotonic_ms"],
        "claims_consistent": not inconsistent,
    }
    result["required_usage_complete"] = _required_usage_complete(result, completed)
    result["unavailable_reasons"] = _unavailable_fields(claims, result)
    return result


def _validate_frame(row: object, index: int, invocation_id: str) -> None:
    """Require frame membership, order, kind, and observation clocks."""
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


def _record_request_frame(
    row: dict[str, object],
    request_id: str,
    requests: dict[str, list[dict[str, object]]],
) -> None:
    """Admit each request once and refuse responses outside its open membership."""
    if row["kind"] == "request":
        if request_id in requests or not isinstance(loads_strict(row["body"]), dict):
            raise ValueError("capture request repeated")
        requests[request_id] = []
    elif request_id not in requests or requests[request_id][-1]["kind"] in _TERMINAL:
        raise ValueError("capture response membership refused")
    if row["kind"] == "response":
        _response_json(row)
    requests[request_id].append(row)


def _admit_capture_row(
    row: dict[str, object], index: int, requests: dict[str, list[dict[str, object]]]
) -> None:
    """Require initial readiness before any identified provider request."""
    if row["kind"] == "capture-ready":
        if index != 0:
            raise ValueError("capture readiness repeated")
        return
    request_id = _identity(row.get("request_id"))
    if request_id is None or index == 0:
        raise ValueError("capture request identity refused")
    _record_request_frame(row, request_id, requests)


def _read_capture_rows(
    data: bytes,
    invocation_id: str,
    records: list[dict[str, object]],
    requests: dict[str, list[dict[str, object]]],
) -> None:
    """Append only admitted frames, retaining the accepted prefix on failure."""
    if not _identity(invocation_id):
        raise ValueError("capture bounds refused")
    for index, line in enumerate(data.splitlines()):
        if index >= 4096:
            raise ValueError("capture item bound exceeded")
        row = loads_strict(line)
        _validate_frame(row, index, invocation_id)
        _admit_capture_row(row, index, requests)
        records.append(row)


def _reduce_calls(
    requests: dict[str, list[dict[str, object]]],
) -> tuple[list[dict[str, object]], bool]:
    """Keep independently valid call reductions when another request is malformed."""
    calls = []
    complete = True
    for rows in requests.values():
        try:
            calls.append(_call(rows))
        except ValueError, TypeError, KeyError, RecursionError:
            complete = False
    complete &= bool(requests) and len(calls) == len(requests)
    complete &= all(
        call["state"] != "unsettled" and call["claims_consistent"] for call in calls
    )
    return calls, complete


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
        _read_capture_rows(data[:max_bytes], invocation_id, records, requests)
    except ValueError, KeyError, TypeError, RecursionError:
        complete = False
    calls, calls_complete = _reduce_calls(requests)
    from aptl.workbench.provider_content_redaction import redact_response_records

    safe_records, withheld = redact_response_records(records, calls, secrets)
    return ProviderCapture(
        records=tuple(safe_records),
        calls=tuple(redact_capture_value(call, secrets) for call in calls),
        complete=complete and calls_complete and not withheld,
        required_usage_complete=bool(calls)
        and all(call["required_usage_complete"] for call in calls),
    )
