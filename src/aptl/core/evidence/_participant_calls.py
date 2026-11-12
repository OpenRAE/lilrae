"""Deduplicate provider deliveries and disclose incomplete token or billing totals."""

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation


def _call_key(
    invocation: Mapping[str, object], call: Mapping[str, object]
) -> tuple[tuple[object, ...], bool]:
    """Prefer returned generation identity; disclose request-local deduplication."""
    claims = call["provider_claims"]
    generation, provider = claims.get("generation_id"), claims.get("served_provider")
    if generation and provider:
        return (invocation.get("gateway_endpoint"), provider, generation), False
    return (invocation["invocation_id"], call["request_id"]), True


def _collect_calls(
    invocations: Sequence[Mapping[str, object]],
) -> tuple[tuple[Mapping[str, object], ...], bool, bool, bool]:
    """Retain one delivery per identity while checking repeated usage claims."""
    calls: dict[tuple[object, ...], Mapping[str, object]] = {}
    consistent, uncertain, required = True, False, True
    for invocation in invocations:
        required &= invocation.get("required_usage_complete") is True
        for call in invocation["calls"]:
            key, local_identity = _call_key(invocation, call)
            uncertain |= local_identity
            previous = calls.get(key)
            if previous is not None:
                consistent &= all(
                    previous.get(field) == call.get(field)
                    for field in ("input_tokens", "output_tokens", "cost")
                )
            else:
                calls[key] = call
    return tuple(calls.values()), consistent, uncertain, required


def _token_totals(
    values: Sequence[Mapping[str, object]], field: str, complete: bool
) -> dict[str, object]:
    """Keep known counts even when membership or another count remains unknown."""
    counts = [item.get(field) for item in values]
    valid = [value for value in counts if type(value) is int and 0 <= value < 2**53]
    known = sum(valid)
    complete = complete and len(valid) == len(counts)
    return {
        f"known_{field}_subtotal": known,
        field: known if complete else None,
        f"{field}_complete": bool(complete),
    }


def _cost(item: Mapping[str, object]) -> Decimal | None:
    """Accept bounded finite optional billing without treating missing cost as zero."""
    try:
        value = item.get("cost")
        amount = Decimal(value) if type(value) in {str, int} else None
        if amount is not None and amount.is_finite() and 0 <= amount <= 10**6:
            return amount
    except InvalidOperation, ValueError:
        # Invalid optional billing remains unknown while other observations survive.
        pass
    return None


def _billing_totals(
    values: Sequence[Mapping[str, object]], complete: bool
) -> dict[str, object]:
    """Expose a known cost subtotal separately from a complete billing total."""
    costs = [amount for item in values if (amount := _cost(item)) is not None]
    subtotal = str(sum(costs, Decimal(0)))
    complete = complete and len(costs) == len(values)
    return {
        "known_cost_subtotal": subtotal,
        "cost": subtotal if complete else None,
        "currency": "USD",
        "billing_complete": bool(complete),
    }


def aggregate_model_calls(
    invocations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Deduplicate provider deliveries; retain failed attempts and unknown totals."""
    values, consistent, uncertain, required = _collect_calls(invocations)
    complete = (
        bool(invocations)
        and consistent
        and all(item.get("complete") is True for item in invocations)
    )
    return {
        "call_count": len(values) if complete else None,
        "known_call_count": len(values),
        "deduplication_uncertain": uncertain,
        "membership_complete": complete,
        "required_usage_complete": required and consistent and complete,
        **_token_totals(values, "input_tokens", complete and consistent),
        **_token_totals(values, "output_tokens", complete and consistent),
        **_billing_totals(values, complete and consistent),
    }
