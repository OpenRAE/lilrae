import { describe, expect, it } from 'vitest';

import { boundToolResult } from '../src/tool-output-cap.js';

// 100 tokens = 400 characters with the module's 4-characters-per-token estimate.
const MAX_TOKENS = 100;
const LIMIT = MAX_TOKENS * 4;

function textResult(value: unknown) {
  return { content: [{ type: 'text', text: JSON.stringify(value, null, 2) }] };
}

function records(count: number, size = 40) {
  return Array.from({ length: count }, (_, index) => ({ id: index, body: 'x'.repeat(size) }));
}

function parsedText(result: { content: { text: string }[] }) {
  return JSON.parse(result.content[0].text);
}

describe('boundToolResult', () => {
  it('returns a result within the budget as the same object', () => {
    const result = textResult({ success: true, data: records(2) });

    const bounded = boundToolResult(result, MAX_TOKENS);

    expect(bounded.result).toBe(result);
    expect(bounded.truncated).toBe(false);
    expect(bounded.returnedChars).toBe(bounded.originalChars);
  });

  it('drops whole records from the end and reports how many were left out', () => {
    const data = records(30);
    const result = textResult({ success: true, status: 200, data });

    const bounded = boundToolResult(result, MAX_TOKENS);
    const body = parsedText(bounded.result);

    expect(bounded.truncated).toBe(true);
    expect(bounded.result.content[0].text.length).toBeLessThanOrEqual(LIMIT);
    expect(body.success).toBe(true);
    expect(body.status).toBe(200);
    expect(body.data).toEqual(data.slice(0, body.data.length));
    expect(body._truncated).toEqual({
      returned: body.data.length,
      total: 30,
      note: `${30 - body.data.length} more results; refine your query`,
    });
  });

  it('trims the nested search hits, not a smaller array beside them', () => {
    const hits = records(30);
    const shards = ['a', 'b', 'c'];
    const result = textResult({ data: { shards, hits: { total: 30, hits } } });

    const body = parsedText(boundToolResult(result, MAX_TOKENS).result);

    expect(body.data.shards).toEqual(shards);
    expect(body.data.hits.hits).toEqual(hits.slice(0, body.data.hits.hits.length));
    expect(body._truncated.total).toBe(30);
  });

  it('picks the array that takes the most bytes, not the one with the most items', () => {
    const tags = Array.from({ length: 50 }, (_, index) => `t${index}`);
    const listing = records(8, 120);
    const result = textResult({ tags, listing });

    const body = parsedText(boundToolResult(result, MAX_TOKENS * 3).result);

    expect(body.tags).toEqual(tags);
    expect(body.listing.length).toBeLessThan(8);
  });

  it('cuts at a line boundary rather than return zero records', () => {
    const record = Object.fromEntries(
      Array.from({ length: 20 }, (_, index) => [`field${index}`, 'z'.repeat(40)]),
    );
    const result = textResult({ success: true, data: [{ id: 0, ...record }] });

    const text = boundToolResult(result, MAX_TOKENS).result.content[0].text;

    expect(text).toContain('"field0"');
    expect(text).not.toContain('"_truncated"');
    expect(text).toMatch(/\n\[truncated: \d+ of \d+ characters shown; refine your query\]$/);
  });

  it('cuts text that is not a JSON object at a line boundary', () => {
    const lines = Array.from({ length: 80 }, (_, index) => `line ${index} ${'y'.repeat(20)}`);
    const text = lines.join('\n');

    const bounded = boundToolResult({ content: [{ type: 'text', text }] }, MAX_TOKENS);
    const output = bounded.result.content[0].text.split('\n');
    const tail = output.pop();

    expect(bounded.truncated).toBe(true);
    expect(lines.slice(0, output.length)).toEqual(output);
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
