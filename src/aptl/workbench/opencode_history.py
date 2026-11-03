"""Bounded read-only reduction of the pinned OpenCode native session history."""

from __future__ import annotations

from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import sys

from aptl.core.opencode import (
    NativeHistoryObservation,
    NativeStepObservation,
)
from aptl.utils.pathsafe import (
    PathContainmentError,
    REASON_NOT_FOUND,
    open_contained_nofollow,
)
from aptl.utils.strict_json import loads_strict

_DATABASE = "data/opencode/opencode.db"
_MAX_ROWS = 4096
_MAX_VALUE_BYTES = 1_000_000
_FINISH_REASONS = frozenset(
    {"stop", "tool-calls", "length", "content-filter", "error", "other", "unknown"}
)


def _identifier(value: object, prefix: str) -> str:
    """Accept only the pinned native identifier format."""
    if not isinstance(value, str) or not re.fullmatch(
        prefix + r"_[A-Za-z0-9]{1,128}", value
    ):
        raise ValueError("invalid native identifier")
    return value


def _object(raw: str) -> dict[str, object]:
    """Decode one bounded closed native JSON object."""
    if len(raw.encode("utf-8")) > _MAX_VALUE_BYTES:
        raise ValueError("oversized native value")
    value = loads_strict(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid native object")
    return value


def _count(value: object) -> int | None:
    """Keep missing token counts distinct from reported zero."""
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError("invalid native count")
    return value


def _time(value: object) -> int:
    """Validate the native millisecond timestamp range."""
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError("invalid native time")
    return value


def _cost(value: object) -> float | None:
    """Validate a finite nonnegative native estimate without billing claims."""
    if value is None:
        return None
    if type(value) not in {int, float} or not 0 <= value <= 10**6:
        raise ValueError("invalid native estimated cost")
    return float(value)


def _step(
    message_id: str, step_id: str, data: dict[str, object], created: int, updated: int
) -> NativeStepObservation:
    """Reduce one terminal step and its separate usage categories."""
    reason = data.get("reason")
    if reason not in _FINISH_REASONS:
        raise ValueError("invalid native finish")
    tokens = data.get("tokens", {})
    if not isinstance(tokens, dict):
        raise ValueError("invalid native tokens")
    cache = tokens.get("cache", {})
    if not isinstance(cache, dict):
        raise ValueError("invalid native cache tokens")
    start, end = _time(created), _time(updated)
    if end < start:
        raise ValueError("invalid native interval")
    return NativeStepObservation(
        message_id,
        step_id,
        reason,
        start,
        end,
        _count(tokens.get("input")),
        _count(tokens.get("output")),
        _count(tokens.get("reasoning")),
        _count(cache.get("read")),
        _count(cache.get("write")),
        _cost(data.get("cost")),
    )


def _messages(
    db: sqlite3.Connection, session: str, expected_model: str
) -> tuple[dict[str, str], str]:
    """Validate message membership and the exact native model."""
    messages = db.execute(
        "SELECT id, data FROM message WHERE session_id=? ORDER BY time_created, id LIMIT ?",
        (session, _MAX_ROWS + 1),
    ).fetchall()
    if not messages or len(messages) > _MAX_ROWS:
        raise ValueError("invalid native message count")
    roles = {}
    users = []
    for identifier, raw in messages:
        identifier = _identifier(identifier, "msg")
        value = _object(raw)
        role = value.get("role")
        if role not in {"user", "assistant"} or identifier in roles:
            raise ValueError("invalid native message")
        _validate_message_model(value, role, expected_model)
        roles[identifier] = role
        if role == "user":
            users.append(identifier)
    if len(users) != 1 or roles[messages[0][0]] != "user":
        raise ValueError("ambiguous native user prompt")
    return roles, users[0]


def _read_session(
    db: sqlite3.Connection,
    expected_prompt: bytes,
    expected_model: str,
    expected_session: str | None,
) -> NativeHistoryObservation:
    """Join one native session to exact authored prompt bytes."""
    sessions = db.execute("SELECT id FROM session LIMIT 2").fetchall()
    if len(sessions) != 1:
        raise ValueError("ambiguous native session")
    session = _identifier(sessions[0][0], "ses")
    if expected_session is not None and session != expected_session:
        raise ValueError("native session mismatch")
    roles, user_message_id = _messages(db, session, expected_model)
    delivered, steps = _parts(db, session, roles)
    if delivered != expected_prompt:
        raise ValueError("native prompt mismatch")
    return NativeHistoryObservation(
        status="observed" if steps and steps[-1].finish_reason == "stop" else "partial",
        session_id=session,
        user_message_id=user_message_id,
        prompt_matches=True,
        recorded_model=expected_model,
        prompt_sha256=hashlib.sha256(delivered).hexdigest(),
        authored_placement="native-user-text",
        steps=tuple(steps),
    )


def _validate_message_model(
    value: dict[str, object], role: str, expected_model: str
) -> None:
    """Compare the recorded provider and model with the independently retained pin."""
    model = value.get("model") if role == "user" else value
    if (
        not isinstance(model, dict)
        or model.get("providerID") != "openrouter"
        or model.get("modelID") != expected_model.removeprefix("openrouter/")
    ):
        raise ValueError("native model mismatch")


def _user_text(value: dict[str, object]) -> str:
    """Accept native authored user text without implicit wrappers or other parts."""
    if value.get("type") != "text" or not isinstance(value.get("text"), str):
        raise ValueError("unexpected native user content")
    return value["text"]


def _parts(
    db: sqlite3.Connection, session: str, roles: dict[str, str]
) -> tuple[bytes, list[NativeStepObservation]]:
    """Reduce bounded part membership to prompt bytes and terminal step facts."""
    parts = db.execute(
        "SELECT id, message_id, data, time_created, time_updated "
        "FROM part WHERE session_id=? ORDER BY time_created, id LIMIT ?",
        (session, _MAX_ROWS + 1),
    ).fetchall()
    if len(parts) > _MAX_ROWS:
        raise ValueError("oversized native history")
    prompt = []
    steps = []
    seen = set()
    for identifier, message, raw, created, updated in parts:
        identifier = _identifier(identifier, "prt")
        if identifier in seen or message not in roles:
            raise ValueError("ambiguous native part")
        seen.add(identifier)
        value = _object(raw)
        if roles[message] == "user":
            prompt.append(_user_text(value))
        elif value.get("type") == "step-finish":
            steps.append(_step(message, identifier, value, created, updated))
    delivered = "".join(prompt).encode("utf-8")
    return delivered, steps


def read_native_history(
    work: Path,
    *,
    expected_prompt: bytes,
    expected_model: str,
    session_id: str | None,
    max_bytes: int = 16 * 1024 * 1024,
) -> NativeHistoryObservation:
    """Read one contained, checkpointed database; never export raw native data.

    The Linux baseline opens SQLite through the checked file descriptor.
    A nonempty WAL is not a complete immutable snapshot and is not ignored.
    All failures retain only a fixed availability code.
    """
    if sys.platform != "linux":
        return NativeHistoryObservation(status="unsupported-platform")
    try:
        observation = _contained_history(
            work, expected_prompt, expected_model, session_id, max_bytes
        )
    except PathContainmentError as exc:
        observation = NativeHistoryObservation(
            status="missing" if exc.reason == REASON_NOT_FOUND else "invalid"
        )
    except OSError, sqlite3.Error, ValueError, TypeError, KeyError:
        observation = NativeHistoryObservation(status="invalid")
    return observation


def _contained_history(
    work: Path, prompt: bytes, model: str, session: str | None, max_bytes: int
) -> NativeHistoryObservation:
    """Read only a contained checkpointed database under SQLite resource limits."""
    try:
        with open_contained_nofollow(work, _DATABASE + "-wal") as journal:
            if journal.read(1):
                return NativeHistoryObservation(status="uncheckpointed")
    except PathContainmentError as exc:
        if exc.reason != REASON_NOT_FOUND:
            raise
    with open_contained_nofollow(work, _DATABASE) as source:
        if os.fstat(source.fileno()).st_size > max_bytes:
            return NativeHistoryObservation(status="oversized")
        uri = f"file:/proc/self/fd/{source.fileno()}?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, _MAX_VALUE_BYTES)
            calls = 0

            def bounded_query() -> int:
                """Abort native queries after a bounded number of VM steps."""
                nonlocal calls
                calls += 1
                return int(calls > 1000)

            db.set_progress_handler(bounded_query, 1000)
            return _read_session(db, prompt, model, session)
