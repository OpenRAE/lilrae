"""Quote-aware shell segmentation and ordered credential substitutions."""

from __future__ import annotations

from collections.abc import Callable
import re

from ._redaction_patterns import (
    _ANY_CREDENTIAL_TOOL_REGEXES,
    _QUOTED_OPTION_TOKEN_RE,
)

InSegPredicate = Callable[[int], bool]
SubReplacer = Callable[[re.Match[str]], str]
ReplacerFactory = Callable[[InSegPredicate], SubReplacer]
SegmentTest = re.Pattern[str] | tuple[re.Pattern[str], ...]


def _advance_quote_state(state: dict[str, bool], ch: str) -> bool:
    """Update single/double-quote and escape state for one character.

    Returns ``True`` when the caller should treat this position as inside
    a quoted run / escape and therefore not a segment separator.
    """
    if state["escaped"]:
        state["escaped"] = False
    elif ch == "\\":
        state["escaped"] = True
    elif not state["in_double"] and ch == "'":
        state["in_single"] = not state["in_single"]
    elif not state["in_single"] and ch == '"':
        state["in_double"] = not state["in_double"]
    else:
        return state["in_single"] or state["in_double"]
    return True


def _ampersand_step(command: str, i: int) -> int:
    """How far past an ``&`` to advance the segment start (0 = not a separator).

    ``2>&1``, ``&>file``, ``<&3`` are redirections, not separators.
    ``&&`` advances by 2, a lone ``&`` (background) by 1.
    """
    prev = command[i - 1] if i > 0 else ""
    nxt = command[i + 1] if i + 1 < len(command) else ""
    if prev in (">", "<") or nxt == ">":
        return 0
    return 2 if nxt == "&" else 1


def _split_top_level_segments(command: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` half-open ranges for each top-level shell segment.

    Quote- and escape-aware. Multi-character separators (``&&``, ``||``)
    are consumed atomically — the loop skips past the second character
    so the splitter never emits a zero-width range. Any subsequent
    reconstruction (``_unquote_options_in_credential_segments``) can
    re-join the slices with the original separator characters intact;
    the previous ``for ... enumerate`` loop revisited the second ``&``,
    which the reconstructor would emit as a stray ``&`` between segments.
    """
    segments: list[tuple[int, int]] = []
    start = 0
    state: dict[str, bool] = {"in_single": False, "in_double": False, "escaped": False}
    n = len(command)
    i = 0
    while i < n:
        ch = command[i]
        if _advance_quote_state(state, ch):
            i += 1
            continue
        if ch in ("|", ";"):
            segments.append((start, i))
            start = i + 1
            i += 1
            continue
        if ch == "&":
            advance = _ampersand_step(command, i)
            if advance > 0:
                segments.append((start, i))
                start = i + advance
                i += advance
                continue
        i += 1
    segments.append((start, n))
    return segments


def _segment_predicate(
    command: str, segment_test: SegmentTest
) -> InSegPredicate:
    """Build an ``offset -> bool`` predicate over precomputed segments.

    ``segment_test`` is either a compiled regex (the segment matches if
    the regex searches successfully) or a tuple of regexes (matches if
    *any* hits — split this way to keep each regex under Sonar's
    regex-complexity threshold).
    """
    segments = _split_top_level_segments(command)
    tests = segment_test if isinstance(segment_test, tuple) else (segment_test,)

    def hit(text: str) -> bool:
        """Whether any tool-family pattern matches the segment."""
        return any(t.search(text) for t in tests)

    flags = [hit(command[s:e]) for (s, e) in segments]

    def in_flagged_segment(offset: int) -> bool:
        """Whether the offset belongs to a credential-bearing segment."""
        for idx, (s, e) in enumerate(segments):
            if s <= offset < e:
                return flags[idx]
        return False

    return in_flagged_segment


def _unquote_options_in_credential_segments(command: str) -> str:
    """Strip surrounding quotes from ``'-X'`` / ``"-X"`` option tokens —
    but only inside segments that name a credential-bearing tool.

    The earlier implementation ran this pre-pass globally, which mutated
    arbitrary data (``echo '-p' hunter2`` became ``echo -p hunter2``,
    then `_redact_short_password_flag` redacted the trailing word as if
    it were a password). Scoping the strip to credential-bearing
    segments keeps the original `hydra '-p' hunter2` parity (hydra's
    segment unquotes, the per-flag matcher fires) while leaving
    non-credential text intact.
    """
    if "'" not in command and '"' not in command:
        # Cheap fast path; most commands have no quotes.
        return command
    segments = _split_top_level_segments(command)
    out_parts: list[str] = []
    last_end = 0
    for s, e in segments:
        if s > last_end:
            # Preserve the separator characters (``&&``/``||``/``;``/``|``/``&``).
            out_parts.append(command[last_end:s])
        seg = command[s:e]
        if any(t.search(seg) for t in _ANY_CREDENTIAL_TOOL_REGEXES):
            seg = _QUOTED_OPTION_TOKEN_RE.sub(r"\2", seg)
        out_parts.append(seg)
        last_end = e
    if last_end < len(command):
        out_parts.append(command[last_end:])
    return "".join(out_parts)


def _segment_aware_sub_chain(
    command: str,
    segment_test: SegmentTest,
    passes: list[tuple[re.Pattern[str], ReplacerFactory]],
) -> str:
    """Run a sequence of segment-aware substitutions safely.

    Each pass recomputes the segment predicate against the *current*
    string before invoking ``re.sub`` — the prior approach (compute
    segments once on the input, then run six sequential ``.sub()`` calls
    on a mutating string) reused stale offsets after replacements
    shifted character positions, which could mis-classify later matches
    into the wrong segment and over-redact things like ``nmap -p 22``
    after a long quoted hydra password contracted the string. Recompute
    per pass; ``re.sub``'s own callback offsets are consistent within a
    single ``.sub()`` call, so this is sufficient.

    ``passes`` is a list of ``(pattern, replacer_factory)`` where
    ``replacer_factory(in_seg)`` returns the ``re.sub`` callback.
    """
    out = command
    for pattern, factory in passes:
        in_seg = _segment_predicate(out, segment_test)
        out = pattern.sub(factory(in_seg), out)
    return out
