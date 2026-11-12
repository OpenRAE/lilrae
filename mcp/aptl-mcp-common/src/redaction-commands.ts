/** Shell-segment-aware credential redaction, without recursive serialization. */
import {
  REDACTED,
  CREDENTIAL_TOOL_REGEXES,
  BASIC_AUTH_SHORT_TOOL_REGEXES,
  QUOTED_OPTION_TOKEN_RE,
  SHORT_P_DQUOTE,
  SHORT_P_SQUOTE,
  SHORT_P_UNQUOTED,
  SHORT_P_ATTACHED_DQUOTE,
  SHORT_P_ATTACHED_SQUOTE,
  SHORT_P_ATTACHED_UNQUOTED,
  NTLM_HASH_DQUOTE,
  NTLM_HASH_SQUOTE,
  NTLM_HASH_UNQUOTED,
  NTLM_HASH_ATTACHED_DQUOTE,
  NTLM_HASH_ATTACHED_SQUOTE,
  NTLM_HASH_ATTACHED_UNQUOTED,
  NTLM_HASHES_DQUOTE,
  NTLM_HASHES_SQUOTE,
  NTLM_HASHES_UNQUOTED,
  HASH_TOOLS_RE,
  BASIC_AUTH_USER_DQUOTE,
  BASIC_AUTH_USER_SQUOTE,
  BASIC_AUTH_USER_UNQUOTED,
  BASIC_AUTH_USER_ATTACHED_DQUOTE,
  BASIC_AUTH_USER_ATTACHED_SQUOTE,
  BASIC_AUTH_USER_ATTACHED_UNQUOTED,
  LDAP_W_DQUOTE,
  LDAP_W_SQUOTE,
  LDAP_W_UNQUOTED,
  LDAP_W_ATTACHED_DQUOTE,
  LDAP_W_ATTACHED_SQUOTE,
  LDAP_W_ATTACHED_UNQUOTED,
  LDAP_TOOL_RE,
  URL_PREFIX_RE,
  IMPACKET_POSITIONAL_DQUOTE,
  IMPACKET_POSITIONAL_SQUOTE,
  IMPACKET_POSITIONAL_BARE,
  IMPACKET_TOOL_REGEXES,
  HASHES_FLAG_TOOL_REGEXES,
  ARGV_SHORT_FLAG_RULES,
} from './redaction-command-patterns.js';
import type { ArgvCredentialModes, ArgvValueTest } from './redaction-command-patterns.js';
import { ImpacketTargetPattern } from './redaction-targets.js';

// `&&` / `||` / `&` / `;` / `|` boundaries split a command line into
// independent shell segments (used for per-segment credential-tool
// detection so `-p 22` in an unrelated nmap segment doesn't get masked
// just because a hydra invocation appears after `&&`).
// independent shell segments. Per-flag credential-tool detection scans
// the segment containing the flag, so `nmap -p 22 ... && hydra -p X`
// keeps nmap's port visible while masking hydra's password.
interface SegmentScanState {
  inSingle: boolean;
  inDouble: boolean;
  escaped: boolean;
}

/**
 * Update quote/escape state for one character. Returns true if the
 * caller should skip emitting a separator at this position (because we
 * are inside a quoted run, in an escape, or just toggled a quote).
 */
function advanceQuoteState(state: SegmentScanState, ch: string): boolean {
  if (state.escaped) {
    state.escaped = false;
    return true;
  }
  if (ch === '\\') {
    state.escaped = true;
    return true;
  }
  if (!state.inDouble && ch === "'") {
    state.inSingle = !state.inSingle;
    return true;
  }
  if (!state.inSingle && ch === '"') {
    state.inDouble = !state.inDouble;
    return true;
  }
  return state.inSingle || state.inDouble;
}

function ampersandStep(command: string, i: number): number {
  const prev = command[i - 1];
  const next = command[i + 1];
  if (prev === '>' || prev === '<' || next === '>') return 0; // not a separator
  return next === '&' ? 2 : 1;
}

function splitTopLevelSegments(command: string): { start: number; end: number }[] {
  // Multi-character separators (`&&`, `||`) are consumed atomically —
  // the loop skips past the second character so the splitter never
  // emits a zero-width range. The earlier `for` loop revisited the
  // second `&`, which the new segment-reconstructor in
  // `unquoteOptionsInCredentialSegments` would emit as a stray `&`
  // between segments.
  const segments: { start: number; end: number }[] = [];
  let start = 0;
  const state: SegmentScanState = { inSingle: false, inDouble: false, escaped: false };
  let i = 0;
  const n = command.length;
  while (i < n) {
    const ch = command[i];
    if (advanceQuoteState(state, ch)) {
      i++;
      continue;
    }
    if (ch === '|' || ch === ';') {
      segments.push({ start, end: i });
      start = i + 1;
      i++;
      continue;
    }
    if (ch === '&') {
      const advance = ampersandStep(command, i);
      if (advance > 0) {
        segments.push({ start, end: i });
        start = i + advance;
        i += advance;
        continue;
      }
    }
    i++;
  }
  segments.push({ start, end: command.length });
  return segments;
}

function segmentHasCredentialTool(segment: string): boolean {
  return CREDENTIAL_TOOL_REGEXES.some((re) => re.test(segment));
}

function segmentHasBasicAuthShortTool(segment: string): boolean {
  return BASIC_AUTH_SHORT_TOOL_REGEXES.some((re) => re.test(segment));
}

// True when the segment names ANY credential-bearing tool family —
// used by the segment-scoped quote-strip below so an option-shaped
// token like `'-p'` is only normalized to bare `-p` when the segment
// is plausibly running a credential-using tool. References to
// per-family tool detectors below are hoisted via function
// declarations; the regex tables they use are initialized at module
// load before any consumer can call this.
function segmentHasAnyCredentialTool(segment: string): boolean {
  return (
    segmentHasCredentialTool(segment) ||
    segmentHasHashTool(segment) ||
    segmentHasLdapTool(segment) ||
    segmentHasImpacketTool(segment) ||
    segmentHasBasicAuthShortTool(segment)
  );
}

/**
 * Strip surrounding quotes from `'-X'` / `"-X"` option tokens — but
 * only inside segments that name a credential-bearing tool. The
 * earlier implementation ran this pre-pass globally, which mutated
 * arbitrary data (`echo '-p' hunter2` became `echo -p hunter2`, then
 * `redactShortPasswordFlag` redacted the trailing word as if it were
 * a password). Scoping the strip to credential-bearing segments
 * keeps the original `hydra '-p' hunter2` parity (hydra's segment
 * unquotes, the per-flag matcher fires) while leaving non-credential
 * text intact. `context` has the meaning that `buildSegmentPredicate`
 * gives it.
 */
export function unquoteOptionsInCredentialSegments(command: string, context = ''): string {
  if (!command.includes("'") && !command.includes('"')) return command;
  const segments = splitTopLevelSegments(command);
  const contextHit = context !== '' && segmentHasAnyCredentialTool(context);
  const parts: string[] = [];
  let lastEnd = 0;
  for (const { start, end } of segments) {
    if (start > lastEnd) parts.push(command.slice(lastEnd, start));
    let seg = command.slice(start, end);
    if (contextHit || segmentHasAnyCredentialTool(seg)) {
      seg = seg.replace(QUOTED_OPTION_TOKEN_RE, '$2');
    }
    parts.push(seg);
    lastEnd = end;
  }
  if (lastEnd < command.length) parts.push(command.slice(lastEnd));
  return parts.join('');
}

function isPortLikeValue(stripped: string): boolean {
  // Comma- or hyphen-separated digits (with each segment ≤ 5 digits).
  return /^\d{1,5}(?:[,-]\d{1,5})*$/.test(stripped);
}

function stripQuotes(value: string): string {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

/**
 * Build an offset-to-bool predicate from the *current* command string.
 *
 * The earlier implementation computed segments once on the input and
 * reused those offsets across six sequential `.replace()` passes that
 * mutated the string between calls — once a quoted credential of a
 * length other than `[REDACTED]` was replaced, later offsets shifted
 * and could mis-classify matches into the wrong segment (e.g. a long
 * hydra password before `&& nmap -p 22` would shift the port match
 * leftwards into the hydra segment and mask `22`). Recompute per pass
 * via `segmentAwareReplace` instead. `context` is the leading token of
 * the command that `command` is an argument of, for example the tool of
 * an argv list. When it names a tool of the family, every segment matches.
 */
function buildSegmentPredicate(
  command: string,
  hasTool: (segment: string) => boolean,
  context: string,
): (offset: number) => boolean {
  const segments = splitTopLevelSegments(command);
  const contextHit = context !== '' && hasTool(context);
  const flags = segments.map((s) => contextHit || hasTool(command.slice(s.start, s.end)));
  return (offset: number): boolean => {
    // Binary search: the segments are ordered and do not overlap.
    let lo = 0;
    let hi = segments.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (offset < segments[mid].start) hi = mid - 1;
      else if (offset >= segments[mid].end) lo = mid + 1;
      else return flags[mid];
    }
    return false;
  };
}

/** Return `buildSegmentPredicate` built at its first call: most text has no flag match. */
function lazySegmentPredicate(
  command: string,
  hasTool: (segment: string) => boolean,
  context: string,
): (offset: number) => boolean {
  let built: ((offset: number) => boolean) | undefined;
  return (offset: number): boolean => {
    built ??= buildSegmentPredicate(command, hasTool, context);
    return built(offset);
  };
}

/**
 * Run a sequence of segment-aware regex replacements safely.
 *
 * Each pass recomputes the segment predicate against the *current*
 * string before invoking `.replace()` — `.replace()`'s own match
 * offsets are consistent within a single call, so this is sufficient
 * to keep classification stable across replacements.
 *
 * `replacerFactory(inSeg)` returns the actual `String.replace` callback;
 * the factory closes over the freshly-computed predicate for that pass.
 */
type Replacer = (...args: unknown[]) => string;

/** Replace each match of `pattern`, giving `replacer` the arguments of a regex replacer. */
function replaceMatches(text: string, pattern: RegExp | ImpacketTargetPattern, replacer: Replacer): string {
  if (pattern instanceof RegExp) return text.replace(pattern, replacer as Parameters<typeof text.replace>[1]);
  return pattern.replace(text, (t) => replacer(t.match, t.user, t.value, t.host, t.offset));
}

function segmentAwareReplace(
  command: string,
  hasTool: (segment: string) => boolean,
  passes: ReadonlyArray<[RegExp | ImpacketTargetPattern, (inSeg: (offset: number) => boolean) => Replacer]>,
  context: string,
): string {
  let out = command;
  let scanned: string | undefined;
  let inSeg = lazySegmentPredicate(out, hasTool, context);
  for (const [pattern, factory] of passes) {
    // The predicate is a function of the text alone: build it again only
    // after a pass changed the text.
    if (out !== scanned) {
      inSeg = lazySegmentPredicate(out, hasTool, context);
      scanned = out;
    }
    out = replaceMatches(out, pattern, factory(inSeg));
  }
  return out;
}

/**
 * Mask short `-p <value>` credential flags inline in `command`.
 *
 * Behaviour:
 *  - When the command's leading tokens include a known credential tool
 *    (hydra, sshpass, medusa, etc., or a wrapper pipeline that contains
 *    one), redact the value regardless of shape — numeric passwords are
 *    common.
 *  - Otherwise, only redact non-numeric `-p` values so `nmap -p 22`,
 *    `nmap -p 22,80,443`, and `nmap -p 1-1024` (port specs) stay visible.
 *
 * Recognises spaced (`-p value`), equals (`-p=value`), and attached
 * (`-p<value>`) shell forms; preserves leading whitespace/pipe so the
 * surrounding context isn't broken.
 */
export function redactShortPasswordFlag(command: string, context = ''): string {
  const makeReplaceSpaced = (inCred: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const lead = args[1] as string;
      const sep = args[2] as string;
      const value = args[3] as string;
      const offset = args[4] as number;
      const stripped = stripQuotes(value);
      if (!inCred(offset) && isPortLikeValue(stripped)) {
        return `${lead}-p${sep}${value}`;
      }
      return `${lead}-p${sep}${REDACTED}`;
    };
  const makeReplaceAttached = (inCred: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const lead = args[1] as string;
      const value = args[2] as string;
      const offset = args[3] as number;
      const stripped = stripQuotes(value);
      if (!inCred(offset) && isPortLikeValue(stripped)) {
        return `${lead}-p${value}`;
      }
      return `${lead}-p ${REDACTED}`;
    };
  return segmentAwareReplace(command, segmentHasCredentialTool, [
    [SHORT_P_DQUOTE, makeReplaceSpaced],
    [SHORT_P_SQUOTE, makeReplaceSpaced],
    [SHORT_P_UNQUOTED, makeReplaceSpaced],
    [SHORT_P_ATTACHED_DQUOTE, makeReplaceAttached],
    [SHORT_P_ATTACHED_SQUOTE, makeReplaceAttached],
    [SHORT_P_ATTACHED_UNQUOTED, makeReplaceAttached],
  ], context);
}

function segmentHasHashTool(segment: string): boolean {
  return HASH_TOOLS_RE.test(segment);
}

function segmentHasHashesFlagTool(segment: string): boolean {
  return HASHES_FLAG_TOOL_REGEXES.some((re) => re.test(segment));
}

export function redactNtlmHashFlag(command: string, context = ''): string {
  const makeReplaceSpaced = (inSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const lead = args[1] as string;
      const sep = args[2] as string;
      const offset = args[4] as number;
      return inSeg(offset) ? `${lead}-H${sep}${REDACTED}` : match;
    };
  const makeReplaceAttached = (inSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const lead = args[1] as string;
      const offset = args[3] as number;
      return inSeg(offset) ? `${lead}-H ${REDACTED}` : match;
    };
  // `-hashes`/`--hashes` (full-word impacket form). Preserves the
  // flag literal (`m[2]` is `-hashes` or `--hashes`) and only masks
  // the value (m[4]).
  const makeReplaceHashes = (inSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const lead = args[1] as string;
      const flag = args[2] as string;
      const sep = args[3] as string;
      const offset = args[5] as number;
      return inSeg(offset) ? `${lead}${flag}${sep}${REDACTED}` : match;
    };
  const out = segmentAwareReplace(command, segmentHasHashTool, [
    [NTLM_HASH_DQUOTE, makeReplaceSpaced],
    [NTLM_HASH_SQUOTE, makeReplaceSpaced],
    [NTLM_HASH_UNQUOTED, makeReplaceSpaced],
    [NTLM_HASH_ATTACHED_DQUOTE, makeReplaceAttached],
    [NTLM_HASH_ATTACHED_SQUOTE, makeReplaceAttached],
    [NTLM_HASH_ATTACHED_UNQUOTED, makeReplaceAttached],
  ], context);
  return segmentAwareReplace(out, segmentHasHashesFlagTool, [
    [NTLM_HASHES_DQUOTE, makeReplaceHashes],
    [NTLM_HASHES_SQUOTE, makeReplaceHashes],
    [NTLM_HASHES_UNQUOTED, makeReplaceHashes],
  ], context);
}
function segmentHasLdapTool(segment: string): boolean {
  return LDAP_TOOL_RE.test(segment);
}
export function redactLdapPasswordFlag(command: string, context = ''): string {
  const makeReplaceSpaced = (inSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const lead = args[1] as string;
      const sep = args[2] as string;
      const offset = args[4] as number;
      return inSeg(offset) ? `${lead}-w${sep}${REDACTED}` : match;
    };
  const makeReplaceAttached = (inSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const lead = args[1] as string;
      const offset = args[3] as number;
      return inSeg(offset) ? `${lead}-w ${REDACTED}` : match;
    };
  return segmentAwareReplace(command, segmentHasLdapTool, [
    [LDAP_W_DQUOTE, makeReplaceSpaced],
    [LDAP_W_SQUOTE, makeReplaceSpaced],
    [LDAP_W_UNQUOTED, makeReplaceSpaced],
    [LDAP_W_ATTACHED_DQUOTE, makeReplaceAttached],
    [LDAP_W_ATTACHED_SQUOTE, makeReplaceAttached],
    [LDAP_W_ATTACHED_UNQUOTED, makeReplaceAttached],
  ], context);
}

function basicAuthValueIsCredential(value: string): boolean {
  const stripped = stripQuotes(value);
  if (URL_PREFIX_RE.test(stripped)) return false;
  return stripped.includes('%') || stripped.includes(':');
}

export function redactBasicAuthUser(command: string, context = ''): string {
  // Long `--user` is content-only — overwhelmingly auth-bearing across
  // tools. Short `-u`/`-U` are tool-scoped to avoid `date -u +%Y:%m`,
  // `grep -u alice:other file`, etc., where those flags don't carry
  // auth values.
  const makeReplaceSpaced = (inShortSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const lead = args[1] as string;
      const flag = args[2] as string;
      const sep = args[3] as string;
      const value = args[4] as string;
      const offset = args[5] as number;
      if (!basicAuthValueIsCredential(value)) return match;
      if ((flag === '-u' || flag === '-U') && !inShortSeg(offset)) return match;
      return `${lead}${flag}${sep}${REDACTED}`;
    };
  const makeReplaceAttached = (inShortSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const lead = args[1] as string;
      const flag = args[2] as string;
      const value = args[3] as string;
      const offset = args[4] as number;
      if (!basicAuthValueIsCredential(value)) return match;
      // Attached forms only fire on `-u`/`-U` by construction, so the
      // tool-segment gate always applies.
      if (!inShortSeg(offset)) return match;
      return `${lead}${flag} ${REDACTED}`;
    };
  return segmentAwareReplace(command, segmentHasBasicAuthShortTool, [
    [BASIC_AUTH_USER_DQUOTE, makeReplaceSpaced],
    [BASIC_AUTH_USER_SQUOTE, makeReplaceSpaced],
    [BASIC_AUTH_USER_UNQUOTED, makeReplaceSpaced],
    [BASIC_AUTH_USER_ATTACHED_DQUOTE, makeReplaceAttached],
    [BASIC_AUTH_USER_ATTACHED_SQUOTE, makeReplaceAttached],
    [BASIC_AUTH_USER_ATTACHED_UNQUOTED, makeReplaceAttached],
  ], context);
}
function segmentHasImpacketTool(segment: string): boolean {
  return IMPACKET_TOOL_REGEXES.some((re) => re.test(segment));
}

export function redactImpacketPositionalAuth(command: string, context = ''): string {
  const makeReplace = (inSeg: (offset: number) => boolean) =>
    (...args: unknown[]): string => {
      const match = args[0] as string;
      const user = args[1] as string;
      const host = args[3] as string;
      const offset = args[4] as number;
      return inSeg(offset) ? `${user}:${REDACTED}@${host}` : match;
    };
  return segmentAwareReplace(command, segmentHasImpacketTool, [
    [IMPACKET_POSITIONAL_DQUOTE, makeReplace],
    [IMPACKET_POSITIONAL_SQUOTE, makeReplace],
    [IMPACKET_POSITIONAL_BARE, makeReplace],
  ], context);
}

export function argvCredentialModes(leading: string): ArgvCredentialModes {
  if (!leading) return { cred: false, hash: false, hashes: false, ldap: false, basic: false };
  return {
    cred: segmentHasCredentialTool(leading),
    hash: segmentHasHashTool(leading),
    hashes: segmentHasHashesFlagTool(leading),
    ldap: segmentHasLdapTool(leading),
    basic: segmentHasBasicAuthShortTool(leading),
  };
}

function argvValueShouldMask(test: ArgvValueTest, value: string, modes: ArgvCredentialModes): boolean {
  if (test === 'credentialPair') return basicAuthValueIsCredential(value);
  if (test === 'notPortOutsideCredentialTool') return modes.cred || !isPortLikeValue(stripQuotes(value));
  return true;
}

function isArgvShortFlagTarget(
  flag: string,
  value: string,
  modes: ArgvCredentialModes,
): boolean {
  for (const { flags, mode, test } of ARGV_SHORT_FLAG_RULES) {
    if (!flags.has(flag) || (mode !== null && !modes[mode])) continue;
    return argvValueShouldMask(test, value, modes);
  }
  return false;
}

export function argvShortFlagSkipIndices(
  items: ReadonlyArray<unknown>,
  modes: ArgvCredentialModes,
): Set<number> {
  const skip = new Set<number>();
  for (let i = 0; i + 1 < items.length; i++) {
    const flag = items[i];
    const value = items[i + 1];
    if (typeof flag !== 'string' || typeof value !== 'string') continue;
    if (isArgvShortFlagTarget(flag, value, modes)) skip.add(i + 1);
  }
  return skip;
}

/**
 * Apply the tool-context-aware command-line redactors in order.
 *
 * The leading segment-scoped quote-strip unquotes `'-X'`/`"-X"` option
 * tokens only within credential-bearing segments, so `hydra '-p' hunter2`
 * triggers the per-flag matcher while `echo '-p' hunter2` is preserved
 * verbatim. `context` is the leading token of the command that `value` is
 * an argument of, for example the tool of an argv list; it scopes every
 * shell segment.
 */
export function redactCommandFlags(value: string, context = ''): string {
  let out = unquoteOptionsInCredentialSegments(value, context);
  out = redactShortPasswordFlag(out, context);
  out = redactNtlmHashFlag(out, context);
  out = redactLdapPasswordFlag(out, context);
  out = redactBasicAuthUser(out, context);
  out = redactImpacketPositionalAuth(out, context);
  return out;
}
