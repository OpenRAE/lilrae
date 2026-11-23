import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { generateAPIToolHandlers, generateAPIToolDefinitions, HTTPClient } from 'aptl-mcp-common';

const config = JSON.parse(readFileSync(
  new URL('../docker-lab-config.json', import.meta.url), 'utf8',
).replace(/\$\{APTL_HP_[A-Z0-9_]+\}/g, '55000'));

describe('Wazuh rule-file input boundary', () => {
  it.each([
    { params: { filename: '../rules.xml' } },
    { params: { filename: 'a%2Fb.xml' } },
    { params: { filename: 'rules.xml\n' } },
    { params: { filename: 'x'.repeat(252) + '.xml' } },
    { params: { filename: ['rules.xml'] } },
    { params: { filename: 'rules.xml', overwrite: 'true' } },
    { params: null },
    null,
  ])('refuses malformed upload before HTTP or authentication: %j', async (args) => {
    vi.restoreAllMocks();
    const makeRequest = vi.spyOn(HTTPClient.prototype, 'makeRequest')
      .mockResolvedValue({ status: 200, data: {} });
    const handler = generateAPIToolHandlers(config.server, config.queries)
      [`${config.server.toolPrefix}_create_detection_rule`];
    const result = await handler(args, { httpClient: { makeRequest }, labConfig: config } as any);

    expect(JSON.parse(result.content[0].text).success).toBe(false);
    expect(makeRequest).not.toHaveBeenCalled();
  });

  it('advertises bounded filenames and boolean overwrite', () => {
    const tool = generateAPIToolDefinitions(config.server, config.queries)
      .find(tool => tool.name.endsWith('_create_detection_rule'))!;
    expect(tool.inputSchema.properties?.params).toMatchObject({
      properties: { filename: { type: 'string', maxLength: 255 }, overwrite: { type: 'boolean' } },
      required: ['filename'],
    });
  });
});
