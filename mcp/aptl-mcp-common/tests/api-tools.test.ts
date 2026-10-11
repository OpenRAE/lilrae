import { describe, it, expect, vi } from 'vitest';
import { generateAPIToolDefinitions } from '../src/tools/api-definitions.js';
import { generateAPIToolHandlers } from '../src/tools/api-handlers.js';

describe('generateAPIToolDefinitions', () => {
  const mockServerConfig = {
    toolPrefix: 'wazuh',
    targetName: 'Wazuh SIEM'
  };

  it('generates basic API tools', () => {
    const tools = generateAPIToolDefinitions(mockServerConfig);

    expect(tools).toHaveLength(2);
    expect(tools[0].name).toBe('wazuh_api_call');
    expect(tools[1].name).toBe('wazuh_api_info');
    expect(tools[0].description).toContain('Wazuh SIEM');
    expect(tools[0].inputSchema.properties?.body).toEqual({
      anyOf: [{ type: 'object' }, { type: 'string' }],
      description: 'Request body for POST/PUT requests. Use a string for raw payloads such as XML.',
    });
  });

  it('generates predefined query tools', () => {
    const queries = {
      recent_alerts: {
        endpoint: '/api/alerts',
        method: 'GET' as const,
        description: 'Get recent alerts'
      },
      search_logs: {
        endpoint: '/api/search',
        method: 'POST' as const,
        description: 'Search log data'
      }
    };

    const tools = generateAPIToolDefinitions(mockServerConfig, queries);

    expect(tools).toHaveLength(4); // 2 basic + 2 queries
    expect(tools[2].name).toBe('wazuh_recent_alerts');
    expect(tools[3].name).toBe('wazuh_search_logs');
    expect(tools[2].description).toBe('Get recent alerts');
    expect(tools[2].inputSchema.properties?.body).toEqual({
      anyOf: [{ type: 'object' }, { type: 'string' }],
      description: 'Override request body data. Use a string for raw payloads such as XML.',
    });
  });

  it('works with different server configs', () => {
    const splunkConfig = {
      toolPrefix: 'splunk',
      targetName: 'Splunk Enterprise'
    };

    const tools = generateAPIToolDefinitions(splunkConfig);

    expect(tools[0].name).toBe('splunk_api_call');
    expect(tools[0].description).toContain('Splunk Enterprise');
  });
});

describe('generateAPIToolHandlers', () => {
  const mockServerConfig = {
    toolPrefix: 'wazuh',
    targetName: 'Wazuh SIEM'
  };

  it('generates handler map with correct tool names', () => {
    const handlers = generateAPIToolHandlers(mockServerConfig);

    expect(handlers['wazuh_api_call']).toBeDefined();
    expect(handlers['wazuh_api_info']).toBeDefined();
    expect(typeof handlers['wazuh_api_call']).toBe('function');
  });

  it('generates predefined query handlers', () => {
    const queries = {
      recent_alerts: {
        endpoint: '/api/alerts',
        method: 'GET' as const,
        description: 'Get recent alerts'
      }
    };

    const handlers = generateAPIToolHandlers(mockServerConfig, queries);

    expect(handlers['wazuh_recent_alerts']).toBeDefined();
    expect(typeof handlers['wazuh_recent_alerts']).toBe('function');
  });

  describe('predefined query path parameters', () => {
    const ruleFileQuery = {
      upload_rule_file: {
        url: 'https://wazuh.example:55000/rules/files/{filename}',
        method: 'PUT' as const,
        path_param_patterns: { filename: '[A-Za-z0-9][A-Za-z0-9_.-]*\\.xml' },
        description: 'Upload a rules file',
      },
    };
    const genericQuery = {
      search_index: {
        url: 'https://indexer.example:9200/{index}/_search',
        method: 'POST' as const,
        description: 'Search one index',
      },
    };

    function context() {
      const makeRequest = vi.fn().mockResolvedValue({ status: 200, data: {} });
      return { makeRequest, ctx: { httpClient: { makeRequest }, labConfig: {} } as any };
    }

    async function call(queries: any, name: string, args: any) {
      const { makeRequest, ctx } = context();
      const handlers = generateAPIToolHandlers(mockServerConfig, queries);
      const result = await handlers[`wazuh_${name}`](args, ctx);
      return { makeRequest, payload: JSON.parse(result.content[0].text) };
    }

    it('substitutes a valid file name and keeps other params as query params', async () => {
      const { makeRequest, payload } = await call(ruleFileQuery, 'upload_rule_file', {
        params: { filename: 'custom_rules.xml', overwrite: true },
        body: '<group name="custom,"></group>',
      });

      expect(payload.success).toBe(true);
      expect(makeRequest).toHaveBeenCalledWith(
        'https://wazuh.example:55000/rules/files/custom_rules.xml',
        'PUT',
        expect.objectContaining({
          params: { overwrite: true },
          body: '<group name="custom,"></group>',
        }),
      );
    });

    it.each(['', '.', '..', '../ossec.conf', 'nested/rules.xml', '.hidden.xml', 'rules.txt'])(
      'rejects the file name %j before any request',
      async (filename) => {
        const { makeRequest, payload } = await call(ruleFileQuery, 'upload_rule_file', {
          params: { filename },
          body: '<group/>',
        });

        expect(payload.success).toBe(false);
        expect(payload.error).toMatch(/path parameter filename/);
        expect(makeRequest).not.toHaveBeenCalled();
      },
    );

    it('rejects a missing path parameter before any request', async () => {
      const { makeRequest, payload } = await call(ruleFileQuery, 'upload_rule_file', {
        body: '<group/>',
      });

      expect(payload.success).toBe(false);
      expect(payload.error).toBe('path parameter filename is required');
      expect(makeRequest).not.toHaveBeenCalled();
    });

    it.each(['', '.', '..'])(
      'rejects the dot segment %j for a parameter without a pattern',
      async (index) => {
        const { makeRequest, payload } = await call(genericQuery, 'search_index', {
          params: { index },
        });

        expect(payload.success).toBe(false);
        expect(payload.error).toMatch(/single non-empty path segment/);
        expect(makeRequest).not.toHaveBeenCalled();
      },
    );

    it('encodes a parameter without a pattern as one path segment', async () => {
      const { makeRequest, payload } = await call(genericQuery, 'search_index', {
        params: { index: 'wazuh-alerts-*' },
      });

      expect(payload.success).toBe(true);
      expect(makeRequest.mock.calls[0][0]).toBe(
        'https://indexer.example:9200/wazuh-alerts-*/_search',
      );
    });
  });

  it('works with different server configs', () => {
    const elasticConfig = {
      toolPrefix: 'elastic',
      targetName: 'Elasticsearch'
    };

    const handlers = generateAPIToolHandlers(elasticConfig);

    expect(handlers['elastic_api_call']).toBeDefined();
    expect(handlers['elastic_api_info']).toBeDefined();
  });
});
