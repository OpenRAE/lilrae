"""Native tool observation counts and gaps, without study scoring."""

from collections.abc import Mapping, Sequence


def aggregate_tool_calls(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Count captured runtime action identities without interpreting study outcomes."""
    phases: dict[str, set[str]] = {}
    for row in rows:
        phase, action = row["phase"], row.get("action_instance_id")
        if isinstance(action, str):
            phases.setdefault(phase, set()).add(action)
    dispatches = phases.get("dispatched", set())
    settled = (
        phases.get("succeeded", set())
        | phases.get("failed", set())
        | phases.get("unsettled", set())
    )
    return {
        "proposed": sum(row["phase"] == "proposed" for row in rows),
        "refused": sum(row["phase"] == "refused" for row in rows),
        "admitted": len(phases.get("admitted", set())),
        "dispatched": len(dispatches),
        "succeeded": len(phases.get("succeeded", set())),
        "failed": len(phases.get("failed", set())),
        "unsettled": len(phases.get("unsettled", set())),
        "in_flight": len(dispatches - settled),
    }


def tool_sequence_complete(rows: Sequence[Mapping[str, object]]) -> bool:
    sequences: dict[str, list[int]] = {}
    actions: dict[str, set[str]] = {}
    for row in rows:
        sequences.setdefault(row["invocation_id"], []).append(row["sequence"])
        action = row.get("action_instance_id")
        if isinstance(action, str):
            actions.setdefault(row["phase"], set()).add(action)
    admitted = actions.get("admitted", set())
    dispatched = actions.get("dispatched", set())
    settled = (
        actions.get("succeeded", set())
        | actions.get("failed", set())
        | actions.get("unsettled", set())
    )
    refused = actions.get("refused", set())
    return (
        all(sorted(values) == list(range(len(values))) for values in sequences.values())
        and admitted <= dispatched | settled | refused
        and dispatched <= admitted
        and settled <= dispatched
        and dispatched <= settled
    )
