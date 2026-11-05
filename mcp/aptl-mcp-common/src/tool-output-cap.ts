/**
 * One size limit on tool results, the same for every MCP server.
 *
 * An agent re-reads each tool result on every later turn of its conversation.
 * One oversized result, such as a 50 KB alert or execution listing, therefore
 * costs input tokens on every turn. A client that compacts its context to make
 * room also changes the prompt prefix, which defeats provider prompt caching.
 *
 * A text result over the budget that is a JSON object stays valid JSON:
 *
 * 1. Whole records are dropped from the end of its largest array.
 * 2. When not even one record fits, or the object has no array, its long
 *    strings, such as command output or file content, are cut at a line
 *    boundary. Every string over one shared length is cut to that length, so
 *    the short fields beside them, such as exit codes, stay in the result.
 *
 * A `_truncated` tail, the last key of the object, gives the counts. Other
 * text, and an object that does not fit even with empty strings, is cut at a
 * line boundary with a size tail. The tails and the log carry counts and sizes
 * only, never result content or the supplied query (#1273 preflight).
 */
import { type LabConfig } from './config.js';

/** Default budget for one tool result, in estimated tokens. */
export const DEFAULT_MAX_TOOL_RESULT_TOKENS = 4000;

// A conservative estimate for JSON and command output.
const CHARS_PER_TOKEN = 4;

/** A tool result budget in estimated tokens. `null` returns the whole result. */
export type ResultBudget = number | null;

type ResultPart = { type: string; text: string };

/** The tool result shape every handler returns. */
export interface ToolResult {
  content: ResultPart[];
  // The MCP SDK's CallTool result type is open to further fields.
  [field: string]: unknown;
}

/** A bounded tool result and the sizes the tool-call log records. */
export interface BoundedToolResult<T extends ToolResult> {
  result: T;
  originalChars: number;
  returnedChars: number;
  truncated: boolean;
}

interface RecordList {
  holder: Record<string, unknown>;
  key: string;
  items: unknown[];
}

/** One string value of a parsed result and how to replace it in place. */
interface StringSlot {
  value: string;
  replace: (text: string) => void;
}

/** How many records or characters a result kept out of its total. */
interface Counts {
  returned: number;
  total: number;
}

/**
 * Return the budget of each tool: its query's `max_result_tokens` when the
 * query sets one, else the server's `maxToolResultTokens`, else the default.
 */
export function toolResultBudgets(labConfig: LabConfig): (toolName: string) => ResultBudget {
  const serverBudget = labConfig.server.maxToolResultTokens ?? DEFAULT_MAX_TOOL_RESULT_TOKENS;
  const queryBudgets = new Map<string, ResultBudget>();
  for (const [queryName, query] of Object.entries(labConfig.queries ?? {})) {
    if (query.max_result_tokens !== undefined) {
      queryBudgets.set(`${labConfig.server.toolPrefix}_${queryName}`, query.max_result_tokens);
    }
  }
  return (toolName) => {
    const budget = queryBudgets.get(toolName);
    return budget === undefined ? serverBudget : budget;
  };
}

/**
 * Return ``result`` with each text part cut to ``maxTokens``. A result within
 * the budget, or with a `null` budget, is returned as the same object.
 */
export function boundToolResult<T extends ToolResult>(
  result: T,
  maxTokens: ResultBudget,
): BoundedToolResult<T> {
  const limit = maxTokens === null ? Infinity : maxTokens * CHARS_PER_TOKEN;
  let originalChars = 0;
  let returnedChars = 0;
  let truncated = false;
  const content = (Array.isArray(result?.content) ? result.content : []).map((part) => {
    if (part.type !== 'text' || typeof part.text !== 'string') {
      return part;
    }
    originalChars += part.text.length;
    const text = part.text.length > limit ? boundText(part.text, limit) : part.text;
    returnedChars += text.length;
    if (text === part.text) {
      return part;
    }
    truncated = true;
    return { ...part, text };
  });
  return {
    result: truncated ? { ...result, content } : result,
    originalChars,
    returnedChars,
    truncated,
  };
}

function boundText(text: string, limit: number): string {
  const root = parseObject(text);
  const bounded = root === undefined ? undefined : boundObject(root, limit);
  return bounded ?? cutText(text, limit);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseObject(text: string): Record<string, unknown> | undefined {
  try {
    const parsed: unknown = JSON.parse(text);
    return isObject(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Cut a parsed JSON object to ``limit`` and keep it valid JSON. Return
 * undefined when the object does not fit even with every string empty.
 */
function boundObject(root: Record<string, unknown>, limit: number): string | undefined {
  const list = largestArray(root);
  if (list === undefined) {
    return cutStrings(root, limit);
  }
  const fitting = trimRecords(root, list, limit);
  if (fitting !== undefined) {
    return fitting;
  }
  // Not even one whole record fits: keep the first and cut its long strings.
  list.holder[list.key] = list.items.slice(0, 1);
  const records = list.items.length > 1 ? { returned: 1, total: list.items.length } : undefined;
  return cutStrings(root, limit, records);
}

/**
 * Drop whole records from the end of the list until the result fits. Return
 * undefined when not even one record fits: an empty list tells the agent
 * nothing.
 */
function trimRecords(root: Record<string, unknown>, list: RecordList, limit: number): string | undefined {
  const { holder, key, items } = list;
  const render = (kept: number): string => {
    holder[key] = items.slice(0, kept);
    return renderWithTail(root, truncationTail({ returned: kept, total: items.length }));
  };
  return longestFitting(1, items.length - 1, render, limit);
}

/**
 * Cut every string longer than one shared length at a line boundary, and use
 * the largest length at which the result fits. Return undefined when the
 * result does not fit even with every string empty.
 */
function cutStrings(root: Record<string, unknown>, limit: number, records?: Counts): string | undefined {
  const slots = stringSlots(root);
  const longest = slots.reduce((max, slot) => Math.max(max, slot.value.length), 0);
  const render = (length: number): string => {
    const characters: Counts = { returned: 0, total: 0 };
    for (const slot of slots) {
      const text = slot.value.length > length ? cutAtLine(slot.value, length) : slot.value;
      if (text !== slot.value) {
        characters.returned += text.length;
        characters.total += slot.value.length;
      }
      slot.replace(text);
    }
    return renderWithTail(root, truncationTail(records, characters));
  };
  return longestFitting(0, longest - 1, render, limit);
}

/**
 * Return the longest rendering within ``limit``: the one for the largest value
 * from ``low`` to ``high`` that fits. A rendering grows with its value.
 */
function longestFitting(
  low: number,
  high: number,
  render: (value: number) => string,
  limit: number,
): string | undefined {
  let fitting: string | undefined;
  let lower = low;
  let upper = high;
  while (lower <= upper) {
    const value = Math.floor((lower + upper) / 2);
    const text = render(value);
    if (text.length <= limit) {
      fitting = text;
      lower = value + 1;
    } else {
      upper = value - 1;
    }
  }
  return fitting;
}

/** Build the `_truncated` tail from the records and characters left out. */
function truncationTail(records?: Counts, characters?: Counts): Record<string, unknown> {
  const tail: Record<string, unknown> = {};
  const omitted: string[] = [];
  if (records !== undefined) {
    tail.returned = records.returned;
    tail.total = records.total;
    omitted.push(`${records.total - records.returned} more results`);
  }
  if (characters !== undefined) {
    tail.returned_characters = characters.returned;
    tail.total_characters = characters.total;
    omitted.push(`${characters.total - characters.returned} more characters`);
  }
  tail.note = `${omitted.join('; ')}; refine your query`;
  return tail;
}

/** Render the object as the handlers do, with the tail as its last key. */
function renderWithTail(root: Record<string, unknown>, tail: Record<string, unknown>): string {
  return JSON.stringify({ ...root, _truncated: tail }, null, 2);
}

/** The non-empty array that takes the most bytes: the result's record list. */
function largestArray(root: Record<string, unknown>): RecordList | undefined {
  let largest: RecordList | undefined;
  let largestSize = 0;
  const visit = (node: Record<string, unknown>): void => {
    for (const [key, value] of Object.entries(node)) {
      if (Array.isArray(value)) {
        const size = JSON.stringify(value).length;
        if (value.length > 0 && size > largestSize) {
          largest = { holder: node, key, items: value };
          largestSize = size;
        }
      } else if (isObject(value)) {
        visit(value);
      }
    }
  };
  visit(root);
  return largest;
}

/** Every string value in the object, in objects and arrays at any depth. */
function stringSlots(root: Record<string, unknown>): StringSlot[] {
  const slots: StringSlot[] = [];
  collectStrings(root, slots);
  return slots;
}

function collectStrings(container: Record<string, unknown> | unknown[], slots: StringSlot[]): void {
  const holder = container as Record<string, unknown>;
  for (const key of Object.keys(holder)) {
    const value = holder[key];
    if (typeof value === 'string') {
      slots.push({ value, replace: (text) => { holder[key] = text; } });
    } else if (Array.isArray(value) || isObject(value)) {
      collectStrings(value, slots);
    }
  }
}

/**
 * Cut ``text`` to at most ``length`` characters at its last line break. A
 * break in the first half of the kept text is not used, so one long line
 * still shows at least half the room. A surrogate pair is never split.
 */
function cutAtLine(text: string, length: number): string {
  let end = Math.max(0, Math.min(length, text.length));
  // A code point above U+FFFF that starts at end - 1 is a surrogate pair
  // that a cut at end would split.
  if (end > 0 && end < text.length && (text.codePointAt(end - 1) ?? 0) > 0xffff) {
    end -= 1;
  }
  const head = text.slice(0, end);
  if (end === text.length || text[end] === '\n') {
    return head;
  }
  const lineEnd = head.lastIndexOf('\n');
  return lineEnd >= head.length / 2 ? head.slice(0, lineEnd) : head;
}

/** Cut text that cannot stay JSON at a line boundary, with a size tail. */
function cutText(text: string, limit: number): string {
  const sizeTail = (shown: number): string =>
    `\n[truncated: ${shown} of ${text.length} characters shown; refine your query]`;
  const kept = cutAtLine(text, limit - sizeTail(limit).length);
  return `${kept}${sizeTail(kept.length)}`;
}
