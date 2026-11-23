"""Allowlisted native usage observations and existing run-store persistence."""

from dataclasses import asdict, dataclass
import json

from aptl.workbench.process import ProcessResult
from aptl.workbench.runtime import AgentLaunch, DecisionAgentLaunch


@dataclass(frozen=True)
class AgentUsage:
    """Reported counters only; absent or invalid reports remain unknown."""

    input_tokens: int | None = None
    output_tokens: int | None = None


def _count(value: object) -> int | None:
    """Keep only nonnegative counts with exact JSON integer representation."""
    return value if type(value) is int and 0 <= value < 2**53 else None


def parse_usage(provider: str, stdout: bytes) -> AgentUsage:
    """Read Claude's result usage or Codex's final completed-turn usage."""
    usage: object = None
    try:
        events = (
            [json.loads(line) for line in stdout.decode().splitlines()]
            if provider == "codex"
            else [json.loads(stdout)]
        )
        for event in events:
            if isinstance(event, dict) and event.get("type") == (
                "turn.completed" if provider == "codex" else "result"
            ):
                usage = event.get("usage")
    except ValueError:
        return AgentUsage()
    if not isinstance(usage, dict):
        return AgentUsage()
    return AgentUsage(
        _count(usage.get("input_tokens")), _count(usage.get("output_tokens"))
    )


class AgentUsageRecorder:
    """Keep raw provider output out of the existing structured run store."""

    def __init__(self, provider: str) -> None:
        self._provider = provider

    def record(self, launch: AgentLaunch, result: ProcessResult) -> AgentUsage:
        usage = parse_usage(self._provider, result.stdout)
        configuration = (
            launch.request.configuration_result
            if isinstance(launch, DecisionAgentLaunch) and launch.request is not None
            else None
        )
        if launch.run_store is not None:
            launch.run_store.append_jsonl(
                launch.run_id,
                "workbench/usage.jsonl",
                [
                    {
                        "event": "agent_usage",
                        "provider": self._provider,
                        "requested_model": launch.model,
                        "participant_address": configuration.participant_address
                        if configuration is not None
                        else None,
                        "configuration_digest": configuration.configuration_digest
                        if configuration is not None
                        else None,
                        "served_model": None,
                        "served_provider": None,
                        "source": "native-cli-invocation-report",
                        "process_exit_code": result.returncode,
                        **asdict(usage),
                    }
                ],
            )
        return usage
