/**
 * Per-session capture harvest from the Kali capture sidecar.
 *
 * OBS-003 / ADR-033 / ADR-041 design: the `aptl-kali-capture` sidecar (not the
 * Kali workload) records each session through its SSH/PTY broker
 * (`containers/kali-capture/broker.py`) into a docker named volume, as
 * `frames.jsonl` and `metadata.json` under
 * `/var/log/aptl/captures/<run_id>/sessions/<session_id>/`. The Kali workload does not
 * mount the volume at all, so a sudo-capable agent cannot read or tamper with
 * evidence (ADR-041). The volume is invisible to the host filesystem to
 * prevent cross-scenario tampering (codex pre-push cycle 1 finding-10).
 *
 * When an SSH session closes, the MCP server invokes `harvestSession()` which
 * runs `docker cp` against the capture container (the sidecar — see
 * `resolveCaptureContainer` / `capture_container_name`) to copy the
 * per-session subtree out into `<run_store_base>/<run_id>/kali-side/<session_id>/`
 * on the host, then sets 0600 permissions on every file. The harvest is
 * best-effort — a missing container / docker / missing subdir logs to stderr
 * but does not throw out of the close path. Each of those failures also
 * leaves a named failure record in the session's kali-side evidence (#1242).
 */

import { spawn } from 'node:child_process';
import { chmod, mkdir, readdir, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

import { kaliSideSessionDir, loadActiveTraceId } from './runs.js';

export interface HarvestOptions {
  /** Docker container to harvest from. Per ADR-041 this is the capture
   * sidecar (e.g. `aptl-kali-capture`), which owns the captures volume. */
  containerName: string;
  /** Path inside the container that holds per-run capture subdirs.
   * Defaults to `/var/log/aptl/captures` to match the capture broker. */
  containerCapturesRoot?: string;
  /** APTL state directory on the host (defaults to `APTL_STATE_DIR`
   * env var or `.aptl`). */
  stateDir?: string;
  /** Env to pass through; used for testability. */
  env?: NodeJS.ProcessEnv;
  /** Bind harvest to a specific run id rather than re-reading the
   * active trace context. Set when a long-running session captured
   * its run_id at open time and the active trace context may have
   * rotated since (codex pre-push cycle 3 finding-6). */
  runId?: string;
}

const DEFAULT_CONTAINER_CAPTURES_ROOT = '/var/log/aptl/captures';

/** Named harvest failures, recorded in the run evidence (#1242). */
const CONTAINER_MISSING = 'aptl.capture-harvest.container-missing';
const SESSION_MISSING = 'aptl.capture-harvest.session-missing';
const COPY_FAILED = 'aptl.capture-harvest.copy-failed';
type HarvestFailure = typeof CONTAINER_MISSING | typeof SESSION_MISSING | typeof COPY_FAILED;
/** Evidence record for a failure, inside the session's kali-side dir. */
const HARVEST_FAILURE_FILE = 'capture-harvest-failure.json';

// Override via `APTL_DOCKER_BIN` for non-standard installations.
// Default to the standard absolute path so the spawn does NOT rely
// on PATH lookup (SonarCloud hotspot captures.ts:47 — a writable
// PATH directory could otherwise execute an attacker-controlled
// `docker`). Falls back to plain `docker` only when the absolute
// path is missing AND the env override is unset; in that case the
// developer is expected to have a controlled PATH.
const DEFAULT_DOCKER_BIN = '/usr/bin/docker';

function dockerBin(env: NodeJS.ProcessEnv = process.env): string {
  const override = env.APTL_DOCKER_BIN;
  if (override && override.length > 0) return override;
  return DEFAULT_DOCKER_BIN;
}

function execDockerCp(
  args: string[],
  env: NodeJS.ProcessEnv = process.env,
): Promise<{ code: number; stderr: string }> {
  // Thread the caller's env through so APTL_DOCKER_BIN overrides set on
  // HarvestOptions actually reach dockerBin(). Without this, the test
  // mock could not observe the override and the SonarCloud S4036
  // "no PATH lookup" contract was unverifiable. (Test-quality review
  // cycle 1 T-002.)
  return new Promise((res) => {
    const child = spawn(dockerBin(env), args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    child.stderr.on('data', (b) => {
      stderr += b.toString();
    });
    child.on('error', (err) => {
      res({ code: -1, stderr: String(err) });
    });
    child.on('close', (code) => {
      res({ code: code ?? -1, stderr });
    });
  });
}

async function chmodTreeBestEffort(root: string, fileMode: number, dirMode: number): Promise<void> {
  // Recursively chmod every file/dir under root. Best-effort: a
  // missing path or permission denied is logged, not thrown.
  try {
    const entries = await readdir(root, { withFileTypes: true });
    for (const entry of entries) {
      const full = join(root, entry.name);
      try {
        if (entry.isDirectory()) {
          await chmod(full, dirMode);
          await chmodTreeBestEffort(full, fileMode, dirMode);
        } else {
          await chmod(full, fileMode);
        }
      } catch (err) {
        console.error(`[captures] chmod ${full} failed:`, err);
      }
    }
  } catch (err) {
    console.error(`[captures] readdir ${root} failed:`, err);
  }
}

interface ResolvedHarvestParams {
  env: NodeJS.ProcessEnv;
  stateDir: string;
  containerCapturesRoot: string;
  tid: string;
}

/**
 * Resolve the effective env, state dir, container captures root, and run id
 * for a harvest. Run id resolution: explicit `opts.runId` wins (passed by
 * persistent-session callers that captured the active trace at session open
 * time), otherwise re-read the current trace context, falling back to
 * `_unbound` so harvests outside a scenario context still land somewhere
 * predictable.
 */
function resolveHarvestParams(opts: HarvestOptions): ResolvedHarvestParams {
  const env = opts.env ?? process.env;
  return {
    env,
    stateDir: opts.stateDir ?? env.APTL_STATE_DIR ?? '.aptl',
    containerCapturesRoot: opts.containerCapturesRoot ?? DEFAULT_CONTAINER_CAPTURES_ROOT,
    tid: opts.runId ?? loadActiveTraceId(env) ?? '_unbound',
  };
}

/** Outcome of one per-session copy: `null` on success, else the failure. */
interface CopyFailure {
  failure: HarvestFailure;
  exitCode: number;
}

/**
 * Copy one session's per-session capture subtree out of the container.
 * Returns `null` on success. Otherwise logs and returns the named failure:
 * the container does not exist, the session subtree does not exist in it, or
 * docker cp failed for another reason (daemon unreachable, no docker binary).
 */
async function copyPerSessionCaptures(
  containerName: string,
  src: string,
  destDir: string,
  env: NodeJS.ProcessEnv,
  sessionId: string,
): Promise<CopyFailure | null> {
  const cpResult = await execDockerCp(['cp', `${containerName}:${src}`, destDir], env);
  if (cpResult.code === 0) return null;
  const exitCode = cpResult.code;
  // Docker reports `No such container: <name>`; a missing path inside an
  // existing container is `Could not find the file …` instead.
  if (/No such container: /i.test(cpResult.stderr)) {
    console.error(`[captures] capture container ${containerName} is missing (${CONTAINER_MISSING})`);
    return { failure: CONTAINER_MISSING, exitCode };
  }
  if (
    /No such file or directory/i.test(cpResult.stderr) ||
    /Could not find the file/i.test(cpResult.stderr)
  ) {
    // Surface the missing-source case loudly. ADR-033 + codex
    // cycle 2 finding-9: an attacker who deletes their own session
    // dir before close can wipe the Kali-side captures. Silent
    // success would convert that tampering into invisible data
    // loss. We log + record the failure so the operator sees a real
    // anomaly. The MCP-side PTY tee and tool-call JSONL remain
    // as the independent (and tamper-resistant) record.
    console.error(
      `[captures] per-session subtree missing for ${sessionId}; expected at ${src}. ` +
        'MCP-side captures remain in `.aptl/runs/<run>/mcp-side/`.',
    );
    return { failure: SESSION_MISSING, exitCode };
  }
  console.error(
    `[captures] docker cp failed (rc=${cpResult.code}):`,
    cpResult.stderr.trim(),
  );
  return { failure: COPY_FAILED, exitCode };
}

/**
 * Record a failed harvest in the run evidence, not only on stderr. The record
 * takes the captures' place in the run directory. It carries no docker
 * output. `wx` refuses to follow or replace anything at its path.
 */
async function recordHarvestFailure(
  destDir: string,
  copy: CopyFailure,
  containerName: string,
  runId: string,
  sessionId: string,
): Promise<void> {
  const record = {
    failure: copy.failure,
    container: containerName,
    run_id: runId,
    session_id: sessionId,
    exit_code: copy.exitCode,
    recorded_at: new Date().toISOString(),
  };
  const path = join(destDir, HARVEST_FAILURE_FILE);
  try {
    await writeFile(path, `${JSON.stringify(record, null, 2)}\n`, { flag: 'wx', mode: 0o600 });
  } catch (err) {
    console.error(`[captures] could not record ${copy.failure} at ${path}:`, err);
  }
}

/**
 * Verify destDir actually has content and chmod everything to 0600. Returns
 * `perSessionOk` on success, or false when the destination is missing.
 */
async function finalizeHarvest(destDir: string, perSessionOk: boolean): Promise<boolean> {
  try {
    const st = await stat(destDir);
    if (!st.isDirectory()) return false;
  } catch {
    return false;
  }
  await chmodTreeBestEffort(destDir, 0o600, 0o700);
  return perSessionOk;
}

/**
 * Harvest one session's captures out of the Kali container into
 * the host-side per-run directory.
 *
 * Returns `true` when the copy completed, `false` when the harvest
 * failed. Never throws.
 */
export async function harvestSession(opts: HarvestOptions, sessionId: string): Promise<boolean> {
  const { env, stateDir, containerCapturesRoot, tid } = resolveHarvestParams(opts);

  let destDir: string;
  try {
    destDir = kaliSideSessionDir(stateDir, tid, sessionId, env);
  } catch (err) {
    console.error('[captures] invalid run/session id; skipping harvest:', err);
    return false;
  }

  try {
    await mkdir(destDir, { recursive: true, mode: 0o700 });
  } catch (err) {
    console.error('[captures] mkdir destDir failed:', err);
    return false;
  }

  // `docker cp <container>:<src>/. <dest>` copies the CONTENTS of src
  // into dest. The trailing `/.` is important — without it docker cp
  // copies the source directory itself into dest, producing
  // dest/<session_id>/... which would nest one level too deep.
  const src = `${containerCapturesRoot}/${tid}/sessions/${sessionId}/.`;
  const failed = await copyPerSessionCaptures(opts.containerName, src, destDir, env, sessionId);
  if (failed) {
    await recordHarvestFailure(destDir, failed, opts.containerName, tid, sessionId);
  }

  return finalizeHarvest(destDir, failed === null);
}
