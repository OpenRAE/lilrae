"""Quote-aware shell segmentation and ordered credential substitutions."""

from __future__ import annotations

import bisect
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

# The characters that change the quote, escape, or segment state.
_SEGMENT_SPECIAL_RE = re.compile(r"[\\'\"|;&]")


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

    The scan visits only the characters that can change the state: a
    backslash escapes the next character, also inside quotes, and quotes
    toggle as in the shell. Thus the cost is linear and small on long text.
    """
    segments: list[tuple[int, int]] = []
    start = 0
    quotes = _ShellQuotes()
    next_free = 0
    for match in _SEGMENT_SPECIAL_RE.finditer(command):
        i = match.start()
        if i < next_free:
            continue
        if command[i] == "\\":
            next_free = i + 2
            continue
        if quotes.consumes(command[i]):
            continue
        advance = _separator_advance(command, i)
        if advance:
            segments.append((start, i))
            start = next_free = i + advance
    segments.append((start, len(command)))
    return segments


class _ShellQuotes:
    """Single- and double-quote state of a shell command."""

    def __init__(self) -> None:
        self.single = False
        self.double = False

    def consumes(self, ch: str) -> bool:
        """Toggle on a quote; whether ``ch`` is a quote or quoted text."""
        if ch == "'" and not self.double:
            self.single = not self.single
            return True
        if ch == '"' and not self.single:
            self.double = not self.double
            return True
        return self.single or self.double


def _separator_advance(command: str, i: int) -> int:
    """How far a top-level separator at ``i`` moves the segment start (0 = none)."""
    if command[i] in "|;":
        return 1
    return _ampersand_step(command, i)


def _segment_hits(text: str, segment_test: SegmentTest) -> bool:
    """Whether any tool-family pattern of ``segment_test`` matches ``text``."""
    tests = segment_test if isinstance(segment_test, tuple) else (segment_test,)
    return any(t.search(text) for t in tests)


def _segment_predicate(
    command: str, segment_test: SegmentTest, context: str = ""
) -> InSegPredicate:
    """Build an ``offset -> bool`` predicate over precomputed segments.

    ``segment_test`` is either a compiled regex (the segment matches if
    the regex searches successfully) or a tuple of regexes (matches if
    *any* hits — split this way to keep each regex under Sonar's
    regex-complexity threshold). ``context`` is the leading token of the
    command that ``command`` is an argument of, for example the tool of an
    argv list. When it names a tool of the family, every segment matches.
    """
    segments = _split_top_level_segments(command)
    context_hit = bool(context) and _segment_hits(context, segment_test)
    flags = [
        context_hit or _segment_hits(command[s:e], segment_test)
        for s, e in segments
    ]

    starts = [s for s, _ in segments]

    def in_flagged_segment(offset: int) -> bool:
        """Whether the offset belongs to a credential-bearing segment."""
        idx = bisect.bisect_right(starts, offset) - 1
        return idx >= 0 and offset < segments[idx][1] and flags[idx]

    return in_flagged_segment


def _unquote_options_in_credential_segments(command: str, context: str = "") -> str:
    """Strip surrounding quotes from ``'-X'`` / ``"-X"`` option tokens —
    but only inside segments that name a credential-bearing tool.

    The earlier implementation ran this pre-pass globally, which mutated
    arbitrary data (``echo '-p' hunter2`` became ``echo -p hunter2``,
    then `_redact_short_password_flag` redacted the trailing word as if
    it were a password). Scoping the strip to credential-bearing
    segments keeps the original `hydra '-p' hunter2` parity (hydra's
    segment unquotes, the per-flag matcher fires) while leaving
    non-credential text intact. ``context`` has the meaning that
    :func:`_segment_predicate` gives it.
    """
    if "'" not in command and '"' not in command:
        # Cheap fast path; most commands have no quotes.
        return command
    segments = _split_top_level_segments(command)
    context_hit = bool(context) and _segment_hits(context, _ANY_CREDENTIAL_TOOL_REGEXES)
    out_parts: list[str] = []
    last_end = 0
    for s, e in segments:
        if s > last_end:
            # Preserve the separator characters (``&&``/``||``/``;``/``|``/``&``).
            out_parts.append(command[last_end:s])
        seg = command[s:e]
        if context_hit or _segment_hits(seg, _ANY_CREDENTIAL_TOOL_REGEXES):
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
    context: str = "",
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
    ``context`` has the meaning that :func:`_segment_predicate` gives it.
    """
    out = command
    scanned: str | None = None
    in_seg: InSegPredicate = _lazy_segment_predicate("", segment_test, context)
    for pattern, factory in passes:
        # The predicate is a function of the text alone: build it again only
        # after a pass changed the text.
        if out is not scanned:
            in_seg = _lazy_segment_predicate(out, segment_test, context)
            scanned = out
        out = pattern.sub(factory(in_seg), out)
    return out


def _lazy_segment_predicate(
    command: str, segment_test: SegmentTest, context: str
) -> InSegPredicate:
    """Return :func:`_segment_predicate` built at its first call.

    Most text has no flag match, so no segment scan is necessary.
    """
    built: list[InSegPredicate] = []

    def in_seg(offset: int) -> bool:
        """Whether the offset belongs to a credential-bearing segment."""
        if not built:
            built.append(_segment_predicate(command, segment_test, context))
        return built[0](offset)

    return in_seg
