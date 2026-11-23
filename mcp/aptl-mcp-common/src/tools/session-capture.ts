import { type LabConfig } from '../config.js';
import { harvestSession } from '../captures.js';

/**
 * OBS-003 / ADR-033 / ADR-041: resolve the docker container the
 * close_session / close_all_sessions handlers harvest per-session captures
 * from, into `.aptl/runs/<run_id>/kali-side/<session_id>/` on the host.
 *
 * Per ADR-041 the capture sink is a dedicated sidecar that the workload
 * container does not mount, so a sudo-capable agent cannot read or tamper
 * with evidence. Harvest targets only the declared `capture_container_name`;
 * a workload container never owns captures, so there is no fallback (#1242).
 *
 * Returns `undefined` when the server declares no capture sidecar (API-only
 * servers, mcp-reverse) or when the configKey is missing — those MCP servers
 * don't ship captures and harvest is a no-op.
 */
export function resolveCaptureContainer(labConfig: LabConfig): string | undefined {
  const key = labConfig.server.configKey;
  if (!key || !labConfig.containers) return undefined;
  return labConfig.containers[key]?.capture_container_name;
}

/**
 * Run capture harvest for the named session, best-effort. Returns
 * `true` when harvest completed cleanly (or there was nothing to
 * harvest because the MCP isn't configured for captures), `false`
 * when the per-session Kali-side subtree was missing or harvest
 * otherwise failed — callers surface that as `harvest_warning` in
 * the tool result so the anomaly is visible to the tool caller
 * rather than just buried in MCP stderr (codex pre-push cycle 3
 * finding-2). Never throws.
 *
 * When `runId` is supplied, harvest uses it instead of re-reading
 * the active trace context at close time. Persistent sessions
 * capture their `run_id` at construction time and pass it here, so
 * a scenario rotation during a long-running session does not
 * cause the harvest to look under the wrong run dir (codex
 * pre-push cycle 3 finding-6).
 */
export async function maybeHarvest(
  labConfig: LabConfig,
  sessionId: string,
  runId?: string,
): Promise<boolean> {
  const containerName = resolveCaptureContainer(labConfig);
  // An absent declaration disables captures; an empty declared name must fail.
  if (containerName === undefined) return true;

  try {
    return await harvestSession({ containerName, runId }, sessionId);
  } catch (err) {
    console.error('[captures] harvest threw:', err);
    return false;
  }
}
