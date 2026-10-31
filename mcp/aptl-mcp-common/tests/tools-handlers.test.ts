import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { generateToolHandlers, resolveCaptureContainer, errorMessage } from '../src/tools/handlers.js';
import { CommandTimeoutError } from '../src/ssh.js';
import { harvestSession } from '../src/captures.js';

describe('errorMessage', () => {
  it('returns the message of an Error', () => {
    expect(errorMessage(new Error('boom'))).toBe('boom');
  });

  it('falls back to "Unknown error" for a non-Error value', () => {
    // Covers the false branch of the instanceof narrowing — the catch blocks
    // only ever throw Errors, so this is the only place the fallback runs.
    expect(errorMessage('a thrown string')).toBe('Unknown error');
    expect(errorMessage(undefined)).toBe('Unknown error');
  });
});

// Partial mock: keep the real error classes, so `assertSessionIdContract`
// throws an SSHError whose `.message` the handler catch block converts into
// the response envelope, and run_command recognizes a real
// CommandTimeoutError (#1319).
vi.mock('../src/ssh.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/ssh.js')>()),
  SSHConnectionManager: vi.fn(),
}));

// Harvest copies captures out of a docker container; the handlers only decide
// whether and when to call it.
vi.mock('../src/captures.js', () => ({ harvestSession: vi.fn(async () => true) }));

describe('generateToolHandlers', () => {
  const mockServerConfig = {
    toolPrefix: 'test',
    targetName: 'Test Container',
    configKey: 'test-container'
  };

  it('generates handler map with correct tool names', () => {
    const handlers = generateToolHandlers(mockServerConfig);

    expect(handlers['test_info']).toBeDefined();
    expect(handlers['test_run_command']).toBeDefined();
    expect(handlers['test_interactive_session']).toBeDefined();
    expect(handlers['test_background_session']).toBeDefined();
    expect(handlers['test_session_command']).toBeDefined();
    expect(handlers['test_list_sessions']).toBeDefined();
    expect(handlers['test_close_session']).toBeDefined();
    expect(handlers['test_get_session_output']).toBeDefined();
    expect(handlers['test_close_all_sessions']).toBeDefined();
  });

  it('works with different server configs', () => {
    const kaliConfig = {
      toolPrefix: 'kali',
      targetName: 'Kali Linux',
      configKey: 'kali'
    };

    const handlers = generateToolHandlers(kaliConfig);

    expect(handlers['kali_info']).toBeDefined();
    expect(handlers['kali_run_command']).toBeDefined();
  });

  it('generates all expected handlers', () => {
    const handlers = generateToolHandlers(mockServerConfig);
    expect(Object.keys(handlers)).toHaveLength(9);
  });

  it('all handlers are functions', () => {
    const handlers = generateToolHandlers(mockServerConfig);
    Object.values(handlers).forEach(handler => {
      expect(typeof handler).toBe('function');
    });
  });

  it('handles empty toolPrefix', () => {
    const emptyConfig = {
      toolPrefix: '',
      targetName: 'Test',
      configKey: 'test'
    };

    const handlers = generateToolHandlers(emptyConfig);
    expect(handlers['_info']).toBeDefined();
    expect(handlers['_run_command']).toBeDefined();
  });
});

describe('handler execution logic', () => {
  const mockLabConfig = {
    server: {
      configKey: 'test-container',
      targetName: 'Test Container'
    },
    lab: {
      name: 'test-lab',
      network_subnet: '172.20.0.0/16'
    },
    containers: {
      'test-container': {
        container_ip: '172.20.0.50',
        ssh_user: 'testuser',
        ssh_port: 2022,
        enabled: true
      }
    }
  };

  const mockContext = {
    sshManager: {},
    labConfig: mockLabConfig
  };

  it('target_info returns container info when enabled', async () => {
    const handlers = generateToolHandlers({ toolPrefix: 'test', targetName: 'Test', configKey: 'test-container' });
    const result = await handlers['test_info']({}, mockContext);

    expect(result.content[0].text).toContain('172.20.0.50');
    expect(result.content[0].text).toContain('testuser');
    expect(result.content[0].text).toContain('test-lab');
  });

  it('target_info returns error when container disabled', async () => {
    const disabledConfig = {
      ...mockLabConfig,
      containers: {
        'test-container': {
          ...mockLabConfig.containers['test-container'],
          enabled: false
        }
      }
    };

    const disabledContext = { ...mockContext, labConfig: disabledConfig };
    const handlers = generateToolHandlers({ toolPrefix: 'test', targetName: 'Test Container', configKey: 'test-container' });

    const result = await handlers['test_info']({}, disabledContext);
    expect(result.content[0].text).toContain('not enabled');
  });
});

describe('assertSessionIdContract — canonical session_id at MCP ingress', () => {
  // OBS-003 / codex pre-push cycle 3 finding-4 + finding-10: every
  // session-taking handler asserts the canonical id contract before
  // touching the SSH manager so downstream layers (PTY tee, Kali
  // wrapper, harvest) all see the same id. The schema regex
  // permits `.` (so version-shaped ids like `sess-1.0` work) but
  // the handler-level guard additionally rejects `..`.

  const handlers = generateToolHandlers({
    toolPrefix: 'test',
    targetName: 'Test',
    configKey: 'test-container',
  });
  const ctx = {
    sshManager: {} as any,
    labConfig: {
      server: { configKey: 'test-container', targetName: 'Test' },
      lab: { name: 'test-lab', network_subnet: '172.20.0.0/16' },
      containers: {
        'test-container': {
          container_ip: '172.20.0.50',
          ssh_user: 'testuser',
          ssh_port: 2022,
          enabled: true,
        },
      },
    } as any,
  };

  it.each([
    ['close_session', 'test_close_session'],
    ['session_command', 'test_session_command'],
    ['get_session_output', 'test_get_session_output'],
  ])('%s rejects an empty session_id', async (_label, handlerName) => {
    const result = await handlers[handlerName](
      { session_id: '', command: 'whoami' },
      ctx,
    );
    // Assert on the assertSessionIdContract message specifically, NOT just the
    // presence of "session_id" — the JSON envelope always carries a
    // `"session_id"` key, so a mere `toContain('session_id')` would also pass
    // if the contract were removed and a downstream TypeError were caught
    // instead (test-quality review cycle 1). The "must be a non-empty string"
    // phrasing only appears in the SSHError the contract throws.
    const body = JSON.parse(result.content[0].text);
    expect(body.success).toBe(false);
    expect(body.error).toContain('must be a non-empty string');
  });

  it.each([
    ['close_session', 'test_close_session'],
    ['session_command', 'test_session_command'],
    ['get_session_output', 'test_get_session_output'],
  ])('%s rejects a session_id containing ".."', async (_label, handlerName) => {
    const result = await handlers[handlerName](
      { session_id: 'sess..with..dots', command: 'whoami' },
      ctx,
    );
    expect(result.content[0].text.toLowerCase()).toContain("'..'");
  });

  it.each([
    ['interactive_session', 'test_interactive_session'],
    ['background_session', 'test_background_session'],
  ])('%s rejects a session_id containing ".."', async (_label, handlerName) => {
    const result = await handlers[handlerName](
      { session_id: '../escape' },
      ctx,
    );
    expect(result.content[0].text.toLowerCase()).toContain("'..'");
  });
});

describe('handler error paths return a failure envelope', () => {
  // Every session/command handler wraps its body in try/catch and returns
  // `{ success: false, error: <message | UNKNOWN_ERROR> }`. Drive each handler
  // through its catch with an sshManager that throws on any call, so the
  // failure-envelope line is exercised (and the UNKNOWN_ERROR fallback line is
  // not dead code). Args use a VALID session id so the handler passes ingress
  // validation and reaches the throwing dependency.
  const handlers = generateToolHandlers({
    toolPrefix: 'test',
    targetName: 'Test',
    configKey: 'test-container',
  });
  const throwingCtx = {
    sshManager: new Proxy(
      {},
      { get: () => () => { throw new Error('boom'); } },
    ) as any,
    labConfig: {
      server: { configKey: 'test-container', targetName: 'Test' },
      lab: { name: 'test-lab', network_subnet: '172.20.0.0/16' },
      containers: {
        'test-container': {
          container_name: 'aptl-test',
          container_ip: '172.20.0.50',
          ssh_key: '/tmp/nonexistent-key',
          ssh_user: 'testuser',
          ssh_port: 2022,
          enabled: true,
        },
      },
    } as any,
  };

  it('reports a nonzero remote command exit as unsuccessful', async () => {
    const context = {
      ...throwingCtx,
      sshManager: { harvestSession: async (_id: string, _run: unknown, harvest: () => Promise<boolean>) => harvest(), executeCommand: vi.fn().mockResolvedValue({
        stdout: 'session could not start', stderr: '', code: 254,
      }) } as any,
    };
    const result = await handlers.test_run_command({ command: 'id' } as any, context);
    const body = JSON.parse(result.content[0].text);
    expect(body.success).toBe(false);
    expect(body.output.code).toBe(254);
  });

  it.each([
    ['run_command', 'test_run_command', { command: 'whoami' }],
    ['interactive_session', 'test_interactive_session', { session_id: 'sess-1' }],
    ['background_session', 'test_background_session', { session_id: 'sess-1' }],
    ['session_command', 'test_session_command', { session_id: 'sess-1', command: 'whoami' }],
    ['list_sessions', 'test_list_sessions', {}],
    ['close_session', 'test_close_session', { session_id: 'sess-1' }],
    ['get_session_output', 'test_get_session_output', { session_id: 'sess-1' }],
    ['close_all_sessions', 'test_close_all_sessions', {}],
  ])('%s returns a failure envelope when its dependency throws', async (_label, handlerName, args) => {
    const result = await handlers[handlerName](args as any, throwingCtx);
    const body = JSON.parse(result.content[0].text);
    expect(body.success).toBe(false);
    expect(typeof body.error).toBe('string');
    expect(body.error.length).toBeGreaterThan(0);
  });
});

describe('#1319: run_command harvests a timed-out exec session', () => {
  const handlers = generateToolHandlers({ toolPrefix: 'test', targetName: 'Test', configKey: 'test-container' });
  const labConfig = {
    server: { configKey: 'test-container', targetName: 'Test' },
    lab: { name: 'test-lab', network_subnet: '172.20.0.0/16' },
    containers: {
      'test-container': {
        container_name: 'aptl-test',
        capture_container_name: 'aptl-test-capture',
        container_ip: '172.20.0.50',
        ssh_key: '/tmp/nonexistent-key',
        ssh_user: 'testuser',
        ssh_port: 2022,
        enabled: true,
      },
    },
  } as any;
  const command = 'nmap -p- 172.20.0.20';
  const timeoutEnvelope = { command, success: false, error: `Command timeout after 30000ms: ${command}` };

  const sessionId = 'exec-1760000000000-0a1b2c3d';
  const harvestedFrom = [{ containerName: 'aptl-test-capture', runId: 'run-1319' }, sessionId];

  // A stub manager whose executeCommand rejects the way SSHConnectionManager
  // does when the timer fires; the test decides when the channel closes.
  const timingOut = () => {
    let closeChannel: () => void = () => {};
    const channelClosed = new Promise<void>((settle) => {
      closeChannel = settle;
    });
    const sshManager = {
      harvestSession: async (_id: string, _run: unknown, harvest: () => Promise<boolean>) => harvest(),
      executeCommand: vi.fn(async () => {
        throw new CommandTimeoutError(timeoutEnvelope.error, sessionId, 'run-1319', channelClosed);
      }),
    } as any;
    return { sshManager, closeChannel };
  };

  beforeEach(() => {
    vi.mocked(harvestSession).mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('harvests the exec session after its channel closes and still reports the timeout', async () => {
    vi.useFakeTimers();
    const { sshManager, closeChannel } = timingOut();
    let body: unknown;
    void handlers.test_run_command({ command }, { sshManager, labConfig }).then((result) => {
      body = JSON.parse(result.content[0].text);
    });
    await vi.advanceTimersByTimeAsync(2000);
    expect(harvestSession).not.toHaveBeenCalled();
    expect(body).toBeUndefined();

    closeChannel();
    await vi.advanceTimersByTimeAsync(0);
    expect(harvestSession).toHaveBeenCalledExactlyOnceWith(...harvestedFrom);
    expect(body).toEqual(timeoutEnvelope);
  });

  it('reports the timeout after a bounded wait and harvests once a late channel closes', async () => {
    vi.useFakeTimers();
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { sshManager, closeChannel } = timingOut();
    let body: unknown;
    void handlers.test_run_command({ command }, { sshManager, labConfig }).then((result) => {
      body = JSON.parse(result.content[0].text);
    });
    await vi.advanceTimersByTimeAsync(2999);
    expect(body).toBeUndefined();

    await vi.advanceTimersByTimeAsync(1);
    expect(body).toEqual(timeoutEnvelope);
    expect(harvestSession).not.toHaveBeenCalled();
    expect(log).toHaveBeenCalledWith(
      `[captures] session ${sessionId} is still open after its run_command timeout; harvesting it when its channel closes`,
    );

    // OpenSSH confirms a forced-command session's close when the command exits.
    await vi.advanceTimersByTimeAsync(600_000);
    closeChannel();
    await vi.advanceTimersByTimeAsync(0);
    expect(harvestSession).toHaveBeenCalledExactlyOnceWith(...harvestedFrom);
  });

  it.each([
    ['reports a failure', () => vi.mocked(harvestSession).mockResolvedValueOnce(false)],
    ['throws', () => vi.mocked(harvestSession).mockRejectedValueOnce(new Error('docker cp failed'))],
  ])('logs a harvest that %s and keeps the timeout error', async (_label, failHarvest) => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    failHarvest();
    const { sshManager, closeChannel } = timingOut();
    closeChannel();

    const body = JSON.parse((await handlers.test_run_command({ command }, { sshManager, labConfig })).content[0].text);
    expect(body).toEqual(timeoutEnvelope);
    expect(harvestSession).toHaveBeenCalledExactlyOnceWith(...harvestedFrom);
    expect(log).toHaveBeenCalledWith(`[captures] harvest after a run_command timeout failed for session ${sessionId}`);
  });

  it('does not harvest when run_command fails before any command ran', async () => {
    const sshManager = { executeCommand: vi.fn().mockRejectedValue(new Error('connection refused')) } as any;
    const body = JSON.parse((await handlers.test_run_command({ command }, { sshManager, labConfig })).content[0].text);
    expect(body).toEqual({ command, success: false, error: 'connection refused' });
    expect(harvestSession).not.toHaveBeenCalled();
  });
});

describe('resolveCaptureContainer (ADR-041 harvest target)', () => {
  const base = {
    server: { configKey: 'kali', targetName: 'Kali' },
    lab: { name: 'aptl-local', network_subnet: '172.20.0.0/16' },
  };

  it('harvests from capture_container_name when set (sidecar)', () => {
    const labConfig = {
      ...base,
      containers: { kali: { capture_container_name: 'aptl-kali-capture' } },
    } as any;
    // ADR-041: captures live in the sidecar, not the workload container, so a
    // sudo-capable agent cannot read or tamper with them.
    expect(resolveCaptureContainer(labConfig)).toBe('aptl-kali-capture');
  });

  it('names no harvest target when the server declares no capture sidecar (#1242)', () => {
    // A workload container never owns captures (ADR-041), so a legacy
    // `container_name` is not a harvest target.
    const labConfig = {
      ...base,
      containers: { kali: { container_name: 'aptl-kali', ssh_user: 'kali' } },
    } as any;
    expect(resolveCaptureContainer(labConfig)).toBeUndefined();
  });

  it('returns undefined for an API-only target (no containers)', () => {
    const labConfig = { ...base, server: { configKey: '' } } as any;
    expect(resolveCaptureContainer(labConfig)).toBeUndefined();
  });

  it('returns undefined when configKey is set but containers is absent', () => {
    const labConfig = { ...base } as any; // no `containers` key
    expect(resolveCaptureContainer(labConfig)).toBeUndefined();
  });

  it('returns undefined when the configKey container is missing', () => {
    const labConfig = { ...base, containers: { other: { capture_container_name: 'x-capture' } } } as any;
    expect(resolveCaptureContainer(labConfig)).toBeUndefined();
  });
});

describe('#1242: a declared empty capture binding still reaches the harvester', () => {
  const handlers = generateToolHandlers({ toolPrefix: 'test', targetName: 'Test', configKey: 'test-container' });
  const withSidecar = (capture: Record<string, string>) => ({
    server: { configKey: 'test-container', targetName: 'Test' },
    lab: { name: 'test-lab', network_subnet: '172.20.0.0/16' },
    containers: {
      'test-container': {
        container_ip: '172.20.0.50', ssh_user: 'testuser', ssh_port: 2022, enabled: true, ...capture,
      },
    },
  }) as any;
  const sshManager = { harvestSession: async (_id: string, _run: unknown, harvest: () => Promise<boolean>) => harvest(), getSessionRunId: vi.fn(() => 'run-1242'), closeSession: vi.fn(async () => true) } as any;

  beforeEach(() => {
    vi.mocked(harvestSession).mockClear();
  });

  it('harvests and warns when the declared sidecar name is empty', async () => {
    // An empty LILRAE_MCP_CAPTURE_CONTAINER resolves the declaration to ''.
    // The harvester records container-unresolved; the handler must not skip it.
    vi.mocked(harvestSession).mockResolvedValueOnce(false);
    const result = await handlers.test_close_session(
      { session_id: 'sess-1' },
      { sshManager, labConfig: withSidecar({ capture_container_name: '' }) },
    );
    expect(harvestSession).toHaveBeenCalledExactlyOnceWith({ containerName: '', runId: 'run-1242' }, 'sess-1');
    expect(JSON.parse(result.content[0].text).harvest_warning).toBeDefined();
  });

  it('does not harvest when the server declares no capture sidecar', async () => {
    const result = await handlers.test_close_session(
      { session_id: 'sess-1' },
      { sshManager, labConfig: withSidecar({}) },
    );
    expect(harvestSession).not.toHaveBeenCalled();
    expect(JSON.parse(result.content[0].text).harvest_warning).toBeUndefined();
  });
});

describe('close_session / close_all_sessions harvest behaviour', () => {
  // OBS-003: when the labConfig declares no capture sidecar,
  // `resolveCaptureContainer` returns undefined and `maybeHarvest`
  // is a true no-op (returns `true` without invoking docker). This
  // exercises the close handlers' happy path without involving the
  // captures module's docker-cp machinery.

  const labConfig = {
    server: { configKey: 'test-container', targetName: 'Test' },
    lab: { name: 'test-lab', network_subnet: '172.20.0.0/16' },
    // No capture_container_name in containers[configKey] — harvest no-ops.
    containers: {
      'test-container': {
        container_ip: '172.20.0.50',
        ssh_user: 'testuser',
        ssh_port: 2022,
        enabled: true,
      },
    },
  };

  it('close_session returns success when session was closed (no harvest_warning)', async () => {
    const handlers = generateToolHandlers({
      toolPrefix: 'test',
      targetName: 'Test',
      configKey: 'test-container',
    });
    const sshManager = {
      harvestSession: async (_id: string, _run: unknown, harvest: () => Promise<boolean>) => harvest(),
      getSessionRunId: vi.fn(() => undefined),
      closeSession: vi.fn(async () => true),
    } as any;
    const result = await handlers['test_close_session'](
      { session_id: 'sess-1' },
      { sshManager, labConfig } as any,
    );
    const body = JSON.parse(result.content[0].text);
    expect(body.success).toBe(true);
    expect(body.session_id).toBe('sess-1');
    expect(body.harvest_warning).toBeUndefined();
  });

  it('close_session reports "not found" envelope when session is missing', async () => {
    const handlers = generateToolHandlers({
      toolPrefix: 'test',
      targetName: 'Test',
      configKey: 'test-container',
    });
    const sshManager = {
      harvestSession: async (_id: string, _run: unknown, harvest: () => Promise<boolean>) => harvest(),
      getSessionRunId: vi.fn(() => undefined),
      closeSession: vi.fn(async () => false),
    } as any;
    const result = await handlers['test_close_session'](
      { session_id: 'sess-missing' },
      { sshManager, labConfig } as any,
    );
    const body = JSON.parse(result.content[0].text);
    expect(body.success).toBe(false);
    expect(body.message).toContain('not found');
  });

  it("session_command envelope carries session_mode reflecting effective mode (#282)", async () => {
    const handlers = generateToolHandlers({
      toolPrefix: 'test',
      targetName: 'Test',
      configKey: 'test-container',
    });
    // Session created raw, command without raw override → effective raw.
    // The fake manager returns the CommandResult shape the real
    // PersistentSession would produce.
    const sshManager = {
      executeInSession: vi.fn(async () => ({
        stdout: 'msf6 >',
        stderr: '',
        code: 0,
        signal: null,
        mode: 'raw',
      })),
    } as any;
    const result = await handlers['test_session_command'](
      { session_id: 'inherited-raw', command: 'msfconsole' },
      { sshManager, labConfig } as any,
    );
    const body = JSON.parse(result.content[0].text);
    expect(body.success).toBe(true);
    expect(body.session_mode).toBe('raw');
    expect(body.exit_code).toBe(0);
  });

  it("session_command envelope reports session_mode='normal' for a normal-mode command", async () => {
    const handlers = generateToolHandlers({
      toolPrefix: 'test',
      targetName: 'Test',
      configKey: 'test-container',
    });
    const sshManager = {
      executeInSession: vi.fn(async () => ({
        stdout: 'hi',
        stderr: '',
        code: 0,
        signal: null,
        mode: 'normal',
      })),
    } as any;
    const result = await handlers['test_session_command'](
      { session_id: 's1', command: 'echo hi' },
      { sshManager, labConfig } as any,
    );
    const body = JSON.parse(result.content[0].text);
    expect(body.session_mode).toBe('normal');
  });

  it('close_all_sessions reports session count', async () => {
    const handlers = generateToolHandlers({
      toolPrefix: 'test',
      targetName: 'Test',
      configKey: 'test-container',
    });
    const sshManager = {
      harvestSession: async (_id: string, _run: unknown, harvest: () => Promise<boolean>) => harvest(),
      listSessions: vi.fn(() => [
        { sessionId: 'sess-a' },
        { sessionId: 'sess-b' },
      ]),
      getSessionRunId: vi.fn(() => undefined),
      disconnectAll: vi.fn(async () => {}),
    } as any;
    const result = await handlers['test_close_all_sessions'](
      {},
      { sshManager, labConfig } as any,
    );
    const body = JSON.parse(result.content[0].text);
    expect(body.success).toBe(true);
    expect(body.sessions_closed).toBe(2);
    expect(body.harvest_warning).toBeUndefined();
  });
});
