/**
 * Linear matcher for impacket positional `user:password@host` targets.
 *
 * It finds the matches of these patterns, in the order that `String.replace`
 * with a global regex finds them:
 *
 *   (?<![\w\\/.:@-])([\w\\/.-]+):"([^"\\]*(?:\\.[^"\\]*)*)"@([\w.-]+)(?=\s|$|[;|&])
 *   (?<![\w\\/.:@-])([\w\\/.-]+):'([^'\\]*(?:\\.[^'\\]*)*)'@([\w.-]+)(?=\s|$|[;|&])
 *   (?<![\w\\/.:@-])([\w\\/.-]+):((?:\\.|[^\\@\s])+)@([\w.-]+)(?=\s|$|[;|&])
 *
 * The regex engine scanned the value again from each candidate start, which
 * is quadratic on text such as `u:x!u:x!...`. Each part of a target here has
 * one possible extent, so the scan keeps the end of each value it has found
 * and stays linear. Mirrors `_redaction_targets.py`.
 */

/** The groups of one target, as a regex match gives them to a replacer. */
export interface TargetMatch {
  match: string;
  user: string;
  value: string;
  host: string;
  offset: number;
}

// JavaScript `\w` without the `u` flag is ASCII, as in the former regexes.
const WORD = /\w/;
const SPACE = /\s/;
const LINE_TERMINATORS = '\n\r\u2028\u2029';

function isUser(ch: string): boolean {
  return WORD.test(ch) || String.raw`\/.-`.includes(ch);
}

function isHost(ch: string): boolean {
  return WORD.test(ch) || '.-'.includes(ch);
}

/** The lookahead `(?=\s|$|[;|&])` after the host. */
function endsTarget(text: string, index: number): boolean {
  return index === text.length || SPACE.test(text[index]) || ';|&'.includes(text[index]);
}

/** One value form of an impacket positional target: `"`, `'`, or bare (``). */
export class ImpacketTargetPattern {
  constructor(private readonly quote: string) {}

  /** Replace each match as `String.replace` with a global regex does. */
  replace(text: string, replacer: (target: TargetMatch) => string): string {
    const parts: string[] = [];
    let cursor = 0;
    for (const target of this.matches(text)) {
      parts.push(text.slice(cursor, target.offset), replacer(target));
      cursor = target.offset + target.match.length;
    }
    parts.push(text.slice(cursor));
    return parts.join('');
  }

  private matches(text: string): TargetMatch[] {
    const found: TargetMatch[] = [];
    const ends = new Map<number, number>();
    let index = 0;
    while (index < text.length) {
      // The lookbehind rejects a start after a user character, so only the
      // first character of a run of user characters can start.
      const previous = index > 0 ? text[index - 1] : '';
      if (!isUser(text[index]) || (previous !== '' && (isUser(previous) || ':@'.includes(previous)))) {
        index += 1;
        continue;
      }
      let userEnd = index;
      while (userEnd < text.length && isUser(text[userEnd])) userEnd += 1;
      const target = this.matchAt(text, index, userEnd, ends);
      if (target === null) {
        index = userEnd;
      } else {
        found.push(target);
        index = target.offset + target.match.length;
      }
    }
    return found;
  }

  private matchAt(text: string, start: number, userEnd: number, ends: Map<number, number>): TargetMatch | null {
    if (text[userEnd] !== ':') return null;
    let valueStart: number;
    let valueEnd: number;
    let at: number;
    if (this.quote === '') {
      valueStart = userEnd + 1;
      valueEnd = this.valueEnd(text, valueStart, ends);
      if (valueEnd === valueStart) return null;
      at = valueEnd;
    } else {
      valueStart = userEnd + 2;
      if (text[userEnd + 1] !== this.quote) return null;
      valueEnd = this.valueEnd(text, valueStart, ends);
      if (valueEnd < 0) return null;
      at = valueEnd + 1;
    }
    if (text[at] !== '@') return null;
    let hostEnd = at + 1;
    while (hostEnd < text.length && isHost(text[hostEnd])) hostEnd += 1;
    if (hostEnd === at + 1 || !endsTarget(text, hostEnd)) return null;
    return {
      match: text.slice(start, hostEnd),
      user: text.slice(start, userEnd),
      value: text.slice(valueStart, valueEnd),
      host: text.slice(at + 1, hostEnd),
      offset: start,
    };
  }

  /**
   * Return where the value that starts at `start` stops. A quoted value stops
   * at its closing quote, or at -1 when it has none. A bare value stops before
   * `@`, white space, or a backslash with no escaped character. `ends` keeps
   * each result, so a later candidate does not scan the same characters again.
   */
  private valueEnd(text: string, start: number, ends: Map<number, number>): number {
    const path: number[] = [];
    let index = start;
    while (!ends.has(index)) {
      const step = this.step(text, index);
      if (step <= 0) {
        ends.set(index, step === 0 ? index : -1);
        break;
      }
      path.push(index);
      index += step;
    }
    const end = ends.get(index) as number;
    for (const visited of path) ends.set(visited, end);
    return end;
  }

  /** Code units that one value unit at `index` holds; 0 stops, -1 fails. */
  private step(text: string, index: number): number {
    if (index >= text.length) return this.quote === '' ? 0 : -1;
    const ch = text[index];
    if (ch === '\\') {
      // `.` matches no line terminator: \n, \r, U+2028, or U+2029.
      if (index + 1 < text.length && !LINE_TERMINATORS.includes(text[index + 1])) return 2;
      return this.quote === '' ? 0 : -1;
    }
    if (this.quote !== '') return ch === this.quote ? 0 : 1;
    return ch === '@' || SPACE.test(ch) ? 0 : 1;
  }
}
