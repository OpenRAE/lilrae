import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';

// The real SDK server runs below; only its stdio transport and the backends
// are replaced. `start()` connects to the in-memory end the test hands over,
// and every SSH or HTTP operation lands on a spy.
const fakes = vi.hoisted(() => ({
  serverTransport: undefined as unknown,
  ssh: {
    executeCommand: vi.fn(),
    createSession: vi.fn(),
    executeInSession: vi.fn(),
    getSessionOutput: vi.fn(),
    getSessionRunId: vi.fn(),
    closeSession: vi.fn(),
    listSessions: vi.fn(),
    disconnectAll: vi.fn(),
  },
  http: { makeRequest: vi.fn() },
}));

vi.mock('@modelcontextprotocol/sdk/server/stdio.js', () => ({
  StdioServerTransport: vi.fn(function () { return fakes.serverTransport; })
}));

vi.mock('../src/ssh.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/ssh.js')>()),
  SSHConnectionManager: vi.fn(function () { return fakes.ssh; })
}));

vi.mock('../src/http.js', () => ({
  HTTPClient: vi.fn(function () { return fakes.http; })
}));

vi.mock('../src/captures.js', () => ({
  harvestSession: vi.fn().mockResolvedValue(true)
}));

vi.mock('../src/telemetry.js', () => ({
  initTracing: vi.fn(),
  shutdownTracing: vi.fn().mockResolvedValue(undefined),
  getTracer: vi.fn(),
  traceToolCall: vi.fn(async (_n: unknown, _s: unknown, _a: unknown, fn: () => unknown) => fn())
}));

const mockConfig = {
  server: {
    name: 'test-server',
    version: '1.0.0',
    description: 'Test Server - Description',
    toolPrefix: 'test',
    targetName: 'Test Container',
    configKey: 'test-container',
    envPrefix: 'APTL_TEST'
  },
  lab: {
    name: 'test-lab',
    network_subnet: '172.20.0.0/16'
  },
  containers: {
    'test-container': {
      container_name: 'test',
      container_ip: 'localhost',
      ssh_key: '/path/to/key',
      ssh_user: 'testuser',
      ssh_port: 22,
      enabled: true
    }
  }
};

const apiConfig = {
  server: { ...mockConfig.server, name: 'wazuh-server', toolPrefix: 'wazuh', targetName: 'Wazuh' },
  lab: mockConfig.lab,
  api: {
    baseUrl: 'https://wazuh.example:55000',
    auth: { type: 'basic', username: 'api-user', password: 'api-password' }
  }
};

const queryConfig = {
  ...apiConfig,
  queries: {
    query_alerts: {
      url: 'https://indexer.example:9200/wazuh-alerts-*/_search',
      method: 'POST',
      body: { size: 1 },
      description: 'Search recent alerts'
    }
  }
};

// The shape of mcp-wazuh's `create_detection_rule` query: the rules file
// name is a path parameter and the rules XML is a raw string body.
const ruleFileConfig = {
  ...apiConfig,
  queries: {
    create_detection_rule: {
      url: 'https://wazuh.example:55000/rules/files/{filename}',
      method: 'PUT',
      path_param_patterns: { filename: '[A-Za-z0-9][A-Za-z0-9_.-]*\\.xml' },
      description: 'Upload a custom Wazuh rules file'
    }
  }
};

const RULE_XML = [
  '<group name="custom,">',
  '  <rule id="100100" level="10">',
  '    <if_sid>5710</if_sid>',
  '    <description>SSH login for "admin" from $(id)</description>',
  '  </rule>',
  '</group>',
].join('\n');

// Neither branch of the API tools' `body: anyOf [object, string]` admits the
// value, so Ajv reports both branches and the anyOf itself.
const BODY_TYPE_VIOLATION = 'arguments/body must be object; arguments/body must be string; '
  + 'arguments/body must match a schema in anyOf';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('createMCPServer', () => {
  let createMCPServer: any;

  beforeEach(async () => {
    vi.clearAllMocks();
    const module = await import('../src/server.js');
    createMCPServer = module.createMCPServer;
  });

  it('creates server with valid config', () => {
    const server = createMCPServer(mockConfig);
    expect(server).toBeDefined();
    expect(server.start).toBeDefined();
    expect(typeof server.start).toBe('function');
  });

  it('calls tool generation functions', async () => {
    const definitions = await import('../src/tools/definitions.js');
    const handlers = await import('../src/tools/handlers.js');
    const mockGenDefs = vi.spyOn(definitions, 'generateToolDefinitions').mockReturnValue([]);
    const mockGenHandlers = vi.spyOn(handlers, 'generateToolHandlers').mockReturnValue({});

    createMCPServer(mockConfig);

    expect(mockGenDefs).toHaveBeenCalledWith(mockConfig.server);
    expect(mockGenHandlers).toHaveBeenCalledWith(mockConfig.server);
  });

  it('creates SSH manager', async () => {
    const ssh = await import('../src/ssh.js');
    const mockSSH = vi.spyOn(ssh, 'SSHConnectionManager');

    createMCPServer(mockConfig);

    expect(mockSSH).toHaveBeenCalled();
  });

  it('works with different server configs', () => {
    const kaliConfig = {
      ...mockConfig,
      server: {
        ...mockConfig.server,
        name: 'kali-server',
        toolPrefix: 'kali',
        targetName: 'Kali Linux'
      }
    };

    const server = createMCPServer(kaliConfig);
    expect(server).toBeDefined();
  });
});

// Shell text an agent sends during a scenario. Quotes, pipes, a loop, a here
// document and non-ASCII text must reach the target unchanged.
const SCENARIO_COMMAND = [
  'for u in aptl-a aptl-b; do ssh -o BatchMode=yes -o ConnectTimeout=5 "$u"@172.20.2.20 true 2>/dev/null || true; done',
  "curl -s 'http://172.20.1.20/login.php?user=admin%27--' | grep -c \"Welcome\"",
  "cat <<'EOF' > /tmp/notes.txt\nrésumé de $(id -un) \\ \"quoted\"\nEOF",
].join('\n');

describe('tool arguments over an MCP transport', () => {
  let createMCPServer: any;
  let traceToolCall: any;
  const clients: Client[] = [];
  const signals = ['SIGINT', 'SIGTERM'] as const;
  let listenersBefore: Record<string, unknown[]>;

  beforeEach(async () => {
    vi.clearAllMocks();
    ({ createMCPServer } = await import('../src/server.js'));
    ({ traceToolCall } = await import('../src/telemetry.js'));
    listenersBefore = Object.fromEntries(signals.map((signal) => [signal, process.listeners(signal)]));
  });

  afterEach(async () => {
    await Promise.all(clients.splice(0).map((client) => client.close()));
    // start() installs shutdown handlers once per server; drop this test's.
    for (const signal of signals) {
      process.listeners(signal)
        .filter((listener) => !listenersBefore[signal].includes(listener))
        .forEach((listener) => process.removeListener(signal, listener));
    }
  });

  async function connect(config: object, options: object = {}): Promise<Client> {
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    fakes.serverTransport = serverTransport;
    await createMCPServer(config, options).start();
    const client = new Client({ name: 'argument-validation-test', version: '1.0.0' });
    await client.connect(clientTransport);
    clients.push(client);
    return client;
  }

  function payload(result: Awaited<ReturnType<Client['callTool']>>) {
    const [block] = result.content as { type: string; text: string }[];
    return JSON.parse(block.text);
  }

  function backendOperations(): number {
    return [...Object.values(fakes.ssh), fakes.http.makeRequest]
      .reduce((count, operation) => count + operation.mock.calls.length, 0);
  }

  it.each([
    ['a missing required argument', mockConfig, 'test_run_command', {},
      "arguments must have required property 'command'"],
    ['a wrong argument type', mockConfig, 'test_run_command', { command: ['id'] },
      'arguments/command must be string'],
    ['an argument the schema does not list', mockConfig, 'test_interactive_session', { timeout: 5000 },
      'arguments must NOT have additional property "timeout"'],
    ['a command timeout past the Node timer limit', mockConfig, 'test_session_command',
      { session_id: 's1', command: 'msfconsole -q', raw: true, timeout: 2_147_483_648 },
      'arguments/timeout must be <= 2147483647'],
    ['a zero session timeout', mockConfig, 'test_background_session', { timeout_ms: 0 },
      'arguments/timeout_ms must be >= 1'],
    ['a negative line count', mockConfig, 'test_get_session_output', { session_id: 's1', lines: -5 },
      'arguments/lines must be >= 1'],
    ['a session id outside the id pattern', mockConfig, 'test_close_session', { session_id: '-s1' },
      'arguments/session_id must match pattern "^[A-Za-z0-9_][A-Za-z0-9._-]*$"'],
    ['an over-long session id', mockConfig, 'test_close_session', { session_id: 's'.repeat(129) },
      'arguments/session_id must NOT have more than 128 characters'],
    ['a string for a boolean flag', mockConfig, 'test_background_session', { raw: 'true' },
      'arguments/raw must be boolean'],
    ['an absolute endpoint URL', apiConfig, 'wazuh_api_call', { endpoint: 'https://attacker.example/agents' },
      'arguments/endpoint must match pattern "^/"'],
    ['an HTTP method outside the enum', apiConfig, 'wazuh_api_call', { endpoint: '/agents', method: 'PATCH' },
      'arguments/method must be equal to one of the allowed values'],
    ['a query parameter string instead of an object', queryConfig, 'wazuh_query_alerts', { params: 'size=1' },
      'arguments/params must be object'],
    ['a number for an API request body', apiConfig, 'wazuh_api_call', { endpoint: '/agents', method: 'POST', body: 42 },
      BODY_TYPE_VIOLATION],
    ['a list for a raw rules body', ruleFileConfig, 'wazuh_create_detection_rule',
      { params: { filename: 'custom_rules.xml' }, body: [RULE_XML] }, BODY_TYPE_VIOLATION],
    ['a null query body', queryConfig, 'wazuh_query_alerts', { body: null }, BODY_TYPE_VIOLATION],
  ])('refuses %s before any trace span, hook or backend operation', async (_label, config, tool, args, violation) => {
    const hook = vi.fn();
    const client = await connect(config, { postToolHook: hook });

    const result = await client.callTool({ name: tool, arguments: args });

    expect(result.isError).toBe(true);
    expect(payload(result)).toEqual({ success: false, error: `Invalid arguments for ${tool}: ${violation}` });
    expect(backendOperations()).toBe(0);
    expect(traceToolCall).not.toHaveBeenCalled();
    expect(hook).not.toHaveBeenCalled();
  });

  it('returns the same redacted error for the same invalid call', async () => {
    const client = await connect(mockConfig);
    const args = {
      session_id: 's1',
      command: 'sshpass -p hunter2 ssh root@172.20.2.20',
      timeout: -1,
      password: 'hunter2',
    };

    const first = await client.callTool({ name: 'test_session_command', arguments: args });
    const second = await client.callTool({ name: 'test_session_command', arguments: args });

    expect(payload(first)).toEqual({
      success: false,
      error: 'Invalid arguments for test_session_command: '
        + 'arguments must NOT have additional property "password"; arguments/timeout must be >= 1',
    });
    expect(second).toEqual(first);
    expect(JSON.stringify(first)).not.toContain('hunter2');
    expect(JSON.stringify(first)).not.toContain('172.20.2.20');
    expect(backendOperations()).toBe(0);
  });

  it('dispatches a scenario shell command to the target unchanged', async () => {
    fakes.ssh.executeCommand.mockResolvedValue({
      stdout: 'done', stderr: '', code: 0, signal: null, sessionId: 'exec-1', mode: 'normal',
    });
    const client = await connect(mockConfig);

    const result = await client.callTool({ name: 'test_run_command', arguments: { command: SCENARIO_COMMAND } });

    expect(result.isError).not.toBe(true);
    expect(payload(result)).toMatchObject({ success: true, command: SCENARIO_COMMAND });
    expect(fakes.ssh.executeCommand).toHaveBeenCalledTimes(1);
    expect(fakes.ssh.executeCommand).toHaveBeenCalledWith('localhost', 'testuser', '/path/to/key', SCENARIO_COMMAND, 22);
    expect(traceToolCall).toHaveBeenCalledTimes(1);
  });

  it('dispatches a raw session command whose timeout is the Node timer limit', async () => {
    fakes.ssh.executeInSession.mockResolvedValue({ stdout: '', stderr: '', code: 0, signal: null, mode: 'raw' });
    const client = await connect(mockConfig);

    const result = await client.callTool({
      name: 'test_session_command',
      arguments: { session_id: 'msf-1', command: 'msfconsole -q', raw: true, timeout: 2_147_483_647 },
    });

    expect(payload(result)).toMatchObject({ success: true, session_mode: 'raw' });
    expect(fakes.ssh.executeInSession).toHaveBeenCalledWith('msf-1', 'msfconsole -q', 2_147_483_647, true);
  });

  it('dispatches a call that omits its arguments when the schema requires none', async () => {
    fakes.ssh.listSessions.mockReturnValue([]);
    const client = await connect(mockConfig);

    const result = await client.callTool({ name: 'test_list_sessions' });

    expect(payload(result)).toEqual({ success: true, sessions: [], total_sessions: 0 });
    expect(fakes.ssh.listSessions).toHaveBeenCalledTimes(1);
  });

  it('dispatches API calls whose free-form params, body and headers stay open', async () => {
    fakes.http.makeRequest.mockResolvedValue({ status: 200, data: { hits: [] } });
    const client = await connect(apiConfig);

    const result = await client.callTool({
      name: 'wazuh_api_call',
      arguments: {
        endpoint: '/agents',
        method: 'POST',
        params: { limit: 1, select: 'id' },
        body: { query: { match_all: {} } },
        headers: { 'X-Request-Id': 'r-1' },
        response_type: 'text',
      },
    });

    expect(payload(result)).toMatchObject({ success: true, status: 200 });
    expect(fakes.http.makeRequest).toHaveBeenCalledWith('/agents', 'POST', {
      params: { limit: 1, select: 'id' },
      body: { query: { match_all: {} } },
      headers: { 'X-Request-Id': 'r-1' },
      responseType: 'text',
    });
  });

  it('dispatches a predefined query with an object body', async () => {
    fakes.http.makeRequest.mockResolvedValue({ status: 200, data: { hits: [] } });
    const client = await connect(queryConfig);

    const result = await client.callTool({
      name: 'wazuh_query_alerts',
      arguments: { body: { query: { match: { 'rule.id': '5710' } } } },
    });

    expect(payload(result)).toMatchObject({ success: true, status: 200 });
    expect(fakes.http.makeRequest).toHaveBeenCalledWith(
      'https://indexer.example:9200/wazuh-alerts-*/_search',
      'POST',
      { params: {}, body: { size: 1, query: { match: { 'rule.id': '5710' } } }, responseType: 'json' },
    );
  });

  it.each([
    ['the API call tool', apiConfig, 'wazuh_api_call',
      { endpoint: '/rules/files/custom_rules.xml', method: 'PUT', params: { overwrite: true }, body: RULE_XML },
      '/rules/files/custom_rules.xml'],
    ['a predefined query', ruleFileConfig, 'wazuh_create_detection_rule',
      { params: { filename: 'custom_rules.xml', overwrite: true }, body: RULE_XML },
      'https://wazuh.example:55000/rules/files/custom_rules.xml'],
  ])('dispatches a raw-string body through %s unchanged', async (_label, config, tool, args, url) => {
    fakes.http.makeRequest.mockResolvedValue({ status: 200, data: { error: 0 } });
    const client = await connect(config);

    const result = await client.callTool({ name: tool, arguments: args });

    expect(result.isError).not.toBe(true);
    expect(payload(result)).toMatchObject({ success: true, status: 200 });
    expect(fakes.http.makeRequest).toHaveBeenCalledTimes(1);
    expect(fakes.http.makeRequest).toHaveBeenCalledWith(
      url,
      'PUT',
      { params: { overwrite: true }, body: RULE_XML, responseType: 'json' },
    );
  });

  it('advertises the closed schemas it enforces', async () => {
    const client = await connect({ ...mockConfig, api: apiConfig.api });

    const { tools } = await client.listTools();

    expect(tools.map((tool) => tool.name)).toContain('test_api_call');
    expect(tools).toHaveLength(11);
    for (const tool of tools) {
      expect(tool.inputSchema.additionalProperties).toBe(false);
    }
  });

  it('keeps the unknown-field rule a tool schema states itself', async () => {
    const definitions = await import('../src/tools/definitions.js');
    vi.spyOn(definitions, 'generateToolDefinitions').mockReturnValue([{
      name: 'test_info',
      description: 'Open schema',
      inputSchema: { type: 'object', properties: {}, additionalProperties: true },
    }]);
    const client = await connect(mockConfig);

    const { tools } = await client.listTools();
    const result = await client.callTool({ name: 'test_info', arguments: { verbose: true } });

    expect(tools[0].inputSchema.additionalProperties).toBe(true);
    expect(result.isError).not.toBe(true);
    expect(payload(result)).toMatchObject({ target_name: 'Test Container' });
  });

  it('refuses a handler that no advertised schema covers', async () => {
    const definitions = await import('../src/tools/definitions.js');
    vi.spyOn(definitions, 'generateToolDefinitions').mockReturnValue([]);
    const client = await connect(mockConfig);

    await expect(
      client.callTool({ name: 'test_run_command', arguments: { command: 'id' } }),
    ).rejects.toThrow('Unknown tool: test_run_command');
    expect(backendOperations()).toBe(0);
  });

  it('stops at creation when a tool schema cannot be compiled', async () => {
    const definitions = await import('../src/tools/definitions.js');
    vi.spyOn(definitions, 'generateToolDefinitions').mockReturnValue([{
      name: 'test_info',
      description: 'Broken schema',
      inputSchema: { type: 'object', properties: { verbose: { type: 'flag' } } },
    }] as any);

    expect(() => createMCPServer(mockConfig)).toThrow('Cannot compile the input schema of test_info');
  });
});
