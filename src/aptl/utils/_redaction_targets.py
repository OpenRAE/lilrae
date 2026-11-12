"""Linear matcher for impacket positional ``user:password@host`` targets.

It finds the matches of these patterns, in the order that ``re.sub`` finds
them::

    (?<![\\w\\\\/.:@-])([\\w\\\\/.-]+):"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"@([\\w.-]+)(?=\\s|$|[;|&])
    (?<![\\w\\\\/.:@-])([\\w\\\\/.-]+):'([^'\\\\]*(?:\\\\.[^'\\\\]*)*)'@([\\w.-]+)(?=\\s|$|[;|&])
    (?<![\\w\\\\/.:@-])([\\w\\\\/.-]+):((?:\\\\.|[^\\\\@\\s])+)@([\\w.-]+)(?=\\s|$|[;|&])

The regex engine scanned the value again from each candidate start, which is
quadratic on text such as ``u:x!u:x!...``. Each part of a target here has one
possible extent, so the scan keeps the end of each value it has found and
stays linear. Mirror any change in ``redaction-targets.ts``.
"""

from __future__ import annotations

from collections.abc import Callable
import re

# A whole run of user characters, then a colon. The lookbehind keeps each run
# to one attempt, so the scan is linear.
_USER_RUN_RE = re.compile(r"(?<![\w\\/.-])[\w\\/.-]+:")


def _is_word(ch: str) -> bool:
    """Python ``\\w`` for a str pattern."""
    return ch.isalnum() or ch == "_"


def _is_host(ch: str) -> bool:
    return _is_word(ch) or ch in ".-"


def _ends_target(text: str, index: int) -> bool:
    """The lookahead ``(?=\\s|$|[;|&])`` after the host."""
    return index == len(text) or text[index].isspace() or text[index] in ";|&"


class _TargetMatch:
    """The parts of ``re.Match`` that the redaction replacers read."""

    def __init__(self, text: str, spans: tuple[tuple[int, int], ...]) -> None:
        self._text = text
        self._spans = spans

    def start(self) -> int:
        return self._spans[0][0]

    def end(self) -> int:
        return self._spans[0][1]

    def group(self, index: int = 0) -> str:
        start, end = self._spans[index]
        return self._text[start:end]


class ImpacketTargetPattern:
    """One value form of an impacket positional target: ``"``, ``'``, or bare."""

    def __init__(self, quote: str) -> None:
        self._quote = quote

    def sub(self, repl: Callable[[_TargetMatch], str], text: str) -> str:
        """Replace each match as ``re.Pattern.sub`` with a callable does."""
        parts: list[str] = []
        cursor = 0
        for match in self._matches(text):
            parts.append(text[cursor : match.start()])
            parts.append(repl(match))
            cursor = match.end()
        parts.append(text[cursor:])
        return "".join(parts)

    def _matches(self, text: str) -> list[_TargetMatch]:
        matches: list[_TargetMatch] = []
        ends: dict[int, int] = {}
        cursor = 0
        # A target starts where a run of user characters starts, and a colon
        # ends the run. The lookbehind of the former regex also rejects a
        # start after ``:`` or ``@``.
        for candidate in _USER_RUN_RE.finditer(text):
            start = candidate.start()
            if start < cursor or (start and text[start - 1] in ":@"):
                continue
            match = self._match_at(text, start, candidate.end() - 1, ends)
            if match is not None:
                matches.append(match)
                cursor = match.end()
        return matches

    def _match_at(
        self, text: str, start: int, user_end: int, ends: dict[int, int]
    ) -> _TargetMatch | None:
        if user_end >= len(text) or text[user_end] != ":":
            return None
        if self._quote:
            value_start = user_end + 2
            if text[user_end + 1 : value_start] != self._quote:
                return None
            value_end = self._value_end(text, value_start, ends)
            if value_end < 0:
                return None
            at = value_end + 1
        else:
            value_start = user_end + 1
            value_end = self._value_end(text, value_start, ends)
            if value_end == value_start:
                return None
            at = value_end
        if text[at : at + 1] != "@":
            return None
        host_end = at + 1
        while host_end < len(text) and _is_host(text[host_end]):
            host_end += 1
        if host_end == at + 1 or not _ends_target(text, host_end):
            return None
        spans = ((start, host_end), (start, user_end), (value_start, value_end), (at + 1, host_end))
        return _TargetMatch(text, spans)

    def _value_end(self, text: str, start: int, ends: dict[int, int]) -> int:
        """Return where the value that starts at ``start`` stops.

        A quoted value stops at its closing quote, or at -1 when it has none.
        A bare value stops before ``@``, white space, or a backslash with no
        escaped character. ``ends`` keeps each result, so that a later
        candidate does not scan the same characters again.
        """
        path: list[int] = []
        index = start
        while index not in ends:
            step = self._step(text, index)
            if step <= 0:
                ends[index] = index if step == 0 else -1
                break
            path.append(index)
            index += step
        for visited in path:
            ends[visited] = ends[index]
        return ends[index]

    def _step(self, text: str, index: int) -> int:
        """Characters that one value unit at ``index`` holds; 0 stops, -1 fails."""
        if index >= len(text):
            return -1 if self._quote else 0
        ch = text[index]
        if ch == "\\":
            if index + 1 < len(text) and text[index + 1] != "\n":
                return 2
            return -1 if self._quote else 0
        if self._quote:
            return 0 if ch == self._quote else 1
        return 0 if ch == "@" or ch.isspace() else 1
