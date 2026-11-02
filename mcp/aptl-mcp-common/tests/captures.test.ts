/**
 * Tests for the OBS-003 / ADR-033 capture harvest helper.
 *
 * `harvestSession` runs the broker's `await-session` check and then
 * `docker cp` via child_process. We don't have a docker daemon in the
 * test environment, so we shim `spawn` to fake the docker CLI: each
 * call is intercepted and replaced with a controllable behaviour
 * (success / not-found / permission-denied), and we assert that:
 *   - the destination dir is created with 0700 mode,
 *   - file/dir modes are repaired to 0600 / 0700 recursively,
 *   - "No such file" from docker cp is treated as a clean no-op,
 *   - the run id is resolved from trace-context.json on the host,
 *   - failures never throw out of harvestSession.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  chmodSync,
  cpSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
  mkdirSync,
  existsSync,
  readFileSync,
  statSync,
  symlinkSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { EventEmitter } from 'node:events';

type DockerResult = { code: number; stderr: string };

// Module-level controls the mocked `spawn` reads on every invocation.
// Each test resets them in `beforeEach`.
interface SpawnControl {
  /** Reply to `docker cp`. */
  exitCode: number;
  stderrText: string;
  /** Reply to `docker exec ... broker.py await-session`. */
  awaitExit: number;
  awaitStderr: string;
  /** Whether a successful `docker cp` brings the session's metadata.json. */
  copyMetadata: boolean;
  capturedArgs: string[][];
  capturedCmds: string[];
  callCount: number;
  /** When set, `docker cp` reads from `root` as the filesystem of `name`. */
  container?: { name: string; root: string };
}
const spawnControl: SpawnControl = {
  exitCode: 0,
  stderrText: '',
  awaitExit: 0,
  awaitStderr: '',
  copyMetadata: true,
  capturedArgs: [],
  capturedCmds: [],
  callCount: 0,
};

/** Answer one docker call from the stand-in container, else with the set reply. */
function replay(args: string[]): DockerResult {
  if (spawnControl.container) {
    return args[0] === 'exec'
      ? awaitFromContainer(spawnControl.container, args)
      : copyFromContainer(spawnControl.container, args);
  }
  if (args[0] === 'exec') return { code: spawnControl.awaitExit, stderr: spawnControl.awaitStderr };
  if (spawnControl.exitCode === 0 && args[0] === 'cp' && spawnControl.copyMetadata) {
    writeFileSync(join(args[2], 'metadata.json'), METADATA);
  }
  return { code: spawnControl.exitCode, stderr: spawnControl.stderrText };
}

/**
 * `broker.py await-session` against the stand-in container, with the broker's
 * exit codes: 3 for a session with no directory, 4 for a session without
 * final metadata.
 */
function awaitFromContainer(container: { name: string; root: string }, args: string[]): DockerResult {
  const name = args[3];
  if (name !== container.name) return noSuchContainer(name);
  const run = args[args.indexOf('--run-id') + 1];
  const session = args[args.indexOf('--session-id') + 1];
  const sessionRoot = join(container.root, ROOT, run, 'sessions', session);
  if (!existsSync(sessionRoot)) return { code: 3, stderr: '' };
  if (!existsSync(join(sessionRoot, 'metadata.json'))) return { code: 4, stderr: '' };
  return { code: 0, stderr: '' };
}

/** The `docker exec` argv of one broker session action against `container`. */
const brokerArgs = (action: string, container: string, run: string, session: string) => [
  'exec', '--user', 'root', container, 'python3', '/usr/local/bin/broker.py',
  action, '--run-id', run, '--session-id', session,
];

/** The `docker cp` calls a harvest made, in order. */
const cpCalls = () => spawnControl.capturedArgs.filter((args) => args[0] === 'cp');

/** `docker cp <name>:<dir>/. <dest>` against a directory standing in for the container. */
function copyFromContainer(container: { name: string; root: string }, args: string[]): DockerResult {
  const [, source, dest] = args;
  const name = source.slice(0, source.indexOf(':'));
  const path = source.slice(name.length + 1);
  if (name !== container.name) return noSuchContainer(name);
  const local = join(container.root, path);
  if (!existsSync(local)) return missingFile(name, path);
  cpSync(local, dest, { recursive: true });
  return { code: 0, stderr: '' };
}

// #1242: `docker cp` replies recorded on 2026-10-09 UTC against Docker CLI and
// Engine 29.7.2 (API 1.55), with stdout and stderr piped as `execDocker`
// spawns them. A created, never-started `FROM scratch` container named
// `aptl-w123456789abc-kali-capture` copied a present path with exit 0 and no
// output, and answered a missing one with the `Could not find the file` line
// below. With no such container, the daemon answered every path with the same
// `No such container` line.
const SCOPED = 'aptl-w123456789abc-kali-capture';
/** Another workspace's sidecar, never the one a harvest names. */
const OTHER_WORKSPACE = 'aptl-wcba987654321-kali-capture';
const FIXED = 'aptl-kali-capture';
const ROOT = '/var/log/aptl/captures';
const RUN = 'a'.repeat(32);
const missingFile = (name: string, path: string): DockerResult => ({
  code: 1,
  stderr: `Error response from daemon: Could not find the file ${path} in container ${name}\n`,
});
const noSuchContainer = (name: string): DockerResult => ({
  code: 1,
  stderr: `Error response from daemon: No such container: ${name}\n`,
});

// One session as containers/kali-capture/broker.py records it: the frames and
// metadata under `<root>/<run>/sessions/<session>/`, and the run's ledger of
// accepted sessions beside `sessions/`.
const FRAMES =
  '{"data_b64":"aGVsbG8K","direction":"output","sequence":1,"timestamp":"2026-10-09T00:00:01Z"}\n';
const METADATA = '{"close_reason":"clean-exit","frame_count":1,"session_id":"sess-1"}';

vi.mock('node:child_process', () => ({
  spawn: (cmd: string, args: string[]) => {
    spawnControl.callCount += 1;
    // Test-quality review cycle 1 T-001/T-002: capture the spawned
    // binary path so SonarCloud S4036 hardening (the "no PATH lookup"
    // contract) is actually pinned. Previously the mock discarded
    // `_cmd`, so both `dockerBin()` regressions (default-vs-override)
    // and "harvest stopped using docker at all" regressions would
    // pass vacuously.
    spawnControl.capturedCmds.push(cmd);
    spawnControl.capturedArgs.push(args);
    const stdout = new EventEmitter();
    const stderr = new EventEmitter();
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter;
      stderr: EventEmitter;
    };
    child.stdout = stdout;
    child.stderr = stderr;
    const { code: exit, stderr: text } = replay(args);
    setImmediate(() => {
      if (text) stderr.emit('data', Buffer.from(text));
      child.emit('close', exit);
    });
    return child;
  },
}));

import { harvestSession, finalizeCaptureSession } from '../src/captures.js';
import { loadLabConfig } from '../src/config.js';
import { resolveCaptureContainer } from '../src/tools/session-capture.js';

// tests/ -> aptl-mcp-common/ -> mcp/, then the shipped red server config.
const RED_CONFIG = join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  '..',
  'mcp-red',
  'docker-lab-config.json',
);

let tmp = '';

beforeEach(() => {
  tmp = mkdtempSync(join(tmpdir(), 'aptl-harvest-test-'));
  spawnControl.exitCode = 0;
  spawnControl.stderrText = '';
  spawnControl.awaitExit = 0;
  spawnControl.awaitStderr = '';
  spawnControl.copyMetadata = true;
  spawnControl.capturedArgs = [];
  spawnControl.capturedCmds = [];
  spawnControl.callCount = 0;
  spawnControl.container = undefined;
});
afterEach(() => {
  vi.unstubAllEnvs();
  rmSync(tmp, { recursive: true, force: true });
});

function activateScenario(traceId: string): void {
  writeFileSync(
    join(tmp, 'trace-context.json'),
    JSON.stringify({ trace_id: traceId, span_id: 'b'.repeat(16), trace_flags: '01' }),
  );
}

describe('harvestSession', () => {
  it('harvests into the configured Python run archive', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);
    const archive = join(tmp, 'archive');
    const dest = join(archive, tid, 'kali-side', 'sess-1');
    mkdirSync(join(dest, 'pty'), { recursive: true });
    writeFileSync(join(dest, 'pty', 'typescript'), 'hello');

    const ok = await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp, APTL_MCP_RUN_STORE_BASE: archive } },
      'sess-1',
    );

    expect(ok).toBe(true);
    expect(cpCalls()[0][2]).toBe(dest);
  });
  it('invokes `docker cp <container>:<src>/. <dest>` for the active scenario', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);

    // Pre-seed the dest with a fake harvested file so the post-cp
    // chmod walk has something to do (no docker daemon in test
    // environment).
    const dest = join(tmp, 'runs', tid, 'kali-side', 'sess-1');
    mkdirSync(join(dest, 'pty'), { recursive: true });
    writeFileSync(join(dest, 'pty', 'typescript'), 'hello');

    // (spawn behaviour controlled by spawnControl above)

    const ok = await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );

    expect(ok).toBe(true);
    // The broker confirms final metadata first, then one docker cp copies
    // the broker's session directory. The capture sidecar runs no auditd
    // or process accounting, so no container-wide `_audit` / `_proc-acct`
    // copy follows.
    expect(spawnControl.capturedArgs).toEqual([
      brokerArgs('await-session', 'aptl-kali', tid, 'sess-1'),
      ['cp', `aptl-kali:/var/log/aptl/captures/${tid}/sessions/sess-1/.`, dest],
    ]);
    expect(existsSync(join(dest, '_global'))).toBe(false);
    expect(existsSync(join(dest, 'capture-harvest-failure.json'))).toBe(false);
  });

  it('falls back to _unbound when trace-context is absent', async () => {
    const dest = join(tmp, 'runs', '_unbound', 'kali-side', 'sess-1');
    mkdirSync(join(dest, 'pty'), { recursive: true });
    writeFileSync(join(dest, 'pty', 'typescript'), 'x');

    const ok = await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );

    expect(ok).toBe(true);
    expect(cpCalls()).toEqual([[
      'cp', 'aptl-kali:/var/log/aptl/captures/_unbound/sessions/sess-1/.', dest,
    ]]);
  });

  it('returns false (NOT silent success) when per-session subtree is missing — converts a tampering primitive into a visible anomaly', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);
    spawnControl.exitCode = 1;
    spawnControl.stderrText = 'Error: No such file or directory';

    const ok = await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );

    // ADR-033 + codex cycle 2 finding-9: a "kali user deleted its
    // own session subtree before close" attack would otherwise be
    // invisible if we returned true here. The MCP-side PTY tee
    // still has the authoritative record; the harvest result
    // reports the anomaly so it's surfaceable.
    expect(ok).toBe(false);
  });

  it("#304: per-session docker cp failure invokes spawn exactly once (no retry-with-backoff)", async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);
    spawnControl.exitCode = 1;
    spawnControl.stderrText = 'Error: No such file or directory';

    await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );

    // #304: retry helper removed — remote close is now awaited in
    // PersistentSession.close before harvest runs. The per-session
    // "no such file" failure is NOT retried — it fails fast.
    expect(cpCalls()).toEqual([
      ['cp', `aptl-kali:/var/log/aptl/captures/${tid}/sessions/sess-1/.`, join(tmp, 'runs', tid, 'kali-side', 'sess-1')],
    ]);
  });

  it('returns false on real docker cp failure but does not throw', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);
    spawnControl.exitCode = 1;
    spawnControl.stderrText = 'Error: permission denied';

    const ok = await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );
    expect(ok).toBe(false);
  });

  it('creates the destination directory with 0700 mode', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);

    await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );

    const dest = join(tmp, 'runs', tid, 'kali-side', 'sess-1');
    expect(existsSync(dest)).toBe(true);
    // Mask to permission bits; the high bits include S_IFDIR which
    // varies by platform.
    expect(statSync(dest).mode & 0o777).toBe(0o700);
  });

  it('chmods harvested files to 0600 and dirs to 0700 recursively', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);

    const dest = join(tmp, 'runs', tid, 'kali-side', 'sess-1');
    mkdirSync(join(dest, 'pty'), { recursive: true });
    mkdirSync(join(dest, 'pcap'), { recursive: true });
    writeFileSync(join(dest, 'pty', 'typescript'), 'x');
    writeFileSync(join(dest, 'pcap', 'session.pcap'), 'binary');

    await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );

    expect(statSync(join(dest, 'pty')).mode & 0o777).toBe(0o700);
    expect(statSync(join(dest, 'pcap')).mode & 0o777).toBe(0o700);
    expect(statSync(join(dest, 'pty', 'typescript')).mode & 0o777).toBe(0o600);
    expect(statSync(join(dest, 'pcap', 'session.pcap')).mode & 0o777).toBe(0o600);
  });

  it('never changes the mode of a file that a harvested link points to (#1242)', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);
    const outside = join(tmp, 'host-file.txt');
    writeFileSync(outside, 'host');
    chmodSync(outside, 0o644);
    const dest = join(tmp, 'runs', tid, 'kali-side', 'sess-1');
    mkdirSync(dest, { recursive: true });
    symlinkSync(outside, join(dest, 'link'));

    await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-1',
    );

    expect(statSync(outside).mode & 0o777).toBe(0o644);
  });

  it('rejects an unsafe session id without invoking docker cp', async () => {
    const tid = 'a'.repeat(32);
    activateScenario(tid);

    const ok = await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      '../escape',
    );
    expect(ok).toBe(false);
    expect(spawnControl.callCount).toBe(0);
  });

  it('honours an explicit runId opt (bypasses ambient trace context)', async () => {
    // Active trace context says X; explicit runId says Y; harvest
    // must pin to Y (codex pre-push cycle 3 finding-6).
    activateScenario('x'.repeat(32));
    await harvestSession(
      {
        containerName: 'aptl-kali',
        env: { APTL_STATE_DIR: tmp },
        runId: 'y'.repeat(32),
      },
      'sess-1',
    );
    expect(spawnControl.capturedArgs[0]).toEqual(brokerArgs('await-session', 'aptl-kali', 'y'.repeat(32), 'sess-1'));
    expect(cpCalls()[0][1]).toContain(`/var/log/aptl/captures/${'y'.repeat(32)}/sessions/sess-1/.`);
  });
});

describe('#1242: workspace-scoped capture container (recorded docker cp)', () => {
  const sessionDir = (session: string) => join(tmp, 'runs', RUN, 'kali-side', session);
  const failureRecord = (session: string) =>
    join(sessionDir(session), 'capture-harvest-failure.json');
  const harvest = (containerName: string, session = 'sess-1') =>
    harvestSession({ containerName, env: { APTL_STATE_DIR: tmp } }, session);
  /** Stand in for the sidecar `name` after the broker recorded `session`. */
  const brokerContainer = (name: string, session: string) => {
    const root = join(tmp, 'container');
    const runRoot = join(root, ROOT, RUN);
    mkdirSync(join(runRoot, 'sessions', session), { recursive: true });
    writeFileSync(join(runRoot, 'accepted-sessions.jsonl'), `{"session_id":"${session}"}\n`);
    writeFileSync(join(runRoot, 'sessions', session, 'frames.jsonl'), FRAMES);
    writeFileSync(join(runRoot, 'sessions', session, 'metadata.json'), METADATA);
    spawnControl.container = { name, root };
  };

  beforeEach(() => activateScenario(RUN));

  it('harvests from the sidecar name lab start injects into the shipped red config', async () => {
    vi.stubEnv('APTL_MCP_DISABLE_DOTENV', '1');
    vi.stubEnv('LILRAE_MCP_CAPTURE_CONTAINER', SCOPED);
    brokerContainer(SCOPED, 'sess-1');
    const containerName = resolveCaptureContainer(await loadLabConfig(RED_CONFIG));
    expect(containerName).toBe(SCOPED);

    expect(await harvest(containerName as string)).toBe(true);
    expect(cpCalls()).toEqual([[
      'cp',
      `${SCOPED}:${ROOT}/${RUN}/sessions/sess-1/.`,
      sessionDir('sess-1'),
    ]]);
    expect(existsSync(failureRecord('sess-1'))).toBe(false);
  });

  it('copies the session files the capture broker writes into the run evidence', async () => {
    brokerContainer(SCOPED, 'sess-1');

    expect(await harvest(SCOPED)).toBe(true);
    expect(readFileSync(join(sessionDir('sess-1'), 'frames.jsonl'), 'utf-8')).toBe(FRAMES);
    expect(readFileSync(join(sessionDir('sess-1'), 'metadata.json'), 'utf-8')).toBe(METADATA);
    // The run's ledger of accepted sessions stays out of one session's evidence.
    expect(existsSync(join(sessionDir('sess-1'), 'accepted-sessions.jsonl'))).toBe(false);
  });

  const recordFor = (failure: string, container: string, session: string, exitCode: number) => ({
    failure,
    container,
    run_id: RUN,
    session_id: session,
    exit_code: exitCode,
    recorded_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
  });

  it.each([
    ['workspace-scoped', SCOPED, OTHER_WORKSPACE],
    ['fixed legacy', FIXED, SCOPED],
  ])('records a named failure in run evidence when the %s container is missing', async (_kind, name, present) => {
    // The broker recorded the session, but in a sidecar with another name.
    brokerContainer(present, 'sess-1');

    expect(await harvest(name)).toBe(false);
    expect(JSON.parse(readFileSync(failureRecord('sess-1'), 'utf-8'))).toEqual(
      recordFor('aptl.capture-harvest.container-missing', name, 'sess-1', 1),
    );
    expect(statSync(failureRecord('sess-1')).mode & 0o777).toBe(0o600);
    expect(spawnControl.callCount).toBe(1);
  });

  it('records a missing per-session subtree under its own name, not as a missing container', async () => {
    brokerContainer(SCOPED, 'sess-1');

    expect(await harvest(SCOPED, 'sess-gone')).toBe(false);
    expect(JSON.parse(readFileSync(failureRecord('sess-gone'), 'utf-8'))).toEqual(
      recordFor('aptl.capture-harvest.session-missing', SCOPED, 'sess-gone', 3),
    );
    expect(cpCalls()).toEqual([]);
  });

  it.each([
    ['an unreachable daemon', 1, 'Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?\n'],
    ['a docker binary that cannot start', -1, 'Error: spawn /usr/bin/docker ENOENT'],
  ])('records any other docker cp failure, such as %s, without its output', async (_kind, code, stderr) => {
    spawnControl.exitCode = code;
    spawnControl.stderrText = stderr;

    expect(await harvest(SCOPED)).toBe(false);
    const text = readFileSync(failureRecord('sess-1'), 'utf-8');
    expect(JSON.parse(text)).toEqual(
      recordFor('aptl.capture-harvest.copy-failed', SCOPED, 'sess-1', code),
    );
    expect(text).not.toContain(stderr.trim());
  });

  it('records an unbound red sidecar as unresolved and runs no docker cp', async () => {
    vi.stubEnv('APTL_MCP_DISABLE_DOTENV', '1');
    vi.stubEnv('LILRAE_MCP_CAPTURE_CONTAINER', undefined);
    // A legacy sidecar under the old fixed name must never stand in.
    brokerContainer(FIXED, 'sess-1');
    const containerName = resolveCaptureContainer(await loadLabConfig(RED_CONFIG)) as string;

    expect(await harvest(containerName)).toBe(false);
    expect(spawnControl.callCount).toBe(0);
    expect(JSON.parse(readFileSync(failureRecord('sess-1'), 'utf-8'))).toEqual({
      ...recordFor('aptl.capture-harvest.container-unresolved', containerName, 'sess-1', 0),
      exit_code: null,
    });
    expect(statSync(failureRecord('sess-1')).mode & 0o777).toBe(0o600);
  });

  it.each(['--privileged', '-q', 'kali:/etc', 'a b', 'x', ''])(
    'records the invalid name %j as unresolved and keeps it out of the docker argv',
    async (name) => {
      expect(await harvest(name)).toBe(false);
      expect(spawnControl.callCount).toBe(0);
      expect(JSON.parse(readFileSync(failureRecord('sess-1'), 'utf-8')).failure).toBe(
        'aptl.capture-harvest.container-unresolved',
      );
    },
  );

  it('never writes through a link already at the failure record path', async () => {
    brokerContainer(OTHER_WORKSPACE, 'sess-1');
    const outside = join(tmp, 'outside.txt');
    writeFileSync(outside, 'untouched');
    mkdirSync(sessionDir('sess-1'), { recursive: true });
    symlinkSync(outside, failureRecord('sess-1'));

    expect(await harvest(SCOPED)).toBe(false);
    expect(readFileSync(outside, 'utf-8')).toBe('untouched');
  });
});

describe('captures: docker binary resolution', () => {
  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'aptl-harvest-bin-'));
    spawnControl.callCount = 0;
    spawnControl.exitCode = 0;
    spawnControl.stderrText = '';
    spawnControl.capturedArgs = [];
    spawnControl.capturedCmds = [];
  });

  it('defaults to /usr/bin/docker (no PATH lookup)', async () => {
    // Without APTL_DOCKER_BIN set, the spawned binary must be the
    // absolute /usr/bin/docker so PATH-injection cannot redirect to
    // a hostile binary (SonarCloud hotspot S4036). Test-quality
    // review cycle 1 T-001: the mock now captures the spawned cmd
    // (previously discarded), so a regression in `dockerBin()` —
    // e.g., returning plain `'docker'` — fails this test.
    await harvestSession(
      { containerName: 'aptl-kali', env: { APTL_STATE_DIR: tmp } },
      'sess-bin',
    );
    expect(spawnControl.callCount).toBeGreaterThan(0);
    expect(spawnControl.capturedCmds[0]).toBe('/usr/bin/docker');
    // Every subsequent spawn (globals harvest) must use the same path.
    for (const cmd of spawnControl.capturedCmds) {
      expect(cmd).toBe('/usr/bin/docker');
    }
  });

  it('honours APTL_DOCKER_BIN override', async () => {
    // Test-quality review cycle 1 T-002: previously this test could
    // not observe whether APTL_DOCKER_BIN was actually consumed —
    // the mock discarded `_cmd`. With cmd capture in place, a
    // regression that ignores the env override fails this test.
    await harvestSession(
      {
        containerName: 'aptl-kali',
        env: { APTL_STATE_DIR: tmp, APTL_DOCKER_BIN: '/opt/docker/bin/docker' },
      },
      'sess-bin',
    );
    expect(spawnControl.callCount).toBeGreaterThan(0);
    expect(spawnControl.capturedCmds[0]).toBe('/opt/docker/bin/docker');
    for (const cmd of spawnControl.capturedCmds) {
      expect(cmd).toBe('/opt/docker/bin/docker');
    }
  });
});

describe('copy only after the broker confirms final metadata (#1541)', () => {
  const sessionDir = (session: string) => join(tmp, 'runs', RUN, 'kali-side', session);
  const failureRecord = (session: string) =>
    JSON.parse(readFileSync(join(sessionDir(session), 'capture-harvest-failure.json'), 'utf-8'));
  const runRoot = () => join(tmp, 'container', ROOT, RUN);

  // The broker has written frames but not yet metadata.json.
  const framesOnly = (session: string) => {
    mkdirSync(join(runRoot(), 'sessions', session), { recursive: true });
    writeFileSync(join(runRoot(), 'sessions', session, 'frames.jsonl'), FRAMES);
    spawnControl.container = { name: FIXED, root: join(tmp, 'container') };
  };
  const harvest = (session: string) =>
    harvestSession({ containerName: FIXED, env: { APTL_STATE_DIR: tmp } }, session);

  beforeEach(() => activateScenario(RUN));

  it('copies a finalized session once, after the broker check', async () => {
    framesOnly('sess-1');
    writeFileSync(join(runRoot(), 'sessions', 'sess-1', 'metadata.json'), METADATA);

    expect(await harvest('sess-1')).toBe(true);
    expect(spawnControl.capturedArgs).toEqual([
      brokerArgs('await-session', FIXED, RUN, 'sess-1'),
      ['cp', `${FIXED}:${ROOT}/${RUN}/sessions/sess-1/.`, sessionDir('sess-1')],
    ]);
    expect(readFileSync(join(sessionDir('sess-1'), 'metadata.json'), 'utf-8')).toBe(METADATA);
  });

  it('records an unfinished session and copies no frames', async () => {
    framesOnly('sess-1');

    expect(await harvest('sess-1')).toBe(false);
    expect(failureRecord('sess-1').failure).toBe('aptl.capture-harvest.metadata-missing');
    expect(failureRecord('sess-1').exit_code).toBe(4);
    expect(cpCalls()).toEqual([]);
    expect(existsSync(join(sessionDir('sess-1'), 'frames.jsonl'))).toBe(false);
  });

  it('fails a copy that arrives without metadata.json', async () => {
    spawnControl.copyMetadata = false;

    expect(await harvest('sess-1')).toBe(false);
    expect(failureRecord('sess-1').failure).toBe('aptl.capture-harvest.metadata-missing');
    expect(cpCalls()).toHaveLength(1);
  });

  it('records any other broker failure as finalize-failed and copies nothing', async () => {
    spawnControl.awaitExit = 1;
    spawnControl.awaitStderr = 'ValueError: capture run authority mismatch\n';

    expect(await harvest('sess-1')).toBe(false);
    expect(failureRecord('sess-1').failure).toBe('aptl.capture-harvest.finalize-failed');
    expect(cpCalls()).toEqual([]);
  });

  it('logs bounded, redacted Docker stderr on one line', async () => {
    const logged: string[] = [];
    const spy = vi.spyOn(console, 'error').mockImplementation((...parts: unknown[]) => {
      logged.push(parts.map(String).join(' '));
    });
    spawnControl.exitCode = 1;
    spawnControl.stderrText = `Error: password=hunter2\r\nforged log line\n${'x'.repeat(10000)}`;
    try {
      expect(await harvest('sess-1')).toBe(false);
    } finally {
      spy.mockRestore();
    }
    const line = logged.find((text) => text.includes('docker cp failed')) ?? '';
    expect(line).not.toBe('');
    expect(line).not.toContain('hunter2');
    expect(line).not.toMatch(/[\r\n]/);
    expect(line.length).toBeLessThan(2300);
  });
});


describe('trusted broker session finalization', () => {
  beforeEach(() => activateScenario(RUN));

  it('passes exact run and session arguments to the configured sidecar', async () => {
    expect(await finalizeCaptureSession({ containerName: SCOPED, env: { APTL_STATE_DIR: tmp } }, 'sess-1')).toBe(true);
    expect(spawnControl.capturedArgs).toEqual([[
      'exec', '--user', 'root', SCOPED, 'python3', '/usr/local/bin/broker.py',
      'stop-session', '--run-id', RUN, '--session-id', 'sess-1',
    ]]);
  });

  it.each([
    [SCOPED, 'aptl.capture-harvest.finalize-failed', 1],
    ['', 'aptl.capture-harvest.container-unresolved', 0],
  ])('records finalization failure for container %j', async (containerName, failure, calls) => {
    spawnControl.awaitExit = 1;
    expect(await finalizeCaptureSession({ containerName, env: { APTL_STATE_DIR: tmp } }, 'sess-1')).toBe(false);
    const record = JSON.parse(readFileSync(join(tmp, 'runs', RUN, 'kali-side', 'sess-1', 'capture-harvest-failure.json'), 'utf-8'));
    expect(record.failure).toBe(failure);
    expect(spawnControl.callCount).toBe(calls);
  });
});
