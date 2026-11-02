/** Credential patterns for shell redaction; mirror Python's pattern module. */
export const REDACTED = '[REDACTED]';


// `-p` / `-p=value` / `-p<value>` short-flag handling for credential
// tools. The leading token of the command line determines whether `-p`
// could carry a password (hydra, medusa, sshpass, crackmapexec, nxc, …)
// — but wrappers like `proxychains4 hydra …` or `sudo hydra …` shift
// that token. Detect both: if the command line contains any known
// credential-taking-`-p` tool token before the `-p`, redact the value
// even if numeric (numeric passwords are common). For unknown leading
// tools, only redact non-numeric `-p` values so port numbers
// (`nmap -p 22`) stay visible.
//
// Known tools whose short `-p` is a password value:
export const CREDENTIAL_SHORT_P_TOOLS: ReadonlySet<string> = new Set([
  'hydra',
  'medusa',
  'patator',
  'crowbar',
  'sshpass',
  'crackmapexec',
  'cme',
  'nxc',
  'wfuzz',
  'mysql',
  'mysqladmin',
  'mariadb',
  'redis-cli',
  'evil-winrm',
  'bloodhound-python',
  'bloodhound.py',
  'kerbrute',
  'impacket-psexec',
  'impacket-smbexec',
  'impacket-wmiexec',
  'impacket-secretsdump',
  'psexec.py',
  'smbexec.py',
  'wmiexec.py',
  'secretsdump.py',
  'getuserspns.py',
  'getnpusers.py',
  'ntlmrelayx.py',
]);

// Tools whose `-w <value>` is a password (LDAP simple-bind). Distinct
// from wordlist-`-w` for hydra/wfuzz; per-segment detection picks the
// right meaning.
export const LDAP_PASSWORD_TOOLS: ReadonlySet<string> = new Set([
  'ldapsearch',
  'ldapmodify',
  'ldapadd',
  'ldapdelete',
  'ldappasswd',
  'ldapwhoami',
  'ldapcompare',
]);

// Per-segment tool detection. Originally a single big alternation
// regex; Sonar S5843 flagged the long tool list as over the
// regex-complexity threshold (~34). Split into smaller batches; a
// segment matches if ANY batch hits. Each batch stays well under the
// 20 limit and `.some()` short-circuits once a batch matches.
export const CREDENTIAL_TOOL_REGEXES: readonly RegExp[] = [
  /(^|[\s|;&])(?:[\w./-]+\/)?(hydra|medusa|patator|crowbar|sshpass|wfuzz|kerbrute)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(crackmapexec|cme|nxc|evil-winrm)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(bloodhound-python|bloodhound\.py)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(mysql|mariadb|mysqladmin|redis-cli)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(impacket-psexec|impacket-smbexec|impacket-wmiexec|impacket-secretsdump)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(psexec\.py|smbexec\.py|wmiexec\.py|secretsdump\.py|getuserspns\.py|getnpusers\.py|ntlmrelayx\.py)(?:\s|$)/i,
];

// Tools where the short flags `-u` / `-U` carry a username (often paired
// with an embedded password — Basic-auth `user:pass` for HTTP clients,
// Samba `user%pass` for the SMB family). The short forms are scoped to
// this list so a generic `date -u +%Y:%m` (where `-u` is the UTC flag
// and `+%Y:%m` is just an unrelated value) is not mis-classified as
// Basic auth. The long `--user` form stays content-based — that
// spelling is overwhelmingly auth-bearing.
export const BASIC_AUTH_SHORT_TOOL_REGEXES: readonly RegExp[] = [
  /(^|[\s|;&])(?:[\w./-]+\/)?(curl|wget|smbclient|smbget|hydra|medusa|kerbrute)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(crackmapexec|cme|nxc|evil-winrm)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(mysql|mysqladmin|mariadb|redis-cli|psql|ldapsearch|bloodhound-python|bloodhound\.py)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(impacket-[\w-]+|psexec\.py|smbexec\.py|wmiexec\.py|secretsdump\.py|getuserspns\.py|getnpusers\.py|ntlmrelayx\.py)(?:\s|$)/i,
];

export const QUOTED_OPTION_TOKEN_RE = /(['"])(-[A-Za-z][\w-]*)\1/g;

// Quote- and form-aware short `-p` matcher. Originally a single regex
// with three value-form alternatives, but Sonar S5843 flagged the
// composed pattern as over the regex-complexity threshold (≥20). We
// now run three smaller regexes per flag — double-quoted, single-quoted,
// unquoted-with-escape — applied in that order so the quoted forms are
// consumed before the unquoted matcher could eat the surrounding quotes.
//
// The escape-aware unquoted alternative `(?:\\.|[^\s'"\\])+` consumes
// `\<anything>` plus ordinary non-whitespace non-quote characters so
// `hydra -p correct\ horse` is treated as a single shell token (the
// space after `correct\` is escaped).
export const SHORT_P_DQUOTE = /(^|\s|\|)-p(\s+|=)("(?:[^"\\]|\\.)*")/g;
export const SHORT_P_SQUOTE = /(^|\s|\|)-p(\s+|=)('(?:[^'\\]|\\.)*')/g;
export const SHORT_P_UNQUOTED = /(^|\s|\|)-p(\s+|=)((?:\\.|[^\s'"\\])+)/g;
export const SHORT_P_ATTACHED_DQUOTE = /(^|\s|\|)-p("(?:[^"\\]|\\.)*")/g;
export const SHORT_P_ATTACHED_SQUOTE = /(^|\s|\|)-p('(?:[^'\\]|\\.)*')/g;
export const SHORT_P_ATTACHED_UNQUOTED = /(^|\s|\|)-p([^\s='"](?:\\.|[^\s'"\\])*)/g;

// `-H <hash>` / `-H=hash` / `-H<hash>` for credential-using tools
// (crackmapexec / cme / nxc / impacket *.py). The same flag means HTTP
// header to curl/wget — we only redact when the segment contains a
// credential tool that uses `-H` as a hash flag.
export const NTLM_HASH_DQUOTE = /(^|\s|\|)-H(\s+|=)("(?:[^"\\]|\\.)*")/g;
export const NTLM_HASH_SQUOTE = /(^|\s|\|)-H(\s+|=)('(?:[^'\\]|\\.)*')/g;
export const NTLM_HASH_UNQUOTED = /(^|\s|\|)-H(\s+|=)((?:\\.|[^\s'"\\])+)/g;
export const NTLM_HASH_ATTACHED_DQUOTE = /(^|\s|\|)-H("(?:[^"\\]|\\.)*")/g;
export const NTLM_HASH_ATTACHED_SQUOTE = /(^|\s|\|)-H('(?:[^'\\]|\\.)*')/g;
export const NTLM_HASH_ATTACHED_UNQUOTED = /(^|\s|\|)-H([^\s='"](?:\\.|[^\s'"\\])*)/g;

// Impacket's documented short form is `-hashes [<LM>]:<NT>` (single
// dash, full word; long form `--hashes` is also valid). Without
// these patterns a command like
// `psexec.py alice@dc -hashes :8846f7eaee8fb117` leaked the NT hash
// through redaction. Scoped to impacket tool segments only via
// HASH_TOOLS_RE to avoid over-redacting unrelated `--hashes` flags.
// Test-quality review cycle 1 finding-1 surfaced the missing
// assertion that exposed this pre-existing bug.
export const NTLM_HASHES_DQUOTE = /(^|\s|\|)(--?hashes)(\s+|=)("(?:[^"\\]|\\.)*")/g;
export const NTLM_HASHES_SQUOTE = /(^|\s|\|)(--?hashes)(\s+|=)('(?:[^'\\]|\\.)*')/g;
export const NTLM_HASHES_UNQUOTED = /(^|\s|\|)(--?hashes)(\s+|=)((?:\\.|[^\s'"\\])+)/g;

export const HASH_TOOLS_RE = /(^|[\s|;&])(?:[\w./-]+\/)?(crackmapexec|cme|nxc|psexec\.py|smbexec\.py|wmiexec\.py|secretsdump\.py|impacket-[\w-]+|evil-winrm)(?:\s|$)/i;

// `--user`, `-u`, `-U` for tools where the value can be a credential.
// Mask when:
//   - the value contains `:` AND it is NOT a URL (URL `-u` for sqlmap /
//     gobuster has `https:` in it but is not a credential) — Basic-auth
//     pair shape.
//   - the value contains `%` — Samba `username%password` shape.
// Bare `--user alice` (no colon, no `%`) is left alone.
export const BASIC_AUTH_USER_DQUOTE = /(^|\s|\|)(--user|-u|-U)(\s+|=)("(?:[^"\\]|\\.)*")/g;
export const BASIC_AUTH_USER_SQUOTE = /(^|\s|\|)(--user|-u|-U)(\s+|=)('(?:[^'\\]|\\.)*')/g;
export const BASIC_AUTH_USER_UNQUOTED = /(^|\s|\|)(--user|-u|-U)(\s+|=)((?:\\.|[^\s'"\\])+)/g;
export const BASIC_AUTH_USER_ATTACHED_DQUOTE = /(^|\s|\|)(-u|-U)("(?:[^"\\]|\\.)*")/g;
export const BASIC_AUTH_USER_ATTACHED_SQUOTE = /(^|\s|\|)(-u|-U)('(?:[^'\\]|\\.)*')/g;
export const BASIC_AUTH_USER_ATTACHED_UNQUOTED = /(^|\s|\|)(-u|-U)([^\s='"](?:\\.|[^\s'"\\])*)/g;

// LDAP simple-bind password: `ldapsearch -w <password>` and friends.
// Per-segment detected: `-w` for hydra/wfuzz is a wordlist (file path),
// not a password.
export const LDAP_W_DQUOTE = /(^|\s|\|)-w(\s+|=)("(?:[^"\\]|\\.)*")/g;
export const LDAP_W_SQUOTE = /(^|\s|\|)-w(\s+|=)('(?:[^'\\]|\\.)*')/g;
export const LDAP_W_UNQUOTED = /(^|\s|\|)-w(\s+|=)((?:\\.|[^\s'"\\])+)/g;
export const LDAP_W_ATTACHED_DQUOTE = /(^|\s|\|)-w("(?:[^"\\]|\\.)*")/g;
export const LDAP_W_ATTACHED_SQUOTE = /(^|\s|\|)-w('(?:[^'\\]|\\.)*')/g;
export const LDAP_W_ATTACHED_UNQUOTED = /(^|\s|\|)-w([^\s='"](?:\\.|[^\s'"\\])*)/g;
export const LDAP_TOOL_RE = /(^|[\s|;&])(?:[\w./-]+\/)?(ldapadd|ldapcompare|ldapdelete|ldapmodify|ldappasswd|ldapsearch|ldapwhoami)(?:\s|$)/i;

export const URL_PREFIX_RE = /^(?:https?|ftp|ldap|ldaps|smb|smbs):\/\//i;

// Impacket family accepts a positional `user:password@host` (or
// `domain/user:password@host`) shape. The shared key/value redactors
// don't catch it because it's not a flag. Mask the password segment
// while preserving user@host context for SIEM correlation. Only fire
// when the segment contains an impacket-family tool token.
//
// Real Windows / domain passwords commonly contain `:`, `@`, and
// whitespace. Match three forms:
//   - bare:    `user:VALUE@host`            — VALUE is non-`@`,
//              non-whitespace chars (with backslash-escapes); aligns
//              with impacket's own `parse_target`, which uses `[^@]*`
//              for the password and therefore can't accept literal
//              `@` in unquoted form either. Users with `@` or
//              whitespace in passwords MUST quote.
//   - dquot:   `user:"VALUE"@host`          — quoted value (any char).
//   - squot:   `user:'VALUE'@host`          — single-quoted.
// Split into per-value-form patterns to keep each regex under Sonar's
// regex-complexity threshold (S5843). The combined form was ~28; each
// split form is ~15-18.
//
// DQUOTE / SQUOTE use the unrolled-loop quoted-string form
// (`[^Q\\]*(?:\\.[^Q\\]*)*`) instead of the alternation form
// (`(?:[^Q\\]|\\.)*`). Both match the same language, but the unrolled
// form has no inner alternation so the regex engine cannot pick
// between two alternatives that could match the same character —
// eliminating the ReDoS risk at the engine level (Sonar S5852).
//
// BARE uses exclusive alternatives `\\.|[^\\@\s]` instead of `\\.|\S`.
// `\S` overlaps with `\\.` (both can match the leading backslash of an
// escape), creating ambiguous backtracking; `[^\\@\s]` excludes the
// backslash so the alternatives are mutually exclusive. `@` is also
// excluded so the pattern stops at the host separator without needing
// laziness, which removes another backtracking source.
// A leading token-boundary lookbehind `(?<![\w\\/.:@-])` eliminates the
// O(n^2) ReDoS these patterns exhibited (ARCH-386-01 / redact-01): without
// it the engine re-tried the match at every offset inside a long flag-like
// token (`hydra --aaaa…` or `aaaa:bbbb` with no `@`), each attempt scanning
// the rest of the token. The lookbehind forbids starting a match in the
// middle of a target token, collapsing attempts from O(n) offsets to
// O(tokens), while still allowing a match to begin after whitespace,
// `;`/`|`/`&`, `=`, or a quote — exactly where an impacket positional target
// legitimately starts. Zero-width and non-capturing, so groups 1/2/3 stay
// user/value/host. Mirrors `redaction.py`; parity is verified by the shared
// golden corpus.
export const IMPACKET_POSITIONAL_DQUOTE = /(?<![\w\\/.:@-])([\w\\/.-]+):"([^"\\]*(?:\\.[^"\\]*)*)"@([\w.-]+)(?=\s|$|[;|&])/g;
export const IMPACKET_POSITIONAL_SQUOTE = /(?<![\w\\/.:@-])([\w\\/.-]+):'([^'\\]*(?:\\.[^'\\]*)*)'@([\w.-]+)(?=\s|$|[;|&])/g;
export const IMPACKET_POSITIONAL_BARE = /(?<![\w\\/.:@-])([\w\\/.-]+):((?:\\.|[^\\@\s])+)@([\w.-]+)(?=\s|$|[;|&])/g;

export const IMPACKET_TOOL_REGEXES: readonly RegExp[] = [
  /(^|[\s|;&])(?:[\w./-]+\/)?(impacket-[\w-]+)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(psexec\.py|smbexec\.py|wmiexec\.py|dcomexec\.py|atexec\.py)(?:\s|$)/i,
  /(^|[\s|;&])(?:[\w./-]+\/)?(secretsdump\.py|getuserspns\.py|getnpusers\.py|ntlmrelayx\.py)(?:\s|$)/i,
];
export interface ArgvCredentialModes {
  cred: boolean;
  hash: boolean;
  ldap: boolean;
  basic: boolean;
}

export interface ArgvShortFlagRule {
  mode: keyof ArgvCredentialModes;
  flags: ReadonlySet<string>;
  contentGated: boolean;
}

export const ARGV_SHORT_FLAG_RULES: readonly ArgvShortFlagRule[] = [
  { mode: 'cred', flags: new Set(['-p']), contentGated: false },
  { mode: 'hash', flags: new Set(['-H']), contentGated: false },
  { mode: 'ldap', flags: new Set(['-w']), contentGated: false },
  // Basic-auth `-u`/`-U` keeps the same content gate as the string-mode
  // redactor: bare usernames stay visible, only credential pairs mask.
  { mode: 'basic', flags: new Set(['-u', '-U']), contentGated: true },
];
