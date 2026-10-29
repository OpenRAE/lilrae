/**
 * One size limit on tool results, the same for every MCP server.
 *
 * An agent re-reads each tool result on every later turn of its conversation.
 * One oversized result, such as a 50 KB alert or execution listing, therefore
 * costs input tokens on every turn. A client that compacts its context to make
 * room also changes the prompt prefix, which defeats provider prompt caching.
 *
 * A text result over the server's budget is cut at a record boundary: whole
 * records are dropped from the end of the result's largest array, and a tail
 * says how many were left out. Text that is not a JSON object with such an
 * array is cut at a line boundary. The tail and the log carry counts and sizes
 * only, never result content or the supplied query (#1273 preflight).
 */

/** Default budget for one tool result, in estimated tokens. */
export const DEFAULT_MAX_TOOL_RESULT_TOKENS = 4000;

// A conservative estimate for JSON and command output.
const CHARS_PER_TOKEN = 4;

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

/**
 * Return ``result`` with each text part cut to ``maxTokens``. A result within
 * the budget is returned as the same object.
 */
export function boundToolResult<T extends ToolResult>(
  result: T,
  maxTokens: number,
): BoundedToolResult<T> {
  const limit = maxTokens * CHARS_PER_TOKEN;
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
  return trimRecords(parseObject(text), limit) ?? cutAtLine(text, limit);
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
 * Drop whole records from the end of the largest array until the result fits.
 * The tail goes at the top of the result, where the agent reads it first.
 */
function trimRecords(root: Record<string, unknown> | undefined, limit: number): string | undefined {
  const records = root === undefined ? undefined : largestArray(root);
  if (root === undefined || records === undefined) {
    return undefined;
  }
  const { holder, key, items } = records;
  const render = (kept: number): string => {
    holder[key] = items.slice(0, kept);
    root._truncated = {
      returned: kept,
      total: items.length,
      note: `${items.length - kept} more results; refine your query`,
    };
    return JSON.stringify(root, null, 2);
  };
  // The full list does not fit, so search the shorter prefixes. An empty list
  // would tell the agent nothing, so when not even one record fits, the result
  // is cut at a line boundary instead.
  let fitting: string | undefined;
  let low = 1;
  let high = items.length - 1;
  while (low <= high) {
    const kept = Math.floor((low + high) / 2);
    const text = render(kept);
    if (text.length <= limit) {
      fitting = text;
      low = kept + 1;
    } else {
      high = kept - 1;
    }
  }
  return fitting;
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

function cutAtLine(text: string, limit: number): string {
  const head = text.slice(0, limit);
  const lineEnd = head.lastIndexOf('\n');
  const kept = lineEnd > 0 ? head.slice(0, lineEnd) : head;
  return `${kept}\n[truncated: ${kept.length} of ${text.length} characters shown; refine your query]`;
}
