import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { generateAPIToolHandlers, HTTPClient } from 'aptl-mcp-common';

// The indexer rule tools take the rule file name from the caller (#1273). No
// scenario file name or replace-all default lives in this generic config.
// The config loader substitutes host ports before any tool runs.
const config = JSON.parse(
  readFileSync(new URL('../docker-lab-config.json', import.meta.url), 'utf8').replace(
    /\$\{APTL_HP_[A-Z0-9_]+\}/g,
    '55000',
  ),
);
const queries = config.queries;
const serverConfig = { toolPrefix: 'indexer', configKey: 'indexer' } as any;

async function call(name: string, args: unknown) {
  vi.restoreAllMocks();
  // Includes the temporary JWT client: invalid input must be refused before
  // reaching the HTTP/authentication boundary, regardless of client choice.
  const makeRequest = vi.spyOn(HTTPClient.prototype, 'makeRequest')
    .mockResolvedValue({ status: 200, data: {} });
  const handlers = generateAPIToolHandlers(serverConfig, queries);
  const result = await handlers[`indexer_${name}`](args, {
    httpClient: { makeRequest },
    labConfig: {},
  } as any);
  return { makeRequest, payload: JSON.parse(result.content[0].text) };
}

describe('indexer rule-file tools', () => {
  it('holds no scenario file name or default overwrite', () => {
    const text = readFileSync(new URL('../docker-lab-config.json', import.meta.url), 'utf8');
    expect(text).not.toMatch(/purple_loop/);
    expect(queries.create_rule.params).toBeUndefined();
  });

  it('writes the caller-named file and passes overwrite only when asked', async () => {
    const { makeRequest, payload } = await call('create_rule', {
      params: { filename: 'custom_rules.xml', overwrite: true },
      body: '<group name="custom,"></group>',
    });

    expect(payload.success).toBe(true);
    const [url, method, options] = makeRequest.mock.calls[0];
    expect(url).toMatch(/\/rules\/files\/custom_rules\.xml$/);
    expect(method).toBe('PUT');
    expect(options.params).toEqual({ overwrite: true });
  });

  it.each(['zzz.txt', '../ossec.conf', 'nested/rules.xml', 'a%2Fb.xml', 'a b.xml', '.x.xml'])(
    'rejects the unsafe file name %j before any request',
    async (filename) => {
      for (const tool of ['create_rule', 'get_rule_file']) {
        const { makeRequest, payload } = await call(tool, {
          params: { filename },
          body: '<group/>',
        });
        expect(payload.success).toBe(false);
        expect(makeRequest).not.toHaveBeenCalled();
      }
    },
  );

  it.each([
    { params: { filename: 'x'.repeat(252) + '.xml' } },
    { params: { filename: 'rules.xml\n' } },
    { params: { filename: 'rules.xml?overwrite=true' } },
    { params: { filename: ['rules.xml'] } },
    { params: { filename: 'rules.xml', overwrite: 'true' } },
    { params: { filename: 'rules.xml', overwrite: [true] } },
    { params: null },
    null,
  ])('refuses malformed rule input before authentication: %j', async (args) => {
    const { makeRequest, payload } = await call('create_rule', args);
    expect(payload.success).toBe(false);
    expect(makeRequest).not.toHaveBeenCalled();
  });
});
