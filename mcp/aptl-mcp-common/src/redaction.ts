/**
 * Shared redaction helper for serialization boundaries in MCP servers.
 *
 * Run analysis artifacts (OTel span attributes, exported run archives,
 * tool call traces) are not credential stores. Redact secret-shaped
 * values at the serialization boundary so file permissions and archive
 * locations remain defense in depth, not the only line of protection.
 * See ADR-012 § Security Guardrail.
 *
 * Mirrors `src/aptl/utils/redaction.py` so artifacts emitted from
 * either language match shape.
 */

import { REDACTED } from './redaction-command-patterns.js';
import {
  unquoteOptionsInCredentialSegments,
  redactShortPasswordFlag,
  redactNtlmHashFlag,
  redactLdapPasswordFlag,
  redactBasicAuthUser,
  redactImpacketPositionalAuth,
  argvCredentialModes,
  argvShortFlagSkipIndices,
} from './redaction-commands.js';
export { REDACTED } from './redaction-command-patterns.js';
export {
  unquoteOptionsInCredentialSegments,
  redactShortPasswordFlag,
  redactNtlmHashFlag,
  redactLdapPasswordFlag,
  redactBasicAuthUser,
  redactImpacketPositionalAuth,
} from './redaction-commands.js';

// Defense-in-depth bounds for the redactor itself (issue #386, ARCH-386-01).
// These cap worst-case work at the secret boundary so a hostile or
// pathological artifact cannot turn redaction into a denial-of-service or a
// fail-open crash. Both bounds fail CLOSED (over-redact, never leak), matching
// the ADR-012 guardrail. Mirror any change in `redaction.py`.
//
// MAX_SCAN_LEN bounds the polynomial-backtracking command-flag passes (the
// `--<word>*<sensitive>` flag matcher and the per-segment shell scanners).
// Strings longer than this skip those passes (the linear key/value/header/
// PEM/bearer/URL passes still run), keeping CPU bounded.
const MAX_SCAN_LEN = 64 * 1024;
// MAX_DEPTH bounds recursion through nested objects/arrays/JSON-in-strings so
// a deeply nested artifact collapses to a bounded marker instead of
// overflowing the call stack. Matches the Python bound.
const MAX_DEPTH = 100;

// OBS-003 experimenter opt-out. The toggle is NOT consulted by the
// shared `redact()` primitive — that would disable redaction at
// every serialization boundary in the project (OTel/Tempo spans
// in `traceToolCall`, stderr OCSF lines, snapshot DTOs, CLI/API
// JSON), giving any lab/observability user with Tempo/Grafana
// access the ability to read raw control-plane secrets the moment
// an experimenter flips the env var (codex pre-push cycle 3
// finding-9). Instead, the toggle is consulted ONLY by the local
// per-run capture sink wrappers (`mcp-red/src/capture.ts`
// `captureToolCall`, `mcp-red/src/logger.ts` `localOcsfJsonlSink`,
// and any future experimental sink that explicitly opts in via
// the documented `experimentNoRedactActive()` helper). See ADR-033's
// "Secret-handling" Security Layers entry for the boundary contract.
const EXPERIMENT_NO_REDACT_ENV = 'APTL_EXPERIMENT_NO_REDACT';
const TRUTHY = new Set(['1', 'true', 'yes', 'on']);

/**
 * Public accessor for the OBS-003 experimenter opt-out env var.
 * Returns true only when `APTL_EXPERIMENT_NO_REDACT` is set to a
 * truthy value (`1`/`true`/`yes`/`on`, case-insensitive). Any other
 * value (including `0`, `false`, empty, or unset) returns false
 * (redaction-on default). This is the only sanctioned consumer of
 * the toggle — call it from a local per-run capture sink BEFORE
 * invoking `redact()`, and skip the redact call when it returns
 * true. Do NOT add a guard inside `redact()` itself.
 */
export function experimentNoRedactActive(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw = env[EXPERIMENT_NO_REDACT_ENV];
  if (raw === undefined) return false;
  return TRUTHY.has(raw.trim().toLowerCase());
}

// `pass` subsumes password/passwd/passphrase; `session` covers replayable
// session identifiers (Wazuh session_id, etc.). False-positive matches on
// unrelated tokens like `passport` are an acceptable cost — the ADR-012
// guardrail prefers over-redaction over leak.
const SENSITIVE_TOKENS: readonly string[] = [
  'pass',
  'secret',
  'token',
  'credential', // also matches "credentials"
  'authorization',
  'cookie',
  'jwt',
  'bearer',
  'api_key',
  'apikey',
  'key', // broad; carved out by SAFE_KEY_NAMES below
  'session',
  // Compose's service fingerprint includes resolved environment credentials.
  'com.docker.compose.config-hash',
];

// Tightened to names that are unambiguously paths/files: bare `ssh_key`
// could mean the private key material itself, so it is intentionally NOT
// in the allowlist.
const SAFE_KEY_NAMES: ReadonlySet<string> = new Set([
  'key_path',
  'key_file',
  'keypath',
  'keyfile',
  'ssh_key_path',
  'ssh_keyfile',
  'ssh_key_file',
  'public_key',
  'publickey',
]);

function isSensitiveKey(name: string): boolean {
  const lower = name.toLowerCase();
  if (SAFE_KEY_NAMES.has(lower)) return false;
  return SENSITIVE_TOKENS.some((token) => lower.includes(token));
}

function safeModelCount(name: string, value: unknown): boolean {
  if (!['max_output_tokens', 'input_tokens', 'output_tokens'].includes(name)) return false;
  if (value === null || (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)) return true;
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  const allowed = ['target_id', 'value_type', 'allowed_value_kinds', 'sensitivity', 'aliases', 'default'];
  const fallback = item.default as Record<string, unknown> | undefined;
  return Object.keys(item).every((key) => allowed.includes(key))
    && item.target_id === name && item.value_type === 'integer'
    && Array.isArray(item.allowed_value_kinds) && item.allowed_value_kinds.length === 1 && item.allowed_value_kinds[0] === 'literal'
    && ['public', 'internal'].includes(item.sensitivity as string)
    && (fallback === undefined || (fallback !== null && typeof fallback === 'object' && fallback.kind === 'literal'
      && typeof fallback.value === 'number' && Number.isSafeInteger(fallback.value) && fallback.value >= 0));
}

// Inline-secret patterns for plain-text strings (command lines, HTTP
// headers, query strings, etc.). MCP tool args/responses regularly carry
// these — a key-only redactor cannot reach inside string values like
// `command: "curl -H 'Authorization: Bearer abc' ..."` or
// `body: "password=hunter2&user=alice"`. Patterns are intentionally
// conservative: they preserve the labelling token (`Bearer`, `password=`)
// so log readers know what was redacted, but mask the secret payload.
const SENSITIVE_KEY_PATTERN =
  String.raw`(?:pass(?:word|wd|phrase)?|secret|token|credential|api[_-]?key|apikey|jwt|bearer|session(?:_id)?|cookie|com\.docker\.compose\.config-hash)`;
// `\S+` would greedily consume trailing quotes/punctuation around the
// secret value (e.g. eat the closing `'` of a curl `-H 'Authorization: ...'`
// header, corrupting downstream diagnostic structure). Stop at quotes
// and whitespace instead.
const VALUE_PATTERN = String.raw`[^\s'"]+`;
// Authorization header: keep optional scheme (`Basic`, `Bearer`) labelled
// for log-readability, mask the token. Single combined pattern so the
// optional-scheme branch and the value-only branch are mutually exclusive
// (avoids a double-redaction artifact on the same input).
// `i` flag handles both cases — listing `A-Z` alongside `a-z` is
// redundant under case-insensitive matching (Sonar S5869).
const AUTHORIZATION_PATTERN = new RegExp(
  String.raw`(authorization\s*[:=]\s*)(?:([a-z][\w-]*)\s+)?${VALUE_PATTERN}`,
  'gi',
);
// `\b` word-boundaries break on compound names because `_` is a word
// character — `access_token=...` matches neither `\btoken\b` nor
// `\baccess_token\b`. Use alphanumeric-only boundaries so `_`, `-`, and
// punctuation all count as separators.
const KEY_LB = String.raw`(?<![a-zA-Z0-9])`;
const KEY_RB = String.raw`(?![a-zA-Z0-9])`;
// `key=value` or `key: value` for any sensitive token. Stops at common
// delimiters so URL query strings and shell key/value pairs mask only
// the value, not the surrounding context. Capture leading and trailing
// quotes as separate groups so the replacement preserves them
// (otherwise wrapping `'<value>'` / `"<value>"` loses the closing
// quote, corrupting downstream diagnostic structure).
const SENSITIVE_KV_PATTERN = new RegExp(
  String.raw`(${KEY_LB}${SENSITIVE_KEY_PATTERN}${KEY_RB}\s*[=:]\s*['"]?)([^'"&\s,;|]+)(['"]?)`,
  'gi',
);
// Bare `Bearer <token>` (no Authorization: prefix).
const BARE_BEARER_PATTERN = new RegExp(
  String.raw`(${KEY_LB}bearer\s+)${VALUE_PATTERN}`,
  'gi',
);
// `--password value` / `--client-secret value` / `--access-token value`
// style (long CLI flags). The `[\w-]*` prefix allows compound flag
// names; regex backtracking finds the embedded sensitive token.
const CLI_FLAG_PATTERN = new RegExp(
  String.raw`(--[\w-]*${SENSITIVE_KEY_PATTERN}${KEY_RB}\s+)${VALUE_PATTERN}`,
  'gi',
);
// Cookie / Set-Cookie header: redact the entire body so multi-segment
// cookies like `Cookie: lang=en; connect.sid=SECRET` are masked in one
// pass instead of leaving later segments intact. Capture the leading
// and trailing quotes (when present) as separate groups so the
// replacement can put them back — otherwise a wrapping `'...'` loses
// its closing quote.
const COOKIE_HEADER_PATTERN =
  /((?:set-cookie|cookie)\s*[:=]\s*['"]?)([^'"\r\n]+)(['"]?)/gi;
// URL userinfo: `scheme://user:password@host/path`. Preserve user (often
// useful for diagnostics) and mask the password segment.
const URL_USERINFO_PATTERN = /(:\/\/[^/:@\s]+:)[^@\s]+(@)/gi;
// PEM key/cert blocks (`-----BEGIN PRIVATE KEY----- … -----END PRIVATE KEY-----`).
// Multi-line with `[\s\S]` since `.` does not match newline by default;
// non-greedy so adjacent blocks are masked separately.
const PEM_BLOCK_PATTERN =
  /(-----BEGIN[^-]*-----)[\s\S]*?(-----END[^-]*-----)/g;
// Recognizes `--<sensitive>` (or compound `--client-secret`,
// `--access-token`) as a standalone token used by array-pair detection
// so adjacent positional values get redacted.
const CLI_FLAG_TOKEN_PATTERN = new RegExp(
  String.raw`^--[\w-]*${SENSITIVE_KEY_PATTERN}${KEY_RB}$`,
  'i',
);

function redactAuthorizationHeader(
  _match: string,
  prefix: string,
  scheme: string | undefined,
): string {
  return scheme ? `${prefix}${scheme} ${REDACTED}` : `${prefix}${REDACTED}`;
}

// Patterns applied sequentially via a static replace-table so the
// caller's cyclomatic / cognitive complexity stays bounded. Each entry
// is `[pattern, replacement]` where replacement is either a string or
// a replace callback.
type ReplaceEntry = [RegExp, string | ((...args: unknown[]) => string)];
// The quote-strip pre-pass that USED to live here was a global rewrite
// and corrupted non-option text (e.g. `echo '-p' hunter2` → `echo -p
// hunter2`, which then triggered `redactShortPasswordFlag`); it now
// lives inside `redactString` behind a segment-scoped tool gate. See
// `unquoteOptionsInCredentialSegments`.
// Linear, single-quantifier passes — ReDoS-safe at any input length and so
// run unconditionally. The polynomial-backtracking passes (CLI_FLAG_PATTERN
// and the per-segment command-flag chain) are length-gated in `redactString`.
const LINEAR_REDACTION_TABLE: ReplaceEntry[] = [
  // PEM blocks first so the surrounding markers stay verbatim.
  [PEM_BLOCK_PATTERN, `$1${REDACTED}$2`],
  // Authorization next so it wins over the more general patterns.
  [AUTHORIZATION_PATTERN, redactAuthorizationHeader as (...args: unknown[]) => string],
  [COOKIE_HEADER_PATTERN, `$1${REDACTED}$3`],
  [SENSITIVE_KV_PATTERN, `$1${REDACTED}$3`],
  [BARE_BEARER_PATTERN, `$1${REDACTED}`],
  [URL_USERINFO_PATTERN, `$1${REDACTED}$2`],
];

function tryRedactJsonString(value: string, depth: number): string | null {
  const trimmed = value.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed !== null && typeof parsed === 'object') {
      return JSON.stringify(redactInner(parsed, depth + 1));
    }
  } catch {
    // Fall through to inline-pattern scanning.
  }
  return null;
}

function redactString(value: string, depth: number): string {
  const jsonRedacted = tryRedactJsonString(value, depth);
  if (jsonRedacted !== null) return jsonRedacted;
  let out = value;
  for (const [pattern, replacement] of LINEAR_REDACTION_TABLE) {
    out = out.replaceAll(
      pattern,
      replacement as Parameters<typeof out.replaceAll>[1],
    );
  }
  // Polynomial-backtracking passes are length-gated to cap worst-case CPU at
  // the secret boundary (ARCH-386-01). Oversized strings skip them; the
  // linear passes above already masked the key/value/header/PEM/bearer/URL
  // secret shapes. Tool-context-aware short flags run last so the simpler
  // kv/flag patterns have first claim on overlapping shapes. The
  // segment-scoped quote-strip unquotes `'-X'`/`"-X"` option tokens *only*
  // within credential-bearing segments so `hydra '-p' hunter2` triggers the
  // per-flag matcher while `echo '-p' hunter2` is preserved verbatim.
  if (out.length <= MAX_SCAN_LEN) {
    out = out.replaceAll(CLI_FLAG_PATTERN, `$1${REDACTED}`);
    out = unquoteOptionsInCredentialSegments(out);
    out = redactShortPasswordFlag(out);
    out = redactNtlmHashFlag(out);
    out = redactLdapPasswordFlag(out);
    out = redactBasicAuthUser(out);
    out = redactImpacketPositionalAuth(out);
  }
  return out;
}

function redactArray(items: unknown[], depth: number): unknown[] {
  // Argv-shape detection: when the leading token is a credential-family
  // tool, mark indices whose values should be redacted as short-flag
  // credentials (-p/-H/-w/-u/-U). Without this, a structured
  // `args = ["hydra", "-p", "hunter2", ...]` payload bypasses the
  // short-flag redactors that only run on scalar command strings
  // (ADR-029 / codex review cycle 3, finding 2).
  const first = items[0];
  const leading = typeof first === 'string' ? first : '';
  const modes = argvCredentialModes(leading);
  const shortFlagSkip = argvShortFlagSkipIndices(items, modes);
  const out: unknown[] = [];
  let skipNext = false;
  for (let i = 0; i < items.length; i++) {
    if (skipNext) {
      out.push(REDACTED);
      skipNext = false;
      continue;
    }
    if (shortFlagSkip.has(i)) {
      out.push(REDACTED);
      continue;
    }
    out.push(redactInner(items[i], depth + 1));
    // Pair-form CLI args: ["--password", "hunter2"]. If this string is a
    // long-flag whose name is sensitive AND the next element is a string,
    // redact the next element as the value-of-flag.
    const item = items[i];
    if (
      typeof item === 'string' &&
      CLI_FLAG_TOKEN_PATTERN.test(item) &&
      i + 1 < items.length &&
      typeof items[i + 1] === 'string'
    ) {
      skipNext = true;
    }
  }
  return out;
}

/**
 * Return a JSON-serialization-safe copy of `value`.
 *
 * Recurses through plain objects and arrays. Replaces values whose
 * containing key is sensitive with the marker `[REDACTED]`. String values
 * are scanned for embedded credentials: JSON-encoded payloads are parsed
 * and recursively redacted; plain-text payloads are scanned for inline
 * `Authorization:`, `Bearer`, and `<sensitive_key>=value` patterns.
 *
 * Pure: never mutates the input.
 */
export function redact(value: unknown): unknown {
  // Does NOT consult `APTL_EXPERIMENT_NO_REDACT` (codex pre-push
  // cycle 3 finding-9). The experiment toggle is scoped to the
  // local per-run capture sinks only; callers that want
  // experimental-record semantics check `experimentNoRedactActive()`
  // themselves before invoking `redact`. This keeps OTel/Tempo,
  // runstore, snapshot, and stderr boundaries redacted at all
  // times regardless of the toggle.
  //
  // Recursion is depth-bounded and fails CLOSED — a structure deeper than
  // MAX_DEPTH collapses to `[REDACTED]` rather than overflowing the stack
  // (ARCH-386-01).
  return redactInner(value, 0);
}

function redactInner(value: unknown, depth: number): unknown {
  if (depth >= MAX_DEPTH) return REDACTED;
  if (Array.isArray(value)) {
    return redactArray(value, depth);
  }
  // Binary payloads (Buffer / typed arrays) are not JSON-serializable and may
  // carry secret material; decode and scan as a string so embedded
  // credentials are masked and the result is JSON-safe (mirrors the Python
  // bytes handling, ARCH-386-01 / redact-03). Checked before the generic
  // object branch, which would otherwise spread the bytes into an index map.
  if (value instanceof Uint8Array) {
    return redactString(Buffer.from(value).toString('utf-8'), depth);
  }
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = isSensitiveKey(k) && !safeModelCount(k, v) ? REDACTED : redactInner(v, depth + 1);
    }
    return out;
  }
  if (typeof value === 'string') {
    return redactString(value, depth);
  }
  return value;
}
