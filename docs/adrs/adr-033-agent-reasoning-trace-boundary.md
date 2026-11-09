# ADR-033: Red-Side Behavioural Capture and Non-Contamination Boundary

## Status

accepted

## Date

2026-05-17

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [capture explanation](../components/red-side-capture-boundary.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

OBS-003 ("Agent Reasoning Traces") was originally stated as "the platform
shall capture agent reasoning traces that record why decisions were
made." The first draft interpreted reasoning as prompts, completions, and assistant rationale. It proposed OpenTelemetry `gen_ai.prompt.*` and `gen_ai.completion.*` events. This revision supersedes that draft.

That framing is architecturally wrong for APTL. APTL's "agent" is the
external MCP client (Claude Code, Cursor, Codex, Aider, or any other
coding-agent CLI the experimenter picks up). The LLM call happens
out-of-process; the MCP protocol does not transport the assistant's
prompt or completion to APTL's MCP servers. The only thing that
crosses into APTL's address space is `tool_call(name, args)` →
`tool_response(body)`.

Reasoning capture needs the agent CLI's own configured transcript or an owned agent loop. Agent configuration belongs to the experimenter. An in-repository loop was outside OBS-003 and would pre-empt EXP-002 onward.

What IS in APTL's control is **the agent↔platform boundary and the
boxes we own**. APTL owns:

- the MCP servers (`aptl-red`, `aptl-mcp-common`, etc.), and
- the Kali container the agent SSHes into, and
- the lab's docker-compose topology.

The lab owns the command boundary, shell, and network capture path. Those layers can record observed bytes with correlation, subject to the stated capture limits.

There is a second concern. Today's lab routed red-side activity
(Wazuh agent on Kali + rsyslog → Wazuh manager + `kali_redteam_rules.xml`
decoder) into the blue defensive stack's SIEM. Attacker-authored logs would give blue knowledge beyond its sensors. The experiment therefore separates red self-reports from defensive observations. For purple-loop experiments
where we compare how blue agents reason about partial information,
that injection contaminates the experiment.

## Decision

OBS-003 is reinterpreted as **comprehensive behavioural capture on
APTL-owned infrastructure, with no scenario information bleeding
across the red/blue boundary**.

### 1. Capture surfaces

All capture happens on machines and process boundaries that APTL
owns.

**MCP-side (inside the MCP server process)**

| Capture | Where | Notes |
|---|---|---|
| Tool-call records (full args + result, exit code, signal, success, timing, session id) | `mcp/mcp-red/src/capture.ts` writes to `<state_dir>/runs/<trace_id>/mcp-side/tool-calls.jsonl` (or `_unbound` when no scenario context) | Already untruncated in the JSONL; the OTel span attribute carries a hash + offset reference and a small preview only. |
| Continuous PTY tee—every byte read from the SSH PTY, timestamped, base64-encoded for byte-fidelity | `mcp/aptl-mcp-common/src/runs.ts` (`createPtyTeeWriter`) called from `PersistentSession` in `ssh.ts`; writes `<state>/runs/<trace_id>/mcp-side/sessions/<session_id>.jsonl` | Closes the chunk-loss gap where bytes arriving between caller polls had no independent record. |
| OCSF activity events | `mcp/mcp-red/src/logger.ts` writes to `<state>/runs/<trace_id>/mcp-side/ocsf.jsonl` (and to stderr for local dev) | Schema, classifier, extractor, taxonomy, MITRE mappings from ADR-027 are unchanged; only the SIEM-shipping transport is removed. |
| Correlation env vars | `mcp/aptl-mcp-common/src/ssh.ts` passes `APTL_SESSION_ID`, `APTL_RUN_ID`, `APTL_TRACE_ID` via SendEnv when opening the SSH shell | Kali's `sshd_config` declares `AcceptEnv APTL_*`. |

**Kali-container-side (inside the box the agent operates against)**

| Capture | Tool | Where |
|---|---|---|
| Process / file / network syscall events | `auditd` with `containers/kali/audit/aptl.rules` (execve, connect, file ops on /home/kali, /tmp, /root, /etc) | `/var/log/audit/audit.log` |
| Process accounting (who ran what, when) | `accton` writing to `pacct` | `/var/log/account/pacct` |
| Per-session PTY (every keystroke + every byte of output, with timing) | `script -q -f --timing` invoked by the sshd `ForceCommand` wrapper `containers/kali/scripts/aptl-wrap-shell.sh` | `/var/log/aptl/runs/<run_id>/kali-side/<session_id>/pty/{typescript,timing}` |
| Per-session network capture (rolling 1GB cap per session) | `tcpdump -i any -w … -C 100 -W 10` started by the wrapper | `/var/log/aptl/runs/<run_id>/kali-side/<session_id>/pcap/session.pcap` |

`docker-compose.yml` mounts the docker-managed **named volume**
`kali_captures` at `/var/log/aptl/captures` inside the kali
container (NOT a host bind mount). Per-session captures land under
`/var/log/aptl/captures/<run_id>/<session_id>/` in the volume; the
MCP-red server harvests them out via `docker cp` on session close
into `.aptl/runs/<run_id>/kali-side/<session_id>/` on the host with
0600 permissions. The named-volume design closes a tampering
primitive—a host bind-mount would expose every prior run's
MCP-side records to the (passwordless-sudo) kali user.

The earlier Kali design granted `AUDIT_CONTROL` and `AUDIT_WRITE` for boot rules. `capsh --drop=cap_audit_control` then removed audit control from the sshd parent. That design intended to prevent `sudo auditctl -D` during the scenario.

### 2. Kali process lifecycle and readiness

The Kali entrypoint owns startup of sshd plus the OBS-003 capture
daemons (`auditd` and process accounting). Because that entrypoint is
PID 1, it must also own child-process reaping. Plain `exec sleep infinity` cannot reap earlier children. It can hide failed startup work behind a healthy long-running container and is not sufficient supervision.

The canonical fix for Kali lifecycle bugs is either:

- run the service under a real init/reaper such as `tini`, or
- keep the entrypoint shell as PID 1 with explicit signal handling and
  `wait`/reap logic for background children it starts.

Do not solve Kali lifecycle failures by reintroducing the removed
Wazuh installer, rsyslog forwarding, `install-all.sh`, or any other
red→SIEM pipe. If a future check mentions Wazuh placeholders on Kali,
the expected invariant is that no Kali Wazuh config exists at all. Wazuh
agent rendering and placeholder validation for blue/target containers
belongs to the shared `_wazuh-agent` path recorded in ADR-020.

Kali readiness requires accepting SSH and the ForceCommand wrapper. Advertised capture daemons must run or produce an explicit degraded-startup result. Health checks must not mask a failed
boot-time child merely because port 22 is open.

### 3. Per-run aggregation directory

`<state_dir>/runs/<trace_id>/`:

```
manifest.json
mcp-side/
  tool-calls.jsonl
  ocsf.jsonl
  sessions/
    <session_id>.jsonl          # continuous PTY tee
kali-side/
  <session_id>/
    pty/{typescript,timing}
    pcap/session.pcap
    audit/                       # mounted from /var/log/audit when copied
    proc-acct/                   # mounted from /var/log/account when copied
```

`trace_id` (from `<state>/trace-context.json`) is the cross-process
correlation key. Python `aptl scenario start` generates it,
`mcp/aptl-mcp-common/src/runs.ts` resolves it on the TS side, and
the Kali shell wrapper receives `APTL_RUN_ID=<trace_id>` via SendEnv.
The directory contract is owned by `src/aptl/core/runstore.py`
(`LocalRunStore`, `resolve_active_run_dir`, session-scoped helpers)
and mirrored by `mcp/aptl-mcp-common/src/runs.ts`.

### 4. Non-contamination principle

**No scenario information crosses the red/blue boundary.** Scenario
information means:

- The defensive-stack composition (which SIEM, which IDS, which SOAR,
  which case-management system)—never inferable by the red agent.
- Red-side activity that bleeds into blue's awareness through the
  defensive stack itself—never injected.

Observation tooling installed on a box is NOT scenario information.
auditd / tcpdump / `script` running on Kali tell the agent nothing
about what Wazuh / Suricata / SOAR / TheHive look like in the lab.
They stay.

The following red→SIEM pipes are removed under this ADR:

- `containers/kali/Dockerfile` Wazuh-agent install + GPG key + apt repo.
- `containers/kali/entrypoint.sh` `SIEM_IP`-gated rsyslog→`$SIEM_IP:514`
  forwarding block and the bashrc-source of `redteam_logging.sh`.
- `containers/kali/scripts/redteam_logging.sh` (deleted).
- `containers/kali/install-scripts/install-wazuh.sh`,
  `ossec.conf.template`, `install-all.sh` (deleted).
- `containers/kali/kali-lab-install.service` (deleted—the boot-time
  Wazuh installer).
- `containers/kali/scripts/simulate_redteam_operations.sh`,
  `simulate_port_scan.sh` (deleted—scripted-scenario simulators
  that called the syslog helpers).
- `docker-compose.yml` `SIEM_IP` env var on the kali service,
  `depends_on: wazuh.manager`, the legacy `kali_logs:/var/log` named
  volume.
- `config/wazuh_cluster/kali_redteam_rules.xml`,
  `config/wazuh_cluster/kali_decoders.xml` (deleted).
- `config/wazuh_cluster/wazuh_manager.conf` `<rule_include>` of
  `kali_redteam_rules.xml`.
- `mcp/mcp-red/src/logger.ts` default sink dispatch path that fed the
  SIEM via stderr-tailing; the stderr `[OCSF]` line stays for local
  dev visibility (it now goes nowhere else).

The kali service stays on `aptl-internal` (172.20.2.x)—that
attachment exists so the agent can reach the internal target hosts
(db, files, ws01, dc, ns1), not to reach the SIEM. The Wazuh
active-response wrapper's kali-source-IP whitelist (referenced in
`wazuh_manager.conf` lines ~224 / ~308) is the blue-side prevention
chain (ADR-019 / ADR-021 / #248 / #249) and unrelated to this ADR.

### 5. Future path for blue's red-activity awareness

When a future requirement wants the blue agent to learn about red
activity (cross-team summary reports, lessons-learned overlays,
shared timelines), the answer is:

- Point blue at the experimental data store, OR
- Build a summary tool that synthesizes red captures into a
  blue-consumable feed,

and NEVER pipe red logs into the SIEM directly. The SIEM is the
defender's perception layer; it must reflect only what the defender's
own sensors detected.

### 6. Experimenter-side reasoning capture

Capturing the LLM's internal reasoning is the experimenter's
responsibility. Each coding-agent CLI (Claude Code, Codex, Cursor,
Cline, Aider) exposes its own OTel and/or transcript surface for
prompts and completions; experimenters configure those per agent.
LilRAE does not mirror agent-side reasoning streams. That separate integration would pre-empt EXP-002 design and depend on each agent CLI's changing interface.

## Security layers

- **Auth surface**: no new ingest API; captures land on the local
  filesystem (bind-mount or in-container path), readable only by the
  host's owning user. Directories are `0700`, files `0600`.
- **Secret-handling**: ADR-029 redaction stays canonical. The shared
  Python (`src/aptl/utils/redaction.py`) and TypeScript
  (`mcp/aptl-mcp-common/src/redaction.ts`) helpers run at every
  serialization boundary. A new opt-out—`APTL_EXPERIMENT_NO_REDACT=1`
—lets the experimenter preserve credentials/secrets verbatim in
  the experimental record. The toggle defaults off, fails closed
  against any non-truthy value, and never affects production traces
  (it requires explicit env-var set).
- **Env/config binding**: `APTL_EXPERIMENT_NO_REDACT` is an environment toggle outside strict `AptlConfig`. It cannot enter shipped configuration through that model. Both languages read it per call.
- **OS exposure**: bind-mount target is the host's `.aptl/runs/`
  (gitignored). Container-side captures live in `/var/log/aptl/runs/`
  (root-owned root dir, kali-writable session subdirs created by
  `entrypoint.sh`'s chown).
- **Pcap files**: contain raw network bytes by design; there is no
  semantic redaction for arbitrary binary protocols and we
  deliberately do not strip them. Pcaps inherit `0600` permissions
  and the gitignored bind-mount target. The redaction toggle does
  NOT affect pcap content.
- **Observation visibility**: the agent CAN see `auditd`, `tcpdump`,
  and `script` running on Kali (`ps aux` will show them). That is
  intentional and acceptable per the non-contamination principle—
  observation tooling is not scenario information.
- **PID 1 / OS lifecycle**: the Kali container starts child processes
  during boot. PID 1 must reap children and propagate termination. A real init or a shell that waits on its own children can supply that boundary. A
  keepalive process that only sleeps is not a lifecycle boundary and
  must not be used to hide failed boot work.
- **Capture integrity from a sudo-capable kali user** (superseded by
  [ADR-041](adr-041-kali-capture-sidecar-ownership-boundary.md) for
  [issue #305](https://github.com/Brad-Edwards/aptl/issues/305)):
  the original ADR-033 implementation left the capture volume writable
  from inside the Kali workload container. The Kali user has passwordless sudo for lab tools. Root ownership, ACLs, setuid helpers, or another capture user cannot prevent tampering within the same writable namespace.

  ADR-041 selects a capture sidecar as the ownership boundary: the
  sidecar shares ONLY Kali's network namespace (not its PID namespace,
  which would expose `/proc/<pid>/root` traversal), mounts
  `kali_captures` read-write, and owns per-session PTY, pcap, auditd,
  and process-accounting writes. Kali does NOT mount `kali_captures`
  at all (not even read-only, since a read-only mount still lets a
  sudo-root shell `cat` sibling sessions' evidence). With the sink
  absent from Kali's mount namespace, `sudo` read/list/rm/truncate/
  chmod/chown/rewrite attempts from Kali have no path to it. The
  wrapper's role narrows to validated session metadata RPC and
  best-effort shell continuation. (PTY transcript bytes are still
  supplied by the workload, so the Kali-side typescript is not
  tamper-resistant for the workload's own session; the authoritative
  keystroke/output record remains the MCP-side PTY tee.)

  Until the ADR-041 implementation lands, the current code still carries
  the residual risk described above. The implementation must preserve the
  existing mitigations that remain valid: MCP-side PTY tee outside the
  container, fail-loud `harvestSession()` missing-source reporting, and
  restrictive harvested host-side modes.
- **Harvest race window** (closed by
  [issue #304](https://github.com/Brad-Edwards/aptl/issues/304)):
  `PersistentSession.close()` now resolves only after the SSH stream's
  remote `close` event has fired (or a bounded
  `TIMEOUTS.REMOTE_CLOSE_AWAIT` has elapsed with a logged
  `[SSH] remote close timeout` warning). The wrapper EXIT trap stops tcpdump and flushes the `script(1)` typescript on remote channel close. Awaiting that event before harvest closes the recorded truncation race. The previous helper used three 250 ms retries to mask the race. It was removed. Missing-source stderr remains necessary to disclose deleted capture sources. Local
  cleanup—rejecting in-flight and queued command promises—is still
  synchronous so command callers are not blocked by the remote-close
  await.
- **Error envelopes**: capture failures log to stderr only. The
  PostToolHook architecture from ADR-027 still applies: capture or
  OCSF emission errors never break tool execution.

## Maintainability

Canonical incumbents the OBS-003 implementation extends rather than
duplicates:

- `src/aptl/core/runstore.py`: `LocalRunStore` already owns the per-run
  directory contract, manifest schema, and redacted writes; the OBS-003
  additions are session-scoped subdirectory helpers
  (`mcp_side_dir`, `kali_side_session_dir`, `mcp_session_jsonl`) and a
  trace-context-driven resolver (`resolve_active_run_dir`).
- `src/aptl/utils/redaction.py` and
  `mcp/aptl-mcp-common/src/redaction.ts`—the `_experiment_no_redact`
  toggle is a leading guard inside the existing `redact()` function;
  no parallel "sanitizeReasoning" policy.
- `mcp/aptl-mcp-common/src/ssh.ts` `PersistentSession` —
  `createPtyTeeWriter` is invoked from the existing `stream.on('data')`
  / `stream.stderr.on('data')` handlers; no second I/O path.
- `mcp/aptl-mcp-common/src/telemetry.ts` `traceToolCall`—extension
  is small attribute additions, not a new tracing pipeline.
- `mcp/mcp-red/src/logger.ts`: the OCSF schema/classifier/extractor
  + the post-tool-hook architecture from ADR-027 are unchanged; only
  the sink/transport changed (stderr-only → stderr + per-run JSONL,
  no SIEM dispatch).
- `containers/kali/scripts/aptl-wrap-shell.sh` is the shared shell wrapper. sshd ForceCommand makes it the Kali entry point, so capture wiring has one owner.

## Extensibility

The seam is `<state>/runs/<run_id>/`. Any future capture source
(host-side eBPF, additional Kali-side instrumentation, per-agent
transcript ingestors when those become in scope) writes into a new
subdirectory under that root without touching existing code. The
`APTL_EXPERIMENT_NO_REDACT` env var is the seam for per-run redaction
policy without changing call sites.

## Non-goals

- Hidden chain-of-thought capture (the LLM's internal reasoning is
  out-of-process—experimenter's concern).
- A new database, queue, sidecar, or long-lived capture service for
  OBS-003.
- Re-implementation of OTel, Tempo, run archives, MCP execution, the
  OCSF schema vocabulary, or the existing Wazuh / Suricata / SOAR
  defensive stack.
- Per-agent CLI transcript ingestors (Claude Code JSONL, Codex JSONL).
  These are deferred to future, per-agent integration work.
- Adoption of MCP spec extensions (for example `_meta.traceparent`,
  modelcontextprotocol/modelcontextprotocol#246)—forward-looking
  and outside the OBS-003 boundary.
- Pcap content redaction—deliberately out of scope. Pcaps are raw
  wire bytes; semantic redaction does not apply.
- Installing, configuring, or health-checking a Wazuh agent on Kali.
  That red→SIEM path was removed by this ADR; Wazuh placeholder
  handling remains in the target/blue agent bootstrap paths, not in
  Kali.

## Anti-patterns

- Scraping `aptl.tool.response` or command stdout to infer assistant
  rationale.
- Writing raw prompts/completions to `.aptl/` files and relying on
  `0600` permissions instead of redaction and bounded serialization.
- Adding per-agent schemas that duplicate GenAI prompt/completion
  event concepts with incompatible field names.
- Hard-coding one provider's response format into `aptl-mcp-common`,
  runstore, collectors, or exporters.
- Turning capture into a required synchronous step on the tool-call
  response path (capture is best-effort and runs alongside the
  response, not in front of it).
- Re-introducing any red→SIEM pipe (rsyslog forwarding, Wazuh agent
  on Kali, OCSF dispatch to a SIEM sink, etc.) without an ADR that
  explicitly overrides the non-contamination principle.
- Ending the Kali entrypoint with an unreaping `sleep`, `tail -f`, or
  equivalent keepalive after spawning background children.
- Treating "SSH port open" as complete Kali readiness when the
  advertised capture surface failed during startup.
- Treating `APTL_EXPERIMENT_NO_REDACT=1` as a default-on setting in
  production. It is an experimenter-side opt-out, never a baseline.
