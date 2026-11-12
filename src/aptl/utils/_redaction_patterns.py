"""Credential patterns shared by recursive and shell redaction.

Keep these definitions in parity with the TypeScript redaction modules.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# Inline-secret patterns for plain-text strings (command lines, headers,
# query strings, etc.). Mirrors the TypeScript helper so artifacts emitted
# from either language match shape.
_SENSITIVE_KEY_PATTERN = (
    r"(?:pass(?:word|wd|phrase)?|secret|token|credential|"
    r"api[_-]?key|apikey|jwt|bearer|session(?:_id)?|cookie|"
    r"com\.docker\.compose\.config-hash)"
)
# `\S+` would greedily consume trailing quotes/punctuation around the
# secret value (e.g. eat the closing `'` of a curl `-H 'Authorization: ...'`
# header, corrupting downstream diagnostic structure). Stop at quotes
# and whitespace instead.
_VALUE_PATTERN = r"[^\s'\"]+"
_AUTHORIZATION_RE = re.compile(
    # `re.IGNORECASE` handles both cases — listing `A-Z` alongside `a-z`
    # is redundant under case-insensitive matching (Sonar S5869).
    rf"(authorization\s*[:=]\s*)(?:([a-z][\w-]*)\s+)?{_VALUE_PATTERN}",
    re.IGNORECASE,
)
# `\b` word-boundaries break on compound names because `_` is a word
# character — `access_token=...` matches neither `\btoken\b` nor
# `\baccess_token\b`. Use alphanumeric-only boundaries so `_`, `-`, and
# punctuation all count as separators.
# Left boundary.
_KEY_LB = r"(?<![a-zA-Z0-9])"
# Right boundary.
_KEY_RB = r"(?![a-zA-Z0-9])"
# Capture leading and trailing quotes as separate groups so the
# replacement preserves them (otherwise wrapping `'<value>'` /
# `"<value>"` loses the closing quote, corrupting downstream
# diagnostic structure).
_SENSITIVE_KV_RE = re.compile(
    rf"({_KEY_LB}{_SENSITIVE_KEY_PATTERN}{_KEY_RB}\s*[=:]\s*['\"]?)([^'\"&\s,;|]+)(['\"]?)",
    re.IGNORECASE,
)
_BARE_BEARER_RE = re.compile(rf"({_KEY_LB}bearer\s+){_VALUE_PATTERN}", re.IGNORECASE)
# `--password value` / `--client-secret value` / `--access-token value`
# style (long CLI flags). The `[\w-]*` prefixes allow compound flag
# names like `--client-secret`; regex backtracking finds the embedded
# sensitive token.
# A match starts only where a run of `[\w-]` characters starts, and group 1
# keeps the run text before its first `--`. A start at a later `--` of the
# same run cannot match when the first `--` does not, so the output is the
# same as for `--[\w-]*...` alone. Without this anchor the regex re-scanned
# the run from every `--` in it, which is quadratic on long dash runs.
_CLI_FLAG_RE = re.compile(
    rf"((?<![\w-])(?:\w|-(?!-))*--[\w-]*{_SENSITIVE_KEY_PATTERN}{_KEY_RB}\s+)"
    rf"{_VALUE_PATTERN}",
    re.IGNORECASE,
)
# Cookie / Set-Cookie header: redact the entire body so multi-segment
# cookies like `Cookie: lang=en; connect.sid=SECRET` are masked in one
# pass instead of leaving later segments intact. Capture the leading and
# trailing quotes (when present) as separate groups so the replacement
# can put them back — otherwise a wrapping `'...'` loses its closing
# quote.
_COOKIE_HEADER_RE = re.compile(
    r"((?:set-cookie|cookie)\s*[:=]\s*['\"]?)([^'\"\r\n]+)(['\"]?)",
    re.IGNORECASE,
)
# URL userinfo: `scheme://user:password@host/path`. Preserve user (often
# useful for diagnostics) and mask the password segment.
_URL_USERINFO_RE = re.compile(r"(://[^/:@\s]+:)[^@\s]+(@)")
# Match only the delimiters; scanning between them avoids buffering or
# backtracking over arbitrary key data, including an unfinished final block.
_PEM_BEGIN_RE = re.compile(r"-----BEGIN[^-]*-----")
_PEM_END_RE = re.compile(r"-----END[^-]*-----")


def _redact_pem_blocks(value: str) -> str:
    """Mask each PEM body through its closing delimiter or the end of input."""
    parts = []
    cursor = 0
    while begin := _PEM_BEGIN_RE.search(value, cursor):
        parts.extend((value[cursor : begin.end()], REDACTED))
        end = _PEM_END_RE.search(value, begin.end())
        if end is None:
            cursor = len(value)
            break
        parts.append(end.group())
        cursor = end.end()
    parts.append(value[cursor:])
    return "".join(parts)


# Recognizes `--<sensitive>` (or compound `--client-secret`,
# `--access-token`) as a standalone token used by array-pair detection
# so adjacent positional values get redacted.
_CLI_FLAG_TOKEN_RE = re.compile(
    rf"^--[\w-]*{_SENSITIVE_KEY_PATTERN}{_KEY_RB}$",
    re.IGNORECASE,
)
# Quote-stripped standalone option tokens — `'-p'` → `-p`, `"-U"` → `-U`.
# Runs before the flag matchers so a quoted option token still triggers
# the per-flag credential redaction below.
_QUOTED_OPTION_TOKEN_RE = re.compile(r"""(['"])(-[A-Za-z][\w-]*)\1""")


def _redact_authorization(match: "re.Match[str]") -> str:
    """Mask an authorization value while preserving its optional scheme."""
    prefix, scheme = match.group(1), match.group(2)
    if scheme:
        return f"{prefix}{scheme} {REDACTED}"
    return f"{prefix}{REDACTED}"


# Per-segment tool-family detectors. Split into small batches so each
# regex stays well under the regex-complexity threshold (Sonar S5843);
# a segment matches if ANY batch hits and `.search()` short-circuits.
_CREDENTIAL_TOOL_REGEXES: tuple["re.Pattern[str]", ...] = (
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(hydra|medusa|patator|crowbar|sshpass|wfuzz|kerbrute)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(crackmapexec|cme|nxc|evil-winrm)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(bloodhound-python|bloodhound\.py)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(mysql|mariadb|mysqladmin|redis-cli)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?"
        r"(impacket-psexec|impacket-smbexec|impacket-wmiexec|impacket-secretsdump)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?"
        r"(psexec\.py|smbexec\.py|wmiexec\.py|secretsdump\.py|getuserspns\.py|getnpusers\.py|ntlmrelayx\.py)(?:\s|$)",
        re.IGNORECASE,
    ),
)
_HASH_TOOLS_RE = re.compile(
    r"(^|[\s|;&])(?:[\w./-]+/)?"
    r"(crackmapexec|cme|nxc|psexec\.py|smbexec\.py|wmiexec\.py|secretsdump\.py|impacket-[\w-]+|evil-winrm)(?:\s|$)",
    re.IGNORECASE,
)
_LDAP_TOOL_RE = re.compile(
    r"(^|[\s|;&])(?:[\w./-]+/)?"
    r"(ldapadd|ldapcompare|ldapdelete|ldapmodify|ldappasswd|ldapsearch|ldapwhoami)(?:\s|$)",
    re.IGNORECASE,
)
_IMPACKET_TOOL_REGEXES: tuple["re.Pattern[str]", ...] = (
    re.compile(r"(^|[\s|;&])(?:[\w./-]+/)?(impacket-[\w-]+)(?:\s|$)", re.IGNORECASE),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(psexec\.py|smbexec\.py|wmiexec\.py|dcomexec\.py|atexec\.py)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(secretsdump\.py|getuserspns\.py|getnpusers\.py|ntlmrelayx\.py)(?:\s|$)",
        re.IGNORECASE,
    ),
)
# Tools whose ``-hashes`` / ``--hashes`` option carries an NTLM hash: the
# ``-H`` hash tools and the impacket family.
_HASHES_FLAG_TOOL_REGEXES: tuple["re.Pattern[str]", ...] = (
    _HASH_TOOLS_RE,
    *_IMPACKET_TOOL_REGEXES,
)
# Tools where the short flags ``-u`` / ``-U`` carry a username (often
# paired with an embedded password — Basic-auth ``user:pass`` for HTTP
# clients, Samba ``user%pass`` for the SMB family). The short forms are
# scoped to this list so a generic ``date -u +%Y:%m`` (where ``-u`` is a
# UTC flag and ``+%Y:%m`` is just an unrelated value) is not mis-classified
# as Basic auth. The long ``--user`` form stays content-based — that
# spelling is overwhelmingly auth-bearing.
_BASIC_AUTH_SHORT_TOOLS_REGEXES: tuple["re.Pattern[str]", ...] = (
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(curl|wget|smbclient|smbget|hydra|medusa|kerbrute)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(crackmapexec|cme|nxc|evil-winrm)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?(mysql|mysqladmin|mariadb|redis-cli|psql|ldapsearch|"
        r"bloodhound-python|bloodhound\.py)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(^|[\s|;&])(?:[\w./-]+/)?"
        r"(impacket-[\w-]+|psexec\.py|smbexec\.py|wmiexec\.py|secretsdump\.py|getuserspns\.py|"
        r"getnpusers\.py|ntlmrelayx\.py)(?:\s|$)",
        re.IGNORECASE,
    ),
)
# Union of every credential-bearing tool family. Used by the
# segment-scoped quote-strip so an option-shaped token like ``'-p'`` is
# only normalized to bare ``-p`` when its segment is plausibly running a
# credential-using tool. Outside such segments (``echo '-p' hunter2``,
# ``grep '-u' alice file``) the quotes are left in place so the per-flag
# matchers cannot fire on innocent data.
_ANY_CREDENTIAL_TOOL_REGEXES: tuple["re.Pattern[str]", ...] = (
    *_CREDENTIAL_TOOL_REGEXES,
    _HASH_TOOLS_RE,
    _LDAP_TOOL_RE,
    *_IMPACKET_TOOL_REGEXES,
    *_BASIC_AUTH_SHORT_TOOLS_REGEXES,
)

# Quoted-value forms use the unrolled-loop pattern `"[^"\\]*(?:\\.[^"\\]*)*"`
# (not the alternation form `(?:[^"\\]|\\.)*`) so the regex engine has no
# ambiguous backtracking path — eliminates the ReDoS class at the engine
# level (Sonar S5852). The unquoted/attached forms are escape-aware:
# `(?:\\.|[^\s'"\\])+` consumes `\<anything>` plus ordinary tokens so
# `hydra -p correct\ horse` is one shell token.
_DQ_VALUE = r'"[^"\\]*(?:\\.[^"\\]*)*"'
_SQ_VALUE = r"'[^'\\]*(?:\\.[^'\\]*)*'"
_BARE_VALUE = r"(?:\\.|[^\s'\"\\])+"

_SHORT_P_DQUOTE = re.compile(rf"(^|\s|\|)-p(\s+|=)({_DQ_VALUE})")
_SHORT_P_SQUOTE = re.compile(rf"(^|\s|\|)-p(\s+|=)({_SQ_VALUE})")
_SHORT_P_UNQUOTED = re.compile(rf"(^|\s|\|)-p(\s+|=)({_BARE_VALUE})")
_SHORT_P_ATTACHED_DQUOTE = re.compile(rf"(^|\s|\|)-p({_DQ_VALUE})")
_SHORT_P_ATTACHED_SQUOTE = re.compile(rf"(^|\s|\|)-p({_SQ_VALUE})")
_SHORT_P_ATTACHED_UNQUOTED = re.compile(r"(^|\s|\|)-p([^\s='\"](?:\\.|[^\s'\"\\])*)")

_NTLM_HASH_DQUOTE = re.compile(rf"(^|\s|\|)-H(\s+|=)({_DQ_VALUE})")
_NTLM_HASH_SQUOTE = re.compile(rf"(^|\s|\|)-H(\s+|=)({_SQ_VALUE})")
_NTLM_HASH_UNQUOTED = re.compile(rf"(^|\s|\|)-H(\s+|=)({_BARE_VALUE})")
_NTLM_HASH_ATTACHED_DQUOTE = re.compile(rf"(^|\s|\|)-H({_DQ_VALUE})")
_NTLM_HASH_ATTACHED_SQUOTE = re.compile(rf"(^|\s|\|)-H({_SQ_VALUE})")
_NTLM_HASH_ATTACHED_UNQUOTED = re.compile(r"(^|\s|\|)-H([^\s='\"](?:\\.|[^\s'\"\\])*)")

# Impacket's documented short form is `-hashes [<LM>]:<NT>` (single
# dash, full word). The `-H` patterns above only catch the
# crackmapexec/nxc shape. Without these, a command like
# `psexec.py alice@dc -hashes :8846f7eaee8fb117` leaked the NT hash
# through redaction (test-quality review cycle 1 finding-1 surfaced
# the missing assertion that exposed this pre-existing bug).
_NTLM_HASHES_DQUOTE = re.compile(rf"(^|\s|\|)(--?hashes)(\s+|=)({_DQ_VALUE})")
_NTLM_HASHES_SQUOTE = re.compile(rf"(^|\s|\|)(--?hashes)(\s+|=)({_SQ_VALUE})")
_NTLM_HASHES_UNQUOTED = re.compile(rf"(^|\s|\|)(--?hashes)(\s+|=)({_BARE_VALUE})")

_LDAP_W_DQUOTE = re.compile(rf"(^|\s|\|)-w(\s+|=)({_DQ_VALUE})")
_LDAP_W_SQUOTE = re.compile(rf"(^|\s|\|)-w(\s+|=)({_SQ_VALUE})")
_LDAP_W_UNQUOTED = re.compile(rf"(^|\s|\|)-w(\s+|=)({_BARE_VALUE})")
_LDAP_W_ATTACHED_DQUOTE = re.compile(rf"(^|\s|\|)-w({_DQ_VALUE})")
_LDAP_W_ATTACHED_SQUOTE = re.compile(rf"(^|\s|\|)-w({_SQ_VALUE})")
_LDAP_W_ATTACHED_UNQUOTED = re.compile(r"(^|\s|\|)-w([^\s='\"](?:\\.|[^\s'\"\\])*)")

_BASIC_AUTH_USER_DQUOTE = re.compile(rf"(^|\s|\|)(--user|-u|-U)(\s+|=)({_DQ_VALUE})")
_BASIC_AUTH_USER_SQUOTE = re.compile(rf"(^|\s|\|)(--user|-u|-U)(\s+|=)({_SQ_VALUE})")
_BASIC_AUTH_USER_UNQUOTED = re.compile(
    rf"(^|\s|\|)(--user|-u|-U)(\s+|=)({_BARE_VALUE})"
)
_BASIC_AUTH_USER_ATTACHED_DQUOTE = re.compile(rf"(^|\s|\|)(-u|-U)({_DQ_VALUE})")
_BASIC_AUTH_USER_ATTACHED_SQUOTE = re.compile(rf"(^|\s|\|)(-u|-U)({_SQ_VALUE})")
_BASIC_AUTH_USER_ATTACHED_UNQUOTED = re.compile(
    r"(^|\s|\|)(-u|-U)([^\s='\"](?:\\.|[^\s'\"\\])*)"
)

# Impacket positional `user:password@host` / `domain/user:password@host`.
# Mirrors impacket's own `parse_target` (`[^@]*` for the password), so the
# bare form can't contain a literal `@`; users with `@`/whitespace in the
# password MUST quote. `(?=\s|$|[;|&])` requires a token boundary after the
# host so we don't eat into the rest of the command line.
# A leading token-boundary lookbehind eliminates the O(n^2) ReDoS these
# patterns exhibited (ARCH-386-01 / redact-01). Without it, `re.sub` re-tried
# the match at *every* offset inside a long flag-like token (`hydra --aaaa…`
# or `aaaa:bbbb` with no `@`), and each attempt scanned the rest of the token
# — quadratic. `(?<![\w\\/.:@-])` forbids starting a match in the middle of a
# target token, so attempts collapse from O(n) offsets to O(tokens); the
# match can still begin after whitespace, `;`/`|`/`&`, `=`, or a quote, which
# is exactly where an impacket positional target legitimately starts. The
# lookbehind is zero-width and non-capturing, so groups 1/2/3 stay
# user/value/host. Portable to the TS mirror (JS supports lookbehind); parity
# is verified by the shared golden corpus.
_IMPACKET_LEAD = r"(?<![\w\\/.:@-])"
_IMPACKET_POSITIONAL_DQUOTE = re.compile(
    rf'{_IMPACKET_LEAD}([\w\\/.-]+):"([^"\\]*(?:\\.[^"\\]*)*)"@([\w.-]+)(?=\s|$|[;|&])'
)
_IMPACKET_POSITIONAL_SQUOTE = re.compile(
    rf"{_IMPACKET_LEAD}([\w\\/.-]+):'([^'\\]*(?:\\.[^'\\]*)*)'@([\w.-]+)(?=\s|$|[;|&])"
)
_IMPACKET_POSITIONAL_BARE = re.compile(
    rf"{_IMPACKET_LEAD}([\w\\/.-]+):((?:\\.|[^\\@\s])+)@([\w.-]+)(?=\s|$|[;|&])"
)

_URL_PREFIX_RE = re.compile(r"^(?:https?|ftp|ldap|ldaps|smb|smbs)://", re.IGNORECASE)
# ASCII digits only: a port is never written in other scripts, so a value in
# other digits is a password and is masked.
_PORT_LIKE_RE = re.compile(r"^[0-9]{1,5}(?:[,-][0-9]{1,5})*$")
