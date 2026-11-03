"""Reported native token counts survive execution and the shared run store."""

import json

import pytest

from aptl.core.runstore import LocalRunStore
from aptl.workbench.agent import ClaudeCodeManagedAgentAdapter
from aptl.workbench.codex_agent import CodexManagedAgentAdapter
from aptl.workbench.process import ProcessResult
from aptl.workbench.runtime import DecisionAgentLaunch
from tests.test_participant_workbench_adapter import _executable, _selection_schema


@pytest.mark.parametrize("provider", ["claude", "codex"])
@pytest.mark.parametrize(
    "count,expected",
    [(12, 12), (0, 0), (None, None), (-1, None), (True, None), ("private-key", None)],
)
def test_reported_usage_survives_adapter_and_storage(
    tmp_path, provider, count, expected
):
    def output(value):
        usage = {
            "input_tokens": value,
            "output_tokens": value,
            "credential": "must-not-persist",
        }
        if provider == "claude":
            return json.dumps(
                {
                    "type": "result",
                    "is_error": False,
                    "result": "decision",
                    "usage": usage,
                }
            ).encode()
        return (
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "decision"},
                }
            )
            + "\n"
            + json.dumps({"type": "turn.completed", "usage": usage})
        ).encode()

    class Runner:
        def __init__(self):
            self.value = count

        def run(self, *args, **kwargs):
            return ProcessResult(0, output(self.value), b"")

    runner = Runner()
    store = LocalRunStore(tmp_path / "runs")
    factory = (
        ClaudeCodeManagedAgentAdapter
        if provider == "claude"
        else CodexManagedAgentAdapter
    )
    kwargs = {f"{provider}_executable": _executable(tmp_path / provider)}
    adapter = factory(
        **kwargs, work_dir=tmp_path / "work", runner=runner, run_store=store
    )
    handle = adapter.launch(
        DecisionAgentLaunch(
            provider=provider,
            model="claude-sonnet-5-5" if provider == "claude" else "gpt-5.2-codex",
            run_id="usage-run",
        ),
        {
            "ANTHROPIC_API_KEY"
            if provider == "claude"
            else "CODEX_API_KEY": "private-fixture-key"
        },
    )
    adapter.list_tools(handle)
    assert (
        adapter.respond(handle, "choose", response_schema=_selection_schema(1))
        == "decision"
    )
    assert adapter.usage(handle).input_tokens == expected
    assert adapter.usage(handle).output_tokens == expected
    # A later response without usage must not reuse the previous observation.
    runner.value = None
    adapter.respond(handle, "choose again", response_schema=_selection_schema(1))
    adapter.close(handle)
    records = [
        json.loads(line)
        for line in (store.get_run_path("usage-run") / "workbench/usage.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(records) == 2
    assert records[0]["input_tokens"] == records[0]["output_tokens"] == expected
    assert records[1]["input_tokens"] is records[1]["output_tokens"] is None
    assert records[0]["served_model"] is records[0]["served_provider"] is None
    assert "private" not in json.dumps(records)
    assert "must-not-persist" not in json.dumps(records)
