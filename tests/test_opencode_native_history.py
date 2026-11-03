"""Native records prove delivery without retaining private chat or capabilities."""

from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

import pytest


def native_database(
    work, *, prompt="exact prompt\n", model="test/model", finish="stop"
):
    path = work / "data/opencode/opencode.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE session(id TEXT PRIMARY KEY);
            CREATE TABLE message(id TEXT, session_id TEXT, data TEXT, time_created INTEGER, time_updated INTEGER);
            CREATE TABLE part(id TEXT, message_id TEXT, session_id TEXT, data TEXT, time_created INTEGER, time_updated INTEGER);
        """)
        db.execute("INSERT INTO session VALUES (?)", ("ses_fixture",))
        for identifier, value in (
            (
                "msg_user",
                {
                    "role": "user",
                    "model": {"providerID": "openrouter", "modelID": model},
                },
            ),
            (
                "msg_assistant",
                {
                    "role": "assistant",
                    "providerID": "openrouter",
                    "modelID": model,
                    "time": {"completed": 30},
                },
            ),
        ):
            db.execute(
                "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
                (
                    identifier,
                    "ses_fixture",
                    json.dumps(value),
                    10 if identifier == "msg_user" else 20,
                    30,
                ),
            )
        parts = [
            ("prt_prompt", "msg_user", {"type": "text", "text": prompt}),
            (
                "prt_reasoning",
                "msg_assistant",
                {
                    "type": "reasoning",
                    "text": "private reasoning and secret-capability",
                },
            ),
            (
                "prt_tool",
                "msg_assistant",
                {"type": "tool", "state": {"input": {"token": "secret-capability"}}},
            ),
            (
                "prt_reply",
                "msg_assistant",
                {"type": "text", "text": "private completion"},
            ),
        ]
        if finish is not None:
            parts.append(
                (
                    "prt_finish",
                    "msg_assistant",
                    {
                        "type": "step-finish",
                        "reason": finish,
                        "cost": 0.125,
                        "tokens": {
                            "input": 12,
                            "output": 3,
                            "reasoning": 1,
                            "cache": {"read": 2, "write": 0},
                        },
                    },
                )
            )
        for identifier, message, value in parts:
            db.execute(
                "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
                (identifier, message, "ses_fixture", json.dumps(value), 20, 30),
            )
    return path


def observe(work, **kwargs):
    from aptl.workbench.opencode_history import read_native_history

    return read_native_history(
        work,
        expected_prompt=b"exact prompt\n",
        expected_model="openrouter/test/model",
        session_id="ses_fixture",
        **kwargs,
    )


def test_native_history_verifies_prompt_model_and_separate_step_usage(tmp_path):
    native_database(tmp_path)
    history = observe(tmp_path)
    assert history.status == "observed"
    assert history.prompt_matches is True
    assert history.session_id == "ses_fixture"
    assert history.user_message_id == "msg_user"
    assert history.recorded_model == "openrouter/test/model"
    import hashlib

    assert history.prompt_sha256 == hashlib.sha256(b"exact prompt\n").hexdigest()
    assert history.authored_placement == "native-user-text"
    (step,) = history.steps
    assert step.message_id == "msg_assistant"
    assert step.step_id == "prt_finish"
    assert (step.input_tokens, step.output_tokens, step.reasoning_tokens) == (12, 3, 1)
    assert (step.cache_read_tokens, step.cache_write_tokens) == (2, 0)
    assert step.estimated_cost == 0.125
    assert step.finish_reason == "stop"
    assert step.created_at_ms == 20
    assert step.completed_at_ms == 30
    assert "outgoing_controls" in history.unavailable_fields
    assert "provider_generation_id" in history.unavailable_fields
    history.require_fields(frozenset({"prompt_delivery", "native_steps"}))
    required_fields = frozenset({"outgoing_controls"})
    with pytest.raises(ValueError, match="unavailable"):
        history.require_fields(required_fields)
    retained = json.dumps(asdict(history))
    assert all(
        value not in retained
        for value in (
            "private completion",
            "private reasoning",
            "secret-capability",
            "exact prompt",
        )
    )


@pytest.mark.parametrize(
    "changes", [{"prompt": "peer prompt"}, {"model": "other/model"}]
)
def test_native_history_rejects_actual_delivery_mismatch(tmp_path, changes):
    native_database(tmp_path, **changes)
    history = observe(tmp_path)
    assert history.status == "invalid"
    assert history.recorded_model is None
    assert history.steps == ()


def test_native_history_retains_prompt_delivery_on_interrupted_generation(tmp_path):
    native_database(tmp_path, finish=None)
    history = observe(tmp_path)
    assert history.status == "partial"
    assert history.prompt_matches is True
    assert history.steps == ()


@pytest.mark.parametrize("column", ["message", "part"])
@pytest.mark.parametrize("value", [None, b"invalid native JSON"])
def test_native_history_rejects_non_text_json_columns(tmp_path, column, value):
    path = native_database(tmp_path)
    with sqlite3.connect(path) as db:
        if column == "message":
            db.execute("UPDATE message SET data=?", (value,))
        else:
            db.execute("UPDATE part SET data=?", (value,))
    history = observe(tmp_path)
    assert history.status == "invalid"
    assert history.steps == ()


@pytest.mark.parametrize("token_value", [None, 0, True, -1, "12"])
def test_native_usage_does_not_invent_or_coerce_counts(tmp_path, token_value):
    path = native_database(tmp_path)
    with sqlite3.connect(path) as db:
        part = json.loads(
            db.execute("SELECT data FROM part WHERE id='prt_finish'").fetchone()[0]
        )
        part["tokens"]["input"] = token_value
        db.execute("UPDATE part SET data=? WHERE id='prt_finish'", (json.dumps(part),))
    history = observe(tmp_path)
    if type(token_value) is int and token_value == 0:
        assert history.steps[0].input_tokens == 0
    elif token_value is None:
        assert history.steps[0].input_tokens is None
    else:
        assert history.status == "invalid"
        assert history.steps == ()


def test_native_history_missing_corrupt_or_uncheckpointed_is_explicit(tmp_path):
    assert observe(tmp_path).status == "missing"
    path = native_database(tmp_path)
    path.with_name("opencode.db-wal").write_bytes(b"uncheckpointed")
    assert observe(tmp_path).status == "uncheckpointed"
    path.with_name("opencode.db-wal").unlink()
    path.write_bytes(b"not a SQLite database; secret-capability")
    history = observe(tmp_path)
    assert history.status == "invalid"
    assert "secret-capability" not in repr(history)


def test_native_history_refuses_symlink_and_byte_limit(tmp_path):
    path = native_database(tmp_path)
    assert observe(tmp_path, max_bytes=1).status == "oversized"
    outside = tmp_path / "unapproved.db"
    path.rename(outside)
    path.symlink_to(outside)
    assert observe(tmp_path).status == "invalid"


def test_native_history_rejects_ambiguous_sessions(tmp_path):
    path = native_database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO session VALUES (?)", ("ses_peer",))
    assert observe(tmp_path).status == "invalid"


@pytest.mark.parametrize("failed", [False, True])
def test_executor_reduces_history_before_private_teardown(tmp_path, failed):
    from threading import Event
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from aptl.workbench.process import AgentExecutionError, ProcessResult
    from tests.opencode_fixture import synthetic_options

    class Runner:
        def run(self, argv, **kwargs):
            native_database(kwargs["cwd"], finish=None if failed else "stop")
            return ProcessResult(
                1 if failed else 0,
                b'{"type":"text","sessionID":"ses_fixture","part":{"text":"done"}}\n{"type":"step_finish","part":{"reason":"stop"}}\n',
                b"",
            )

    records = []
    active = LilraeOpenCodeExecutor(
        options=synthetic_options(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            runner=Runner(),
            evidence_sink=records.append,
        ),
        model="openrouter/test/model",
        prompt="exact prompt\n",
        timeout_seconds=30,
    )
    if failed:
        failure_cancellation = Event()
        with pytest.raises(AgentExecutionError):
            active("action", failure_cancellation)
    else:
        assert active("action", Event()) == "done"
    history = records[0].native_history
    assert history.status == ("partial" if failed else "observed")
    assert history.prompt_matches is True
    assert history.session_id == records[0].session_id
    assert not list(tmp_path.glob("lilrae-participant-*"))
    assert "secret-capability" not in repr(records)


def test_executor_refuses_mismatched_native_prompt(tmp_path):
    from threading import Event
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from aptl.workbench.process import AgentExecutionError, ProcessResult
    from tests.opencode_fixture import synthetic_options

    class Runner:
        def run(self, argv, **kwargs):
            native_database(kwargs["cwd"], prompt="other trial prompt")
            return ProcessResult(
                0,
                b'{"type":"text","sessionID":"ses_fixture","part":{"text":"done"}}\n{"type":"step_finish","part":{"reason":"stop"}}\n',
                b"",
            )

    active = LilraeOpenCodeExecutor(
        options=synthetic_options(
            executable=Path("/bin/true"), work_root=tmp_path, runner=Runner()
        ),
        model="openrouter/test/model",
        prompt="exact prompt\n",
        timeout_seconds=30,
    )
    failure_cancellation = Event()
    with pytest.raises(AgentExecutionError, match="native"):
        active("action", failure_cancellation)
    assert active.last_evidence.status == "failed"
    assert active.last_evidence.native_history.status == "invalid"


def test_required_native_history_cannot_be_silently_missing(tmp_path):
    from dataclasses import replace
    from threading import Event
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from aptl.workbench.process import AgentExecutionError
    from tests.opencode_fixture import synthetic_options
    from tests.test_lilrae_opencode import RecordingRunner

    options = synthetic_options(
        executable=Path("/bin/true"), work_root=tmp_path, runner=RecordingRunner()
    )
    active = LilraeOpenCodeExecutor(
        options=replace(options, native_history_required=True),
        model="openrouter/test/model",
        prompt="exact prompt\n",
        timeout_seconds=30,
    )
    failure_cancellation = Event()
    with pytest.raises(AgentExecutionError, match="native"):
        active("action", failure_cancellation)
    assert active.last_evidence.status == "failed"
    assert active.last_evidence.native_history.status == "missing"
