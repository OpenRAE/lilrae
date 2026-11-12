"""Shared secret redaction for serialization boundaries (ADR-012 / ADR-029).

Run artifacts are not credential stores; redact before persistence.
Mirror changes in mcp/aptl-mcp-common/src/redaction.ts and run both languages'
redaction tests, including the shared parity corpus.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ._redaction_patterns import (
    REDACTED,
    _AUTHORIZATION_RE,
    _BARE_BEARER_RE,
    _BASIC_AUTH_SHORT_TOOLS_REGEXES,
    _CLI_FLAG_RE,
    _CLI_FLAG_TOKEN_RE,
    _COOKIE_HEADER_RE,
    _CREDENTIAL_TOOL_REGEXES,
    _HASH_TOOLS_RE,
    _LDAP_TOOL_RE,
    _redact_pem_blocks,
    _SENSITIVE_KV_RE,
    _URL_USERINFO_RE,
    _redact_authorization,
)

from ._redaction_grants import erase_granted_secrets

from ._redaction_shell import (
    _basic_auth_value_is_credential,
    _redact_command_flags,
)

# Defense-in-depth bounds for the redactor itself (issue #386, ARCH-386-01).
# These cap worst-case work at the secret boundary so a hostile or
# pathological artifact cannot turn redaction into a denial-of-service or a
# fail-open crash. Both bounds fail CLOSED (over-redact, never leak), matching
# the ADR-012 guardrail. Mirror any change in ``redaction.ts``.
#
# ``_MAX_SCAN_LEN`` bounds the polynomial-backtracking command-flag passes:
# the ``--<word>*<sensitive>`` flag matcher and the per-segment shell scanners
# backtrack ~O(n^2) on long flag-like tokens. Strings longer than this skip
# those passes (the linear key/value/header/PEM/bearer/URL passes still run),
# so CPU stays bounded. 64 KiB is far above any real command line while keeping
# the worst case trivial.
_MAX_SCAN_LEN = 64 * 1024
# ``_MAX_DEPTH`` bounds recursion through nested dicts / lists / JSON-in-strings
# so a deeply nested artifact collapses to a bounded marker instead of raising
# ``RecursionError`` (a fail-OPEN crash at the serialization boundary). Kept
# well under ``sys.getrecursionlimit()`` accounting for ~3 frames per level.
_MAX_DEPTH = 100

# OBS-003 experimenter opt-out. The toggle is NOT consulted by the
# shared :func:`redact` primitive — that would disable redaction at
# every serialization boundary in the project (OTel/Tempo spans,
# `LocalRunStore` JSON/JSONL writes, snapshot DTOs, stderr OCSF
# lines, CLI/API JSON), giving any lab/observability user with
# Tempo/Grafana access the ability to read raw control-plane
# secrets the moment an experimenter flips the env var (codex
# pre-push cycle 3 finding-9 — class category: "Global redact()
# identity bypass affecting every serialization boundary that
# imports the shared redactor"). Instead, the toggle is consulted
# ONLY by the local per-run capture sink wrappers
# (`mcp-red/src/capture.ts` `captureToolCall`,
# `mcp-red/src/logger.ts` `localOcsfJsonlSink`) and any future
# experimental sink that explicitly opts in via the documented
# `experiment_no_redact_active()` helper. See ADR-033's
# "Secret-handling" Security Layers entry for the boundary contract.
_EXPERIMENT_NO_REDACT_ENV = "APTL_EXPERIMENT_NO_REDACT"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def experiment_no_redact_active() -> bool:
    """Read the OBS-003 local capture opt-out; shared redact() never uses it.

    Only experimental sink wrappers may consult this flag. Control-plane
    serialization always redacts, including under this opt-out.
    """
    return os.environ.get(_EXPERIMENT_NO_REDACT_ENV, "").strip().lower() in _TRUTHY


# Substring tokens that mark a key as carrying credential material. Match
# is case-insensitive substring against the *full key name* so a field like
# ``ssl_authorization_header`` is also caught. ``pass`` subsumes
# ``password``/``passwd``/``passphrase``; ``session`` covers replayable
# session identifiers (Wazuh session_id, etc.). False-positive matches on
# unrelated tokens like ``passport`` are an acceptable cost — the ADR-012
# guardrail prefers over-redaction over leak.
_SENSITIVE_TOKENS: tuple[str, ...] = (
    "pass",
    "secret",
    "token",
    "credential",  # also matches "credentials"
    "authorization",
    "cookie",
    "jwt",
    "bearer",
    "api_key",
    "apikey",
    "key",  # broad — see allowlist below
    "session",
    # Compose's service fingerprint includes resolved environment credentials.
    "com.docker.compose.config-hash",
)

# Field names that look sensitive (contain "key") but legitimately hold a
# path or other public reference, not key material. Tightened to names
# that are unambiguously paths/files: bare ``ssh_key`` could mean the
# private key material itself, so it is intentionally NOT in the
# allowlist.
_SAFE_KEY_NAMES: frozenset[str] = frozenset(
    {
        "key_path",
        "key_file",
        "keypath",
        "keyfile",
        "ssh_key_path",
        "ssh_keyfile",
        "ssh_key_file",
        "public_key",
        "publickey",
        # Boolean validation/qualification outcome. The exact-name allowlist
        # does not exempt compound credential keys containing ``pass``.
        "passed",
    }
)


def _is_sensitive_key(name: str) -> bool:
    lower = name.lower()
    if lower in _SAFE_KEY_NAMES:
        return False
    return any(token in lower for token in _SENSITIVE_TOKENS)


def is_sensitive_key(key: str) -> bool:
    """Public yes/no predicate: does ``redact()`` treat ``key`` as a
    sensitive dict key? This conservative key-only classification does not
    apply the value-aware exceptions for public model counts or scope labels.

    This is a thin public wrapper around the exact same
    ``_is_sensitive_key``/``_SENSITIVE_TOKENS``/``_SAFE_KEY_NAMES`` table
    :func:`redact` uses internally for dict keys — ADR-047 "Secret
    handling" requires reusing this classification (e.g. to validate an
    experiment parameter *name* before it is ever used to build a plan)
    rather than copying the token table into a second checker. Keep
    ``tests/test_redaction.py``'s parity assertions passing when either
    changes.
    """
    return _is_sensitive_key(key)


def _public_count(value: object) -> bool:
    """Use JSON integer semantics, including finite integral JSON numbers."""
    return type(value) in (int, float) and 0 <= value < 2**53 and value == int(value)


def _public_count_default(value: object) -> bool:
    """Admit only a typed literal count as a declaration default."""
    return (
        isinstance(value, dict)
        and value.get("kind") == "literal"
        and _public_count(value.get("value"))
    )


def _count_declaration(name: str, value: dict[str, object]) -> bool:
    """Recognize the closed native integer declaration shape."""
    allowed = {
        "target_id",
        "value_type",
        "allowed_value_kinds",
        "sensitivity",
        "aliases",
        "default",
    }
    return (
        set(value) <= allowed
        and value.get("target_id") == name
        and value.get("value_type") == "integer"
        and value.get("allowed_value_kinds") == ["literal"]
        and value.get("sensitivity") in ("public", "internal")
        and ("default" not in value or _public_count_default(value["default"]))
    )


#: OpenCode's per-call usage record: integer counts, with cache read and write counts.
_OPENCODE_USAGE_COUNTS = frozenset({"input", "output", "reasoning", "total"})


def _opencode_usage(value: object) -> bool:
    """Recognize OpenCode's closed per-call ``tokens`` record of public counts."""
    if not isinstance(value, dict) or not set(value) <= _OPENCODE_USAGE_COUNTS | {"cache"}:
        return False
    cache = value.get("cache", {})
    return (
        all(_public_count(value[key]) for key in value if key != "cache")
        and isinstance(cache, dict)
        and set(cache) <= {"read", "write"}
        and all(_public_count(count) for count in cache.values())
    )


def _safe_model_count(name: str, value: object) -> bool:
    """Preserve only typed public counts and closed integer target declarations."""
    if name in {"input_tokens_complete", "output_tokens_complete"}:
        return type(value) is bool
    if name == "tokens":
        return _opencode_usage(value)
    return name in {
        "prompt_tokens",
        "output_tokens",
        "completion_tokens",
        "max_tokens",
        "cache_write_tokens",
        "effective_token_limit",
        "reasoning_tokens",
        "input_tokens",
        "total_tokens",
        "cache_read_tokens",
        "cached_tokens",
        "max_completion_tokens",
        "known_output_tokens_subtotal",
        "known_input_tokens_subtotal",
        "max_output_tokens",
    } and (
        value is None
        or _public_count(value)
        or isinstance(value, dict)
        and _count_declaration(name, value)
    )


def _redact_string(value: str, depth: int = 0) -> str:
    """Redact inline credentials from a plain string.

    A JSON-encoded payload is parsed and recursively redacted (carrying
    ``depth`` so the recursion stays bounded); otherwise the string is scanned
    by the linear key/value/header passes plus the length-gated command-flag
    passes.
    """
    # Try JSON.parse first — payloads like '{"password":"x"}' and the MCP
    # `content[].text` envelope (which wraps the real result in a JSON
    # string) need to be parsed, recursively redacted, and re-serialized.
    stripped = value.lstrip()
    if stripped and stripped[0] in "{[":
        try:
            parsed = json.loads(value)
        except ValueError:  # JSONDecodeError is a ValueError subclass
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(_redact(parsed, depth + 1), separators=(",", ":"))
    # Linear, single-quantifier passes — ReDoS-safe at any input length.
    # PEM blocks first so the markers stay verbatim (the inner key bytes
    # contain `=`/`/` characters that other patterns would otherwise see
    # as `key=value`). The quote-strip pre-pass that USED to live here
    # was a global rewrite and corrupted non-option text like
    # ``echo '-p' hunter2``; it now lives inside ``_redact_command_flags``
    # behind a segment-scoped tool gate.
    out = _redact_pem_blocks(value)
    out = _AUTHORIZATION_RE.sub(_redact_authorization, out)
    # Cookie before SENSITIVE_KV so the full header body is masked in one
    # pass (otherwise SENSITIVE_KV stops at `;` and leaves later segments).
    out = _COOKIE_HEADER_RE.sub(rf"\1{REDACTED}\3", out)
    out = _SENSITIVE_KV_RE.sub(rf"\1{REDACTED}\3", out)
    out = _BARE_BEARER_RE.sub(rf"\1{REDACTED}", out)
    out = _URL_USERINFO_RE.sub(rf"\1{REDACTED}\2", out)
    # Polynomial-backtracking passes (the `--<word>*<sensitive>` long-flag
    # matcher and the tool-context-aware short-flag chain) are bounded by
    # length to cap worst-case CPU at the secret boundary (ARCH-386-01).
    # Oversized strings skip them; the linear passes above already masked the
    # key/value/header/PEM/bearer/URL secret shapes. Run last so the simpler
    # kv/flag patterns have first claim on overlapping shapes.
    if len(out) <= _MAX_SCAN_LEN:
        out = _CLI_FLAG_RE.sub(rf"\1{REDACTED}", out)
        out = _redact_command_flags(out)
    return out


def _argv_credential_modes(leading: str) -> dict[str, bool]:
    """Classify an argv leading token by which credential-flag families
    apply. Empty / unknown returns all-False (the array is not treated
    as an argv for short-flag purposes)."""
    return {
        "cred": any(t.search(leading) for t in _CREDENTIAL_TOOL_REGEXES),
        "hash": bool(_HASH_TOOLS_RE.search(leading)),
        "ldap": bool(_LDAP_TOOL_RE.search(leading)),
        "basic": any(t.search(leading) for t in _BASIC_AUTH_SHORT_TOOLS_REGEXES),
    }


# Mode → (set of short flags it owns) → does the value need a content gate?
# Keeping this as data instead of an if/elif chain keeps
# ``_argv_short_flag_skip_indices`` under the cognitive-complexity ceiling.
_ARGV_SHORT_FLAG_RULES: tuple[tuple[str, frozenset[str], bool], ...] = (
    ("cred", frozenset({"-p"}), False),
    ("hash", frozenset({"-H"}), False),
    ("ldap", frozenset({"-w"}), False),
    # Basic-auth `-u`/`-U` keeps the same content gate as the string-mode
    # redactor: bare usernames stay visible, only credential pairs mask.
    ("basic", frozenset({"-u", "-U"}), True),
)


def _is_argv_short_flag_target(flag: str, value: str, modes: dict[str, bool]) -> bool:
    """Decide whether ``value`` (the element following ``flag``) should be
    redacted as a short-flag credential value, per ``modes``."""
    for mode, flags, content_gated in _ARGV_SHORT_FLAG_RULES:
        if not modes[mode] or flag not in flags:
            continue
        if content_gated:
            return _basic_auth_value_is_credential(value)
        return True
    return False


def _argv_short_flag_skip_indices(items: list, modes: dict[str, bool]) -> set[int]:
    """Indices in ``items`` whose value should be redacted as a short-flag
    credential, given the modes derived from the argv leading token.

    Mirrors the per-segment string-mode short-flag rules — ``-p`` for
    credential tools, ``-H`` for hash tools, ``-w`` for LDAP tools,
    ``-u``/``-U`` for basic-auth tools (with the bare-username carve-out).
    """
    skip: set[int] = set()
    if not any(modes.values()):
        return skip
    for i in range(len(items) - 1):
        flag = items[i]
        value = items[i + 1]
        if not isinstance(flag, str) or not isinstance(value, str):
            continue
        if _is_argv_short_flag_target(flag, value, modes):
            skip.add(i + 1)
    return skip


def _argv_leading_modes(items_list: list[Any]) -> dict[str, bool]:
    """Credential-flag modes implied by the argv's leading token.

    When the first element names a credential-family tool, the short-flag
    redactors apply to the array's values; otherwise all modes are off.
    """
    leading = items_list[0] if items_list and isinstance(items_list[0], str) else ""
    if not leading:
        return {"cred": False, "hash": False, "ldap": False, "basic": False}
    return _argv_credential_modes(leading)


def _is_long_flag_value_pair(item: object, idx: int, items_list: list[Any]) -> bool:
    """True when ``item`` is a sensitive long flag (``--password``) whose
    following element is a string value that should be redacted as its value."""
    return (
        isinstance(item, str)
        and bool(_CLI_FLAG_TOKEN_RE.match(item))
        and idx + 1 < len(items_list)
        and isinstance(items_list[idx + 1], str)
    )


def _redact_list(items: list[Any] | tuple[Any, ...], depth: int = 0) -> list[Any]:
    """Redact each element of a list/tuple, with argv-aware short-flag handling."""
    # Argv-shape detection: when the leading token is a credential-family
    # tool, mark indices whose values should be redacted as short-flag
    # credentials (`-p`/`-H`/`-w`/`-u`/`-U`). Without this, a structured
    # ``args = ["hydra", "-p", "hunter2", ...]`` payload bypasses the
    # short-flag redactors that only run on scalar command strings
    # (ADR-029 / codex review cycle 3, finding 2).
    out: list[Any] = []
    skip_next = False
    items_list = list(items)
    modes = _argv_leading_modes(items_list)
    short_flag_skip = _argv_short_flag_skip_indices(items_list, modes)
    for idx, item in enumerate(items_list):
        if skip_next:
            out.append(REDACTED)
            skip_next = False
            continue
        if idx in short_flag_skip:
            out.append(REDACTED)
            continue
        out.append(_redact(item, depth + 1))
        # Pair-form CLI args: ["--password", "hunter2"]. If this string is a
        # long-flag whose name is sensitive AND the next element is a plain
        # string, redact the next element as the value-of-flag.
        if _is_long_flag_value_pair(item, idx, items_list):
            skip_next = True
    return out


def redact(value: Any) -> Any:
    """Return a JSON-serialization-safe copy of ``value``.

    Recurses through dicts, lists, and tuples (tuples normalize to lists
    so the result is JSON-compatible). Replaces values whose containing
    key is sensitive with the marker ``[REDACTED]``. String values are
    scanned for embedded credentials: JSON-encoded payloads are parsed
    and recursively redacted; plain-text payloads are scanned for inline
    ``Authorization:``, ``Bearer``, ``<sensitive_key>=value``,
    ``--<sensitive_key> value``, and the command-line credential forms
    (short ``-p`` passwords, ``-H`` NTLM hashes, ``-w`` LDAP bind
    passwords, ``--user``/``-u``/``-U`` Basic-auth and Samba
    ``user%pass``, impacket positional ``user:pass@host``). List
    traversal also catches ``["--password", "hunter2"]`` pair-form CLI
    args.

    Pure: never mutates the input.

    Does NOT consult ``APTL_EXPERIMENT_NO_REDACT`` (codex pre-push
    cycle 3 finding-9). The experiment toggle is scoped to the local
    per-run capture sinks only; callers that want experimental-record
    semantics check :func:`experiment_no_redact_active` themselves
    before invoking ``redact``. This keeps OTel/Tempo, runstore,
    snapshot, and stderr boundaries redacted at all times regardless
    of the toggle.

    Bounded against pathological input (ARCH-386-01): recursion is depth-
    capped (``_MAX_DEPTH``) and fails CLOSED — a structure deeper than the
    bound collapses to ``[REDACTED]`` rather than raising ``RecursionError``.
    """
    return _redact(value, 0)


def redact_granted_secrets(value: object, secrets: tuple[str, ...]) -> object:
    """Remove explicitly granted values, then apply the ordinary shared policy.

    This does not discover credentials or consult the environment. Callers
    supply only their existing grants. JSON-in-string values get the same
    treatment as structured values, including escaped credential strings.
    """
    return redact(erase_granted_secrets(value, secrets, _MAX_DEPTH))


def is_secret_shaped_value(value: object) -> bool:
    """Return whether the shared recursive redactor changes this value.

    Uses the same transform, including nested sensitive keys and depth bounds.
    Bytes are decoded just as redact() decodes them before comparison.
    Used to refuse secret-shaped executable inputs before persistence (ADR-047).
    """
    baseline: object = (
        bytes(value).decode("utf-8", "replace")
        if isinstance(value, (bytes, bytearray))
        else value
    )
    return _redact(value, 0) != baseline


def _redact_scalar(value: object, depth: int) -> object:
    """Redact a non-container value.

    ``bytes``/``bytearray`` are not JSON-serializable and may carry secret
    material, so they are decoded and scanned as strings (ARCH-386-01 /
    redact-03) — previously they fell through unredacted. Strings are scanned
    for inline credentials; every other scalar passes through unchanged.
    """
    if isinstance(value, (bytes, bytearray)):
        return _redact_string(bytes(value).decode("utf-8", "replace"), depth)
    if isinstance(value, str):
        return _redact_string(value, depth)
    return value


def _redact(value: object, depth: int) -> object:
    """Depth-bounded recursive core of :func:`redact`.

    ``depth`` counts container/JSON nesting levels. At ``_MAX_DEPTH`` the
    subtree is replaced by the marker (fail-closed) instead of recursing into
    a ``RecursionError``.
    """
    if depth >= _MAX_DEPTH:
        return REDACTED
    if isinstance(value, dict):
        return {
            k: REDACTED
            if _is_sensitive_key(str(k))
            and not _safe_model_count(str(k), v)
            and not _safe_authorization_scope(str(k), v)
            else _redact(v, depth + 1)
            for k, v in value.items()
        }
    return (
        _redact_list(value, depth)
        if isinstance(value, (list, tuple))
        else _redact_scalar(value, depth)
    )


def _safe_authorization_scope(name: str, value: object) -> bool:
    """Recognize permission labels; their values still receive inline masking."""
    return (
        name.lower() == "authorization_scope"
        and isinstance(value, (list, tuple))
        and all(isinstance(label, str) for label in value)
    )
