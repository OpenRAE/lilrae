import { describe, expect, it } from 'vitest';

import { boundToolResult, toolResultBudgets } from '../src/tool-output-cap.js';

// 100 tokens = 400 characters with the module's 4-characters-per-token estimate.
const MAX_TOKENS = 100;
const LIMIT = MAX_TOKENS * 4;

// The handlers format every envelope this way.
function textResult(value: unknown) {
  return { content: [{ type: 'text', text: JSON.stringify(value, null, 2) }] };
}

function records(count: number, size = 40) {
  return Array.from({ length: count }, (_, index) => ({ id: index, body: 'x'.repeat(size) }));
}

function lines(count: number, prefix = 'line') {
  return Array.from({ length: count }, (_, index) => `${prefix} ${index} ${'y'.repeat(20)}`).join('\n');
}

function boundedText(value: unknown, maxTokens = MAX_TOKENS) {
  return boundToolResult(textResult(value), maxTokens).result.content[0].text;
}

describe('boundToolResult', () => {
  it('returns a result within the budget as the same object', () => {
    const result = textResult({ success: true, data: records(2) });

    const bounded = boundToolResult(result, MAX_TOKENS);

    expect(bounded.result).toBe(result);
    expect(bounded.truncated).toBe(false);
    expect(bounded.returnedChars).toBe(bounded.originalChars);
  });

  it('returns the whole result for a null budget and still measures it', () => {
    const result = textResult({ success: true, data: lines(500) });

    const bounded = boundToolResult(result, null);

    expect(bounded.result).toBe(result);
    expect(bounded.truncated).toBe(false);
    expect(bounded.originalChars).toBe(result.content[0].text.length);
  });

  it('drops whole records from the end and ends with how many were left out', () => {
    const data = records(30);

    const text = boundedText({ success: true, status: 200, data });
    const body = JSON.parse(text);

    expect(text.length).toBeLessThanOrEqual(LIMIT);
    expect(body.success).toBe(true);
    expect(body.status).toBe(200);
    expect(body.data).toEqual(data.slice(0, body.data.length));
    expect(body._truncated).toEqual({
      returned: body.data.length,
      total: 30,
      note: `${30 - body.data.length} more results; refine your query`,
    });
    expect(Object.keys(body).at(-1)).toBe('_truncated');
  });

  it('trims the nested search hits, not a smaller array beside them', () => {
    const hits = records(30);
    const shards = ['a', 'b', 'c'];

    const body = JSON.parse(boundedText({ data: { shards, hits: { total: 30, hits } } }));

    expect(body.data.shards).toEqual(shards);
    expect(body.data.hits.hits).toEqual(hits.slice(0, body.data.hits.hits.length));
    expect(body._truncated.total).toBe(30);
  });

  it('picks the array that takes the most bytes, not the one with the most items', () => {
    const tags = Array.from({ length: 50 }, (_, index) => `t${index}`);

    const body = JSON.parse(boundedText({ tags, listing: records(8, 120) }, MAX_TOKENS * 3));

    expect(body.tags).toEqual(tags);
    expect(body.listing.length).toBeLessThan(8);
  });

  it('cuts one long string at a line boundary and keeps the fields after it', () => {
    const stdout = lines(200);

    const text = boundedText({ success: true, output: stdout, exit_code: 0, session_mode: 'normal' });
    const body = JSON.parse(text);

    expect(text.length).toBeLessThanOrEqual(LIMIT);
    expect(body.exit_code).toBe(0);
    expect(body.session_mode).toBe('normal');
    expect(body.output.length).toBeGreaterThan(0);
    expect(stdout.startsWith(`${body.output}\n`)).toBe(true);
    expect(body._truncated).toEqual({
      returned_characters: body.output.length,
      total_characters: stdout.length,
      note: `${stdout.length - body.output.length} more characters; refine your query`,
    });
    expect(Object.keys(body).at(-1)).toBe('_truncated');
  });

  it('cuts every long string to one shared length, so each keeps its head', () => {
    const stdout = lines(200, 'out');
    const stderr = lines(200, 'err');

    const body = JSON.parse(boundedText({ output: { stdout, stderr, code: 1 } }, MAX_TOKENS * 2));

    expect(body.output.code).toBe(1);
    expect(stdout.startsWith(body.output.stdout)).toBe(true);
    expect(stderr.startsWith(body.output.stderr)).toBe(true);
    expect(body.output.stdout.length).toBeGreaterThan(0);
    expect(body.output.stderr.length).toBeGreaterThan(0);
  });

  it('keeps one record and cuts its strings when not even one record fits', () => {
    const data = Array.from({ length: 5 }, (_, id) => ({ id, log: lines(40) }));

    const text = boundedText({ success: true, data });
    const body = JSON.parse(text);

    expect(text.length).toBeLessThanOrEqual(LIMIT);
    expect(body.data).toHaveLength(1);
    expect(body.data[0].id).toBe(0);
    expect(data[0].log.startsWith(body.data[0].log)).toBe(true);
    expect(body._truncated.returned).toBe(1);
    expect(body._truncated.total).toBe(5);
    expect(body._truncated.note).toMatch(/^4 more results; \d+ more characters; refine your query$/);
  });

  it('cuts a single long line at the room, not at an early line break', () => {
    const value = `start\n${'z'.repeat(5000)}`;

    const body = JSON.parse(boundedText({ data: value }));

    expect(body.data.length).toBeGreaterThan(LIMIT / 4);
    expect(value.startsWith(body.data)).toBe(true);
  });

  it('never splits a surrogate pair', () => {
    const value = '\u{1F600}'.repeat(3000);

    const body = JSON.parse(boundedText({ data: value }));

    expect(body.data.length % 2).toBe(0);
    expect(value.startsWith(body.data)).toBe(true);
  });

  it('cuts an object that does not fit even with empty strings at a line boundary', () => {
    const fields = Object.fromEntries(Array.from({ length: 60 }, (_, index) => [`field${index}`, index]));

    const text = boundedText({ success: true, ...fields });

    expect(text.length).toBeLessThanOrEqual(LIMIT);
    expect(text).toContain('"field0"');
    expect(text).not.toContain('"_truncated"');
    expect(text).toMatch(/\n\[truncated: \d+ of \d+ characters shown; refine your query\]$/);
  });

  it('cuts text that is not a JSON object at a line boundary, tail included in the budget', () => {
    const text = lines(80);

    const bounded = boundToolResult({ content: [{ type: 'text', text }] }, MAX_TOKENS);
    const returned = bounded.result.content[0].text;
    const output = returned.split('\n');
    const tail = output.pop();

    expect(bounded.truncated).toBe(true);
    expect(returned.length).toBeLessThanOrEqual(LIMIT);
    expect(text.split('\n').slice(0, output.length)).toEqual(output);
    expect(tail).toMatch(/^\[truncated: \d+ of \d+ characters shown; refine your query\]$/);
  });

  it('leaves parts that are not text untouched', () => {
    const image = { type: 'image', data: 'z'.repeat(2000), mimeType: 'image/png' };
    const result = { content: [image as unknown as { type: string; text: string }] };

    const bounded = boundToolResult(result, MAX_TOKENS);

    expect(bounded.result).toBe(result);
    expect(bounded.originalChars).toBe(0);
  });
});

describe('toolResultBudgets', () => {
  const config = {
    server: { toolPrefix: 'indexer', maxToolResultTokens: 2000 },
    queries: {
      query: { url: 'u', method: 'POST', description: 'd' },
      get_rule_file: { url: 'u', method: 'GET', description: 'd', max_result_tokens: null },
      small: { url: 'u', method: 'GET', description: 'd', max_result_tokens: 50 },
    },
  } as any;

  it('uses the query budget when the query sets one, else the server budget', () => {
    const budget = toolResultBudgets(config);

    expect(budget('indexer_query')).toBe(2000);
    expect(budget('indexer_get_rule_file')).toBeNull();
    expect(budget('indexer_small')).toBe(50);
    expect(budget('indexer_run_command')).toBe(2000);
  });

  it('uses the default budget when the server sets none', () => {
    const budget = toolResultBudgets({ server: { toolPrefix: 'red' } } as any);

    expect(budget('red_run_command')).toBe(4000);
  });
});
