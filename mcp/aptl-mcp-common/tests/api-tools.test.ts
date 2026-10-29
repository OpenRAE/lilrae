import { describe, it, expect, vi } from 'vitest';
import { generateAPIToolDefinitions } from '../src/tools/api-definitions.js';
import { generateAPIToolHandlers } from '../src/tools/api-handlers.js';
import { HTTPTimeoutError } from '../src/http.js';

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

    it.each(['', '.', '..', '../ossec.conf', 'nested/rules.xml', '.hidden.xml', 'rules.txt', 'rules.xml\n'])(
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

    it.each([[['custom_rules.xml']], [{ name: 'custom_rules.xml' }], [true], [null]])(
      'rejects the non-string file name %j before any request',
      async (filename) => {
        const { makeRequest, payload } = await call(ruleFileQuery, 'upload_rule_file', {
          params: { filename },
          body: '<group/>',
        });

        expect(payload.success).toBe(false);
        expect(payload.error).toBe('path parameter filename must be a string');
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

    it.each([[null], [[]], ['invalid'], [1]])('rejects a malformed argument container %j', async (args) => {
      const queries = { upload_rule_file: { ...ruleFileQuery.upload_rule_file, params: { filename: 'rules.xml' } } };
      const { makeRequest, payload } = await call(queries, 'upload_rule_file', args);
      expect(payload.success).toBe(false);
      expect(makeRequest).not.toHaveBeenCalled();
    });

    it.each([[null], [[]], ['invalid'], [1]])('rejects a malformed params container %j', async (params) => {
      const queries = { upload_rule_file: { ...ruleFileQuery.upload_rule_file, params: { filename: 'rules.xml' } } };
      const { makeRequest, payload } = await call(queries, 'upload_rule_file', { params });
      expect(payload.success).toBe(false);
      expect(makeRequest).not.toHaveBeenCalled();
    });

    const typedQueries = { upload_rule_file: {
      ...ruleFileQuery.upload_rule_file,
      params_schema: { type: 'object', properties: {
        filename: { type: 'string', maxLength: 255 }, overwrite: { type: 'boolean' },
      }, required: ['filename'], additionalProperties: false },
    } };

    it.each([['true'], [1], [['true']], [null]])('rejects an unsupported overwrite shape %j', async (overwrite) => {
      const { makeRequest, payload } = await call(typedQueries, 'upload_rule_file', {
        params: { filename: 'rules.xml', overwrite },
      });
      expect(payload.success).toBe(false);
      expect(makeRequest).not.toHaveBeenCalled();
    });

    it('rejects an oversized rule filename', async () => {
      const { makeRequest, payload } = await call(typedQueries, 'upload_rule_file', {
        params: { filename: 'x'.repeat(252) + '.xml' },
      });
      expect(payload.success).toBe(false);
      expect(makeRequest).not.toHaveBeenCalled();
    });

    it('advertises the same query parameter schema it enforces', () => {
      const tools = generateAPIToolDefinitions(mockServerConfig, typedQueries, false);
      expect(tools[0].inputSchema.properties?.params).toMatchObject(typedQueries.upload_rule_file.params_schema);
    });

    it('keeps arbitrary transport exceptions out of query responses', async () => {
      const { ctx, makeRequest } = context();
      makeRequest.mockRejectedValue(new Error('private-fixture-value'));
      const handler = generateAPIToolHandlers(mockServerConfig, ruleFileQuery).wazuh_upload_rule_file;
      const result = await handler({ params: { filename: 'rules.xml' } }, ctx);
      const payload = JSON.parse(result.content[0].text);
      expect(payload.success).toBe(false);
      expect(result.content[0].text).not.toContain('private-fixture-value');
      expect(payload).not.toHaveProperty('status');
      expect(payload).not.toHaveProperty('failure');
      expect(payload).not.toHaveProperty('api_error');
    });

    async function failedQuery(error: Error) {
      const { ctx, makeRequest } = context();
      makeRequest.mockRejectedValue(error);
      const handler = generateAPIToolHandlers(mockServerConfig, ruleFileQuery).wazuh_upload_rule_file;
      const result = await handler({ params: { filename: 'rules.xml' } }, ctx);
      return { text: result.content[0].text, payload: JSON.parse(result.content[0].text) };
    }

    function httpFailure(statusCode: number, response: unknown): Error {
      return Object.assign(new Error(`HTTP ${statusCode}: private-status-text`), {
        statusCode,
        response,
      });
    }

    it('reports the HTTP status and API error of a failed query, not its exception text', async () => {
      const { text, payload } = await failedQuery(
        httpFailure(403, { error: 'permission denied', trace: 'private-body-field' }),
      );

      expect(payload).toMatchObject({
        success: false,
        error: 'API query failed',
        status: 403,
        api_error: 'permission denied',
      });
      expect(text).not.toMatch(/private-(status-text|body-field)/);
    });

    it.each([
      ['RFC 7807 detail', { title: 'Bad Request', detail: 'Invalid rule XML', error: 1905 }, 'Invalid rule XML'],
      [
        'OpenSearch error.reason',
        { error: { type: 'parsing_exception', reason: 'Unknown key [qury]' }, status: 400 },
        'Unknown key [qury]',
      ],
      ['message', { type: 'BadRequest', message: 'Invalid case id' }, 'Invalid case id'],
      ['reason', { success: false, reason: 'Workflow not found' }, 'Workflow not found'],
    ])('reads the API error from the %s field', async (_shape, body, expected) => {
      const { payload } = await failedQuery(httpFailure(400, body));

      expect(payload).toMatchObject({ status: 400, api_error: expected });
    });

    it.each([
      ['an HTML body', '<html>private-page</html>'],
      ['an object without a message field', { error: { type: 'x' }, detail: 7, message: '  ' }],
      ['no body', undefined],
    ])('adds no API error for %s', async (_shape, body) => {
      const { text, payload } = await failedQuery(httpFailure(500, body));

      expect(payload).toMatchObject({ status: 500 });
      expect(payload).not.toHaveProperty('api_error');
      expect(text).not.toContain('private-page');
    });

    it('redacts and bounds the API error', async () => {
      const { payload } = await failedQuery(
        httpFailure(400, { detail: `password=private-secret ${'x'.repeat(1000)}` }),
      );

      expect(payload.api_error).not.toContain('private-secret');
      expect(payload.api_error).toContain('[REDACTED]');
      expect(payload.api_error).toHaveLength(513);
      expect(payload.api_error.endsWith('…')).toBe(true);
    });

    it('classifies a timed-out query without a status', async () => {
      const { payload } = await failedQuery(new HTTPTimeoutError('Request timeout after 30000ms'));

      expect(payload).toMatchObject({ success: false, error: 'API query failed', failure: 'timeout' });
      expect(payload).not.toHaveProperty('status');
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

  it('reports the HTTP status and API error of a failed generic API call', async () => {
    const makeRequest = vi.fn().mockRejectedValue(
      Object.assign(new Error('HTTP 404: Not Found'), {
        statusCode: 404,
        response: { detail: 'Resource not found', trace: 'private-body-field' },
      }),
    );
    const handler = generateAPIToolHandlers(mockServerConfig).wazuh_api_call;

    const result = await handler(
      { endpoint: '/api/missing' },
      { httpClient: { makeRequest }, labConfig: {} } as any,
    );

    expect(JSON.parse(result.content[0].text)).toMatchObject({
      success: false,
      error: 'HTTP 404: Not Found',
      status: 404,
      api_error: 'Resource not found',
    });
    expect(result.content[0].text).not.toContain('private-body-field');
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
