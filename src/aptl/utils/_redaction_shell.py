"""Shell-segment-aware credential redaction; no recursive serialization.

Keep replacement order and tool gates in parity with TypeScript.
"""

from __future__ import annotations

import re

from ._redaction_patterns import (
    REDACTED,
    _ANY_CREDENTIAL_TOOL_REGEXES,
    _BASIC_AUTH_SHORT_TOOLS_REGEXES,
    _BASIC_AUTH_USER_ATTACHED_DQUOTE,
    _BASIC_AUTH_USER_ATTACHED_SQUOTE,
    _BASIC_AUTH_USER_ATTACHED_UNQUOTED,
    _BASIC_AUTH_USER_DQUOTE,
    _BASIC_AUTH_USER_SQUOTE,
    _BASIC_AUTH_USER_UNQUOTED,
    _CREDENTIAL_TOOL_REGEXES,
    _HASH_TOOLS_RE,
    _IMPACKET_POSITIONAL_BARE,
    _IMPACKET_POSITIONAL_DQUOTE,
    _IMPACKET_POSITIONAL_SQUOTE,
    _IMPACKET_TOOL_REGEXES,
    _LDAP_TOOL_RE,
    _LDAP_W_ATTACHED_DQUOTE,
    _LDAP_W_ATTACHED_SQUOTE,
    _LDAP_W_ATTACHED_UNQUOTED,
    _LDAP_W_DQUOTE,
    _LDAP_W_SQUOTE,
    _LDAP_W_UNQUOTED,
    _NTLM_HASHES_DQUOTE,
    _NTLM_HASHES_SQUOTE,
    _NTLM_HASHES_UNQUOTED,
    _NTLM_HASH_ATTACHED_DQUOTE,
    _NTLM_HASH_ATTACHED_SQUOTE,
    _NTLM_HASH_ATTACHED_UNQUOTED,
    _NTLM_HASH_DQUOTE,
    _NTLM_HASH_SQUOTE,
    _NTLM_HASH_UNQUOTED,
    _PORT_LIKE_RE,
    _QUOTED_OPTION_TOKEN_RE,
    _SHORT_P_ATTACHED_DQUOTE,
    _SHORT_P_ATTACHED_SQUOTE,
    _SHORT_P_ATTACHED_UNQUOTED,
    _SHORT_P_DQUOTE,
    _SHORT_P_SQUOTE,
    _SHORT_P_UNQUOTED,
    _URL_PREFIX_RE,
)

# --------------------------------------------------------------------------
# Command-line credential forms (mirrors redaction.ts).
#
# Some credential shapes can't be matched by a key/value pattern alone
# because the same flag means different things to different tools — `-p`
# is a port to nmap but a password to hydra; `-H` is an HTTP header to
# curl but an NTLM hash to crackmapexec; `-w` is a wordlist to hydra but
# an LDAP bind password to ldapsearch. So these are scoped per shell
# segment: split the command on top-level `&&`/`||`/`;`/`|`/`&`, then
# redact a flag's value only when the segment containing it names a tool
# for which the flag carries a secret.
# --------------------------------------------------------------------------


def _advance_quote_state(state: dict[str, bool], ch: str) -> bool:
    """Update single/double-quote and escape state for one character.

    Returns ``True`` when the caller should treat this position as inside
    a quoted run / escape and therefore not a segment separator.
    """
    if state["escaped"]:
        state["escaped"] = False
        return True
    if ch == "\\":
        state["escaped"] = True
        return True
    if not state["in_double"] and ch == "'":
        state["in_single"] = not state["in_single"]
        return True
    if not state["in_single"] and ch == '"':
        state["in_double"] = not state["in_double"]
        return True
    return state["in_single"] or state["in_double"]


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


def _segment_predicate(command: str, segment_test: "re.Pattern[str] | tuple"):
    """Build an ``offset -> bool`` predicate over precomputed segments.

    ``segment_test`` is either a compiled regex (the segment matches if
    the regex searches successfully) or a tuple of regexes (matches if
    *any* hits — split this way to keep each regex under Sonar's
    regex-complexity threshold).
    """
    segments = _split_top_level_segments(command)
    tests = segment_test if isinstance(segment_test, tuple) else (segment_test,)

    def hit(text: str) -> bool:
        return any(t.search(text) for t in tests)

    flags = [hit(command[s:e]) for (s, e) in segments]

    def in_flagged_segment(offset: int) -> bool:
        for idx, (s, e) in enumerate(segments):
            if s <= offset < e:
                return flags[idx]
        return False

    return in_flagged_segment


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _is_port_like(stripped: str) -> bool:
    """Comma- or hyphen-separated digit groups (each ≤ 5 digits) — a port spec."""
    return bool(_PORT_LIKE_RE.fullmatch(stripped))


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
        return command  # cheap fast path; most commands have no quotes
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
    segment_test: "re.Pattern[str] | tuple",
    passes: list,
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


def _redact_short_password_flag(command: str) -> str:
    """Mask short ``-p <value>`` credential flags.

    Numeric values stay visible (so ``nmap -p 22``, ``nmap -p 22,80``,
    ``nmap -p 1-1024`` survive) unless the segment names a credential tool
    (``hydra``, ``sshpass``, ``medusa``, …), in which case the value is
    masked even when numeric — numeric passwords are common. Handles
    spaced (``-p value``), equals (``-p=value``), and attached
    (``-p<value>``) shell forms.
    """

    def make_repl_spaced(in_cred):
        def repl(m: "re.Match[str]") -> str:
            lead, sep, value = m.group(1), m.group(2), m.group(3)
            if not in_cred(m.start()) and _is_port_like(_strip_quotes(value)):
                return f"{lead}-p{sep}{value}"
            return f"{lead}-p{sep}{REDACTED}"

        return repl

    def make_repl_attached(in_cred):
        def repl(m: "re.Match[str]") -> str:
            lead, value = m.group(1), m.group(2)
            if not in_cred(m.start()) and _is_port_like(_strip_quotes(value)):
                return f"{lead}-p{value}"
            return f"{lead}-p {REDACTED}"

        return repl

    return _segment_aware_sub_chain(
        command,
        _CREDENTIAL_TOOL_REGEXES,
        [
            (_SHORT_P_DQUOTE, make_repl_spaced),
            (_SHORT_P_SQUOTE, make_repl_spaced),
            (_SHORT_P_UNQUOTED, make_repl_spaced),
            (_SHORT_P_ATTACHED_DQUOTE, make_repl_attached),
            (_SHORT_P_ATTACHED_SQUOTE, make_repl_attached),
            (_SHORT_P_ATTACHED_UNQUOTED, make_repl_attached),
        ],
    )


def _redact_ntlm_hash_flag(command: str) -> str:
    """Mask ``-H <hash>`` only inside a segment that names a hash-using tool
    (crackmapexec / cme / nxc / impacket *.py / evil-winrm). ``curl -H
    'X-Foo: bar'`` is left alone."""

    def make_repl_spaced(in_seg):
        def repl(m: "re.Match[str]") -> str:
            if not in_seg(m.start()):
                return m.group(0)
            return f"{m.group(1)}-H{m.group(2)}{REDACTED}"

        return repl

    def make_repl_attached(in_seg):
        def repl(m: "re.Match[str]") -> str:
            if not in_seg(m.start()):
                return m.group(0)
            return f"{m.group(1)}-H {REDACTED}"

        return repl

    out = _segment_aware_sub_chain(
        command,
        _HASH_TOOLS_RE,
        [
            (_NTLM_HASH_DQUOTE, make_repl_spaced),
            (_NTLM_HASH_SQUOTE, make_repl_spaced),
            (_NTLM_HASH_UNQUOTED, make_repl_spaced),
            (_NTLM_HASH_ATTACHED_DQUOTE, make_repl_attached),
            (_NTLM_HASH_ATTACHED_SQUOTE, make_repl_attached),
            (_NTLM_HASH_ATTACHED_UNQUOTED, make_repl_attached),
        ],
    )

    # Impacket-specific `-hashes :HASH` / `--hashes <LM>:<NT>` form.
    # Scoped to segments where an impacket *.py tool appears so we
    # don't over-redact unrelated `--hashes` flags. Preserves the
    # flag literal (`m.group(2)` is `-hashes` or `--hashes`) and
    # only masks the value (group 4).
    from typing import Callable
    InSegPredicate = Callable[[int], bool]
    SubReplacer = Callable[["re.Match[str]"], str]

    def make_repl_hashes(in_seg: InSegPredicate) -> SubReplacer:
        """Build a `re.sub` replacer that masks `-hashes <value>` /
        `--hashes <value>` only when ``in_seg(match.start())`` is
        true (the match falls inside a command segment that names
        an impacket tool).
        """
        def repl(m: "re.Match[str]") -> str:
            """Mask the value; preserve the flag literal and leading separator."""
            if not in_seg(m.start()):
                return m.group(0)
            return f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}"
        return repl

    impacket_pred_re = re.compile(
        "|".join(p.pattern for p in _IMPACKET_TOOL_REGEXES),
        re.IGNORECASE,
    )
    out = _segment_aware_sub_chain(
        out,
        impacket_pred_re,
        [
            (_NTLM_HASHES_DQUOTE, make_repl_hashes),
            (_NTLM_HASHES_SQUOTE, make_repl_hashes),
            (_NTLM_HASHES_UNQUOTED, make_repl_hashes),
        ],
    )
    return out


def _redact_ldap_password_flag(command: str) -> str:
    """Mask ``-w <password>`` (LDAP simple bind) only inside a segment that
    names an ``ldap*`` tool. ``hydra -w wordlist.txt`` (wordlist, not a
    password) is left alone."""

    def make_repl_spaced(in_seg):
        def repl(m: "re.Match[str]") -> str:
            if not in_seg(m.start()):
                return m.group(0)
            return f"{m.group(1)}-w{m.group(2)}{REDACTED}"

        return repl

    def make_repl_attached(in_seg):
        def repl(m: "re.Match[str]") -> str:
            if not in_seg(m.start()):
                return m.group(0)
            return f"{m.group(1)}-w {REDACTED}"

        return repl

    return _segment_aware_sub_chain(
        command,
        _LDAP_TOOL_RE,
        [
            (_LDAP_W_DQUOTE, make_repl_spaced),
            (_LDAP_W_SQUOTE, make_repl_spaced),
            (_LDAP_W_UNQUOTED, make_repl_spaced),
            (_LDAP_W_ATTACHED_DQUOTE, make_repl_attached),
            (_LDAP_W_ATTACHED_SQUOTE, make_repl_attached),
            (_LDAP_W_ATTACHED_UNQUOTED, make_repl_attached),
        ],
    )


def _basic_auth_value_is_credential(value: str) -> bool:
    stripped = _strip_quotes(value)
    if _URL_PREFIX_RE.match(stripped):  # `sqlmap -u https://target/...`
        return False
    return "%" in stripped or ":" in stripped  # Samba user%pass / Basic user:pass


def _redact_basic_auth_user(command: str) -> str:
    """Mask ``--user``/``-u``/``-U`` when the value is a credential pair.

    The long ``--user`` form is content-based — overwhelmingly auth
    bearing across tools, so a value with ``:`` or ``%`` (and not a
    URL) is masked. The short ``-u``/``-U`` forms ALSO require the
    segment to name a tool that actually uses those short flags for
    auth (curl/wget/smbclient/nxc/crackmapexec/impacket family/…).
    Without that gate, ``date -u +%Y:%m`` (where ``-u`` is the UTC
    flag and ``+%Y:%m`` is just an unrelated value) would be misread
    as Basic auth.
    """

    def make_repl_spaced(in_short_seg):
        def repl(m: "re.Match[str]") -> str:
            lead, flag, sep, value = m.group(1), m.group(2), m.group(3), m.group(4)
            if not _basic_auth_value_is_credential(value):
                return m.group(0)
            if flag in ("-u", "-U") and not in_short_seg(m.start()):
                return m.group(0)
            return f"{lead}{flag}{sep}{REDACTED}"

        return repl

    def make_repl_attached(in_short_seg):
        def repl(m: "re.Match[str]") -> str:
            lead, flag, value = m.group(1), m.group(2), m.group(3)
            if not _basic_auth_value_is_credential(value):
                return m.group(0)
            # Attached forms only fire on the short flags (``-u``/``-U``)
            # by construction, so the tool-segment gate always applies.
            if not in_short_seg(m.start()):
                return m.group(0)
            return f"{lead}{flag} {REDACTED}"

        return repl

    return _segment_aware_sub_chain(
        command,
        _BASIC_AUTH_SHORT_TOOLS_REGEXES,
        [
            (_BASIC_AUTH_USER_DQUOTE, make_repl_spaced),
            (_BASIC_AUTH_USER_SQUOTE, make_repl_spaced),
            (_BASIC_AUTH_USER_UNQUOTED, make_repl_spaced),
            (_BASIC_AUTH_USER_ATTACHED_DQUOTE, make_repl_attached),
            (_BASIC_AUTH_USER_ATTACHED_SQUOTE, make_repl_attached),
            (_BASIC_AUTH_USER_ATTACHED_UNQUOTED, make_repl_attached),
        ],
    )


def _redact_impacket_positional_auth(command: str) -> str:
    """Mask the password in an impacket positional ``user:password@host``
    target (``psexec.py corp/alice:pw@dc``) — only inside a segment that
    names an impacket-family tool, so a ``user:token@host`` elsewhere is
    untouched. Preserves ``user`` and ``@host`` for SIEM correlation."""

    def make_repl(in_seg):
        def repl(m: "re.Match[str]") -> str:
            if not in_seg(m.start()):
                return m.group(0)
            return f"{m.group(1)}:{REDACTED}@{m.group(3)}"

        return repl

    return _segment_aware_sub_chain(
        command,
        _IMPACKET_TOOL_REGEXES,
        [
            (_IMPACKET_POSITIONAL_DQUOTE, make_repl),
            (_IMPACKET_POSITIONAL_SQUOTE, make_repl),
            (_IMPACKET_POSITIONAL_BARE, make_repl),
        ],
    )


def _redact_command_flags(value: str) -> str:
    """Apply the tool-context-aware command-line redactors in order.

    Runs after the simple key/value patterns so the cheaper shapes have
    first claim on overlapping inputs (matches ``redaction.ts``'s order).
    The leading segment-scoped quote-strip unquotes ``'-X'``/``"-X"``
    option tokens *only* within credential-bearing segments so
    ``hydra '-p' hunter2`` still triggers the per-flag matcher while
    ``echo '-p' hunter2`` is preserved verbatim.
    """
    out = _unquote_options_in_credential_segments(value)
    out = _redact_short_password_flag(out)
    out = _redact_ntlm_hash_flag(out)
    out = _redact_ldap_password_flag(out)
    out = _redact_basic_auth_user(out)
    out = _redact_impacket_positional_auth(out)
    return out
