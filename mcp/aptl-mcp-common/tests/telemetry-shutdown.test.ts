/**
 * SIGTERM path of the common MCP server against a real OTLP exporter (#1333).
 *
 * The handler awaits `shutdownTracing()` before `sshManager.disconnectAll()`.
 * These tests drive that handler with the real OTLP HTTP exporter pointed at
 * loopback sockets: a port with no listener, a listener that never answers,
 * and a stub collector that accepts every export. Only the MCP SDK transport
 * and the SSH manager are faked, so the measured delay is the real flush.
 */

import { createServer as createHttpServer, type Server as HttpServer } from 'node:http';
import { createServer as createNetServer, type AddressInfo, type Server as NetServer, type Socket } from 'node:net';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { trace } from '@opentelemetry/api';

const ssh = vi.hoisted(() => ({ disconnectAll: vi.fn(), listSessions: vi.fn(() => []), setHarvestHook: vi.fn() }));

vi.mock('@modelcontextprotocol/sdk/server/index.js', () => ({
  Server: vi.fn(function () {
    return { setRequestHandler: vi.fn(), connect: vi.fn().mockResolvedValue(undefined) };
  }),
}));

vi.mock('@modelcontextprotocol/sdk/server/stdio.js', () => ({
  StdioServerTransport: vi.fn(function () { return {}; }),
}));

vi.mock('../src/ssh.js', () => ({
  SSHConnectionManager: vi.fn(function () { return { disconnectAll: ssh.disconnectAll, listSessions: ssh.listSessions, setHarvestHook: ssh.setHarvestHook }; }),
}));

vi.mock('../src/tools/definitions.js', () => ({
  generateToolDefinitions: vi.fn().mockReturnValue([]),
}));

vi.mock('../src/tools/handlers.js', () => ({
  generateToolHandlers: vi.fn().mockReturnValue({}),
}));

const SPAN_NAME = 'span-recorded-before-sigterm';
// Done-when of #1333: SSH teardown starts within 1 s of SIGTERM.
const TEARDOWN_LIMIT_MS = 1000;
// Without the bound the flush waits out the exporter's retries (about 8 s
// refused, 10 s silent); keep the test alive long enough to report that delay.
const UNBOUNDED_FLUSH_TIMEOUT_MS = 20_000;

const labConfig = {
  server: {
    name: 'shutdown-test-server',
    version: '1.0.0',
    description: 'Shutdown Test Server - Description',
    toolPrefix: 'test',
    targetName: 'Test Container',
    configKey: 'test-container',
    envPrefix: 'APTL_TEST',
  },
  lab: { name: 'test-lab', network_subnet: '172.20.0.0/16' },
  containers: {
    'test-container': {
      container_name: 'test',
      container_ip: 'localhost',
      ssh_key: '/path/to/key',
      ssh_user: 'testuser',
      ssh_port: 22,
      enabled: true,
    },
  },
};

interface ShutdownObservation {
  exitCode: number;
  teardownAfterMs: number;
}

const closers: Array<() => Promise<void>> = [];

function listen(server: NetServer | HttpServer): Promise<string> {
  return new Promise(resolve => {
    server.listen(0, '127.0.0.1', () => {
      resolve(`http://127.0.0.1:${(server.address() as AddressInfo).port}`);
    });
  });
}

function close(server: NetServer | HttpServer): Promise<void> {
  return new Promise(resolve => { server.close(() => resolve()); });
}

/** A loopback port that refuses connections: nothing listens on it. */
async function refusingEndpoint(): Promise<string> {
  const server = createNetServer();
  const endpoint = await listen(server);
  await close(server);
  return endpoint;
}

/** A listener that accepts connections and never sends a response. */
async function silentEndpoint(): Promise<string> {
  const sockets = new Set<Socket>();
  const server = createNetServer(socket => { sockets.add(socket); });
  const endpoint = await listen(server);
  closers.push(async () => {
    for (const socket of sockets) socket.destroy();
    await close(server);
  });
  return endpoint;
}

/** A stub collector that records each OTLP request body and answers 200. */
async function collectorEndpoint(received: Buffer[]): Promise<string> {
  const server = createHttpServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => {
      if (req.method === 'POST' && req.url === '/v1/traces') received.push(Buffer.concat(chunks));
      res.writeHead(200, { 'Content-Type': 'application/x-protobuf' });
      res.end();
    });
  });
  const endpoint = await listen(server);
  closers.push(() => close(server));
  return endpoint;
}

/** Start the server, record one span, deliver SIGTERM and await process.exit. */
async function sigtermWithCollectorAt(endpoint: string): Promise<ShutdownObservation> {
  vi.stubEnv('OTEL_EXPORTER_OTLP_ENDPOINT', endpoint);

  const signalHandlers = new Map<string, () => void>();
  const addListener = process.on.bind(process);
  vi.spyOn(process, 'on').mockImplementation(((event: string, listener: () => void) => {
    if (event !== 'SIGTERM' && event !== 'SIGINT') return addListener(event, listener);
    signalHandlers.set(event, listener);
    return process;
  }) as typeof process.on);
  const exited = new Promise<number>(resolve => {
    vi.spyOn(process, 'exit').mockImplementation(((code?: number) => { resolve(code ?? 0); }) as never);
  });

  let teardownAt = Number.NaN;
  ssh.disconnectAll.mockImplementation(async () => { teardownAt = performance.now(); });

  const { createMCPServer } = await import('../src/server.js');
  const { getTracer } = await import('../src/telemetry.js');
  await createMCPServer(labConfig as never).start();
  getTracer().startSpan(SPAN_NAME).end();

  const signalledAt = performance.now();
  signalHandlers.get('SIGTERM')?.();
  const exitCode = await exited;
  return { exitCode, teardownAfterMs: teardownAt - signalledAt };
}

describe('MCP server SIGTERM trace flush', () => {
  beforeEach(() => {
    // initTracing() registers a global provider; clear the previous test's.
    trace.disable();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    ssh.disconnectAll.mockReset();
    await Promise.all(closers.splice(0).map(closeServer => closeServer()));
  });

  it.each([
    ['refuses connections', refusingEndpoint],
    ['accepts connections but never answers', silentEndpoint],
  ])(
    'starts SSH teardown within 1 s when the collector endpoint %s',
    async (_case, unreachableEndpoint) => {
      const { exitCode, teardownAfterMs } = await sigtermWithCollectorAt(await unreachableEndpoint());

      expect(exitCode).toBe(0);
      expect(ssh.disconnectAll).toHaveBeenCalledOnce();
      expect(teardownAfterMs).toBeLessThan(TEARDOWN_LIMIT_MS);
      expect(console.error).toHaveBeenCalledWith(
        expect.stringContaining('[OTel] Trace export did not finish within'),
      );
    },
    UNBOUNDED_FLUSH_TIMEOUT_MS,
  );

  it('exports the spans recorded before SIGTERM when the collector is reachable', async () => {
    const received: Buffer[] = [];

    const { exitCode, teardownAfterMs } = await sigtermWithCollectorAt(await collectorEndpoint(received));

    expect(exitCode).toBe(0);
    expect(received.some(body => body.includes(SPAN_NAME))).toBe(true);
    expect(teardownAfterMs).toBeLessThan(TEARDOWN_LIMIT_MS);
    expect(console.error).not.toHaveBeenCalledWith(
      expect.stringContaining('[OTel] Trace export did not finish within'),
    );
  });
});
