# Issue #1418: Participant MCP action admission

This preflight covers the supplied #1418 contract: admit and observe red and
blue MCP tool calls through the RAES participant runtime. It is guidance, not
an implementation plan. The issue has no Ground Control requirement. Its
native blocked-by dependencies remain authoritative; “issue-plan items 11
and 34” are not enough information to infer their contracts or completion.

## Decision and current boundary

RAES owns participant admission, episode lifecycle, action identity, ordering,
and accepted behavior history. LilRAE binds a tool invocation to that authority
and executes its existing MCP handler only after admission permits execution.
ADRs [003](../adrs/adr-003-mcp-common-library.md),
[029](../adrs/adr-029-control-plane-secret-handling.md),
[033](../adrs/adr-033-agent-reasoning-trace-boundary.md), and
[050](../adrs/adr-050-terminal-attempt-archival-and-atomic-seal.md) already own
the relevant boundaries. No new ADR or policy engine is needed.

The current paths solve different parts of this problem:

- `backends/raes_participant_runtime.py` extends RAES `BaseParticipantRuntime`.
  Its `admit_action()` retains RAES history; `_model_action()` dispatches native
  work. `raes_participant_driver.py` already uses published admission requests,
  the v2 binder, and control-plane receipts. Reuse the applicable published
  admission path; do not force autonomous tools through a decision-only
  provider solicitation or the frozen bounded-agency scenario registry.
- `backends/lilrae_participant_execution.py` binds exact participant/action/
  target relations and supervises autonomous invocations. A harness invocation
  is an outer action. Its terminal result does not record its individual tool
  calls. `lilrae_participant_workload.py` owns the trial's RAES manager and
  consumes settled history.
- `workbench/relay.py` checks protocol and live access before forwarding calls.
  SSH dispatch and `browser_mcp.py` share it. Autonomous OpenCode, managed
  agent, and authenticated host participant adapters can instead launch MCP
  servers directly. Instrumenting only the guest relay leaves those paths
  uncovered.
- `mcp/aptl-mcp-common/src/server.ts` owns generated tools, argument validation,
  dispatch, and tracing for SSH and API servers. Its `postToolHook` is
  asynchronous best-effort observation. Red capture and OCSF use that hook;
  neither it nor OTel can enforce admission or establish portable history.

Python paths above and below are relative to `src/aptl/` unless stated otherwise.

## Admission and execution guardrails

The common tool dispatch boundary is the enforcement seam shared by both
roles. The management side supplies a narrow connection to the existing RAES
runtime owner. It must not expose a runtime manager, deployment client,
arbitrary backend method, or evaluator store to the participant. Guest relay
authorization remains an additional gate. Any process boundary needed to
reach the runtime must be private, authenticated, bounded, and tied to its
owning invocation; no general operator API or externally published listener
is justified by this issue.

Bind run/attempt, participant, episode, implementation selection, execution
scope/generation, server, tool, action contract, observation boundary, and
permitted targets from admitted management state. Role names, tool prefixes,
JSON-RPC IDs, `_meta`, environment claims, and the active trace file are not
participant authority. A transport grant/profile needs an explicit join to
that participant context. A role is not a unique participant identifier.

The installed tool-to-action relation must resolve against the admitted
compiled model and implementation manifest. Missing, ambiguous, stale, or
cross-participant bindings fail before handler effects. No fallback to a
generic command action, invented contract address, default red participant,
or automatically initialized episode. A tool may have several native effects;
record the admitted invocation without pretending to enumerate every shell
command or downstream SOC job.

Keep the SDK envelope and common Ajv argument validators ahead of native
execution. They enforce the advertised schema without coercion or defaults.
RAES separately validates action authority, arguments, observation boundaries,
and runtime state. These checks serve distinct contracts: do not port tool
JSON Schema validation into Python or encode RAES policy independently in
TypeScript. Schema rejection is not an executed action. Denied requests remain
observable through the existing refusal/diagnostic contracts without claiming
a terminal native result that never happened.

Each admitted tool invocation needs its own action identity and outcome,
correlated to the outer invocation through supported RAES coordinates. MCP
IDs are connection-local and reusable across connections. Idempotency must
include trusted invocation context and the exact semantic request. Repeated
delivery must not repeat effects; the same key with different arguments must
be refused. Redact persisted diagnostics and evidence without changing the
arguments actually executed or collapsing distinct secret-bearing requests
into one idempotency identity.

**Contract qualification required:** `pyproject.toml` pins RAES 9.1.0. The
current repository demonstrates autonomous batch admission and v2 selected
actions, but does not demonstrate tool admission while the same participant's
outer action is running. Confirm the published contract for that relationship,
active generations, and accepted history before choosing its concrete API.
Do not assume recursive `manager.apply()` or `admit_action()` is supported.
If the pinned dependency cannot express it, surface a RAES contract gap rather
than inventing local nested-action semantics or claiming admission from a log.

RAES concurrent workers receive isolated predecessor snapshots and settle in
request order. Tool completions must enter the owning RAES settlement path;
they must survive outer-action settlement and retain the peer's history.
Never mutate `_behavior_history` directly, merge snapshots with dictionary
updates, or construct a second runtime per tool/server. Do not hold a manager
lock while waiting for a harness that needs the same lock for tool admission.
The dependency qualification must establish progress as well as correct
history under overlapping red/blue calls.

## Contract qualification result

Qualification on 2026-10-30 confirmed an upstream contract gap.
The installed RAES 9.1.0 requires exactly three history events for each scheduled action.
Every appended event must identify that same action instance and contract.
Published RAES 9.2.0 retains these checks in `participant_action_validation.py`.

The probe used the existing concurrent red/blue fixture and reference admission.
It made no model requests and caused no native lab effects.
Ordinary outer invocations succeeded with three accepted events per participant.
Adding a reference-admitted tool action to each worker snapshot caused settlement failure.
The runtime reported `runtime.participant-autonomous-action-protocol-invalid` and `runtime.control-plane.operation-indeterminate`.
Neither participant's behavior history was accepted.
The existing concurrent red/blue baseline test passed separately.

[RAES issue #1740](https://github.com/OpenRAE/rae/issues/1740) owns the missing contract.
LilRAE #1418 has a native GitHub blocked-by relationship to that issue.
Implementation must wait for a supported, released contract and consumer qualification.
Do not weaken settlement checks or replace accepted history with logs.
The user prohibits work in other checkouts or worktrees.
The upstream issue records the required work for its owning development session.

## Cross-cutting layers the design must pass

| Layer and canonical incumbent | Required behavior |
| --- | --- |
| Scenario, implementation, and configuration admission: `ParticipantPlanAuthority`, `LilraeParticipantBinding`, `_raes_participant_manifest.py`, `raes_manifest.py`, RAES contracts | Use the compiled action/target relation, installed manifest and selection, and active episode/generation. Preserve manifest capability checks and configuration digests; advertise only qualified tool behavior. |
| Harness configuration: `workbench/agent.py`, `codex_agent.py`, `_raes_participant_transport.py`, `lilrae_opencode.py`, `profiles.py` | Preserve private-file ownership, no-follow reads, unchanged-config digests, exact inventory, credential aliases, allowed environment sets, and default-deny tools. Internal generated entries require exactly `{command,args,env}`; external client serializers have their own shapes. Do not smuggle context in unknown fields. |
| Durable config and environment: `core/config.py`, `core/env.py`, MCP `config.ts`, `workbench/guest_binding.py` | Retain strict first-party models and typed binding validation. Extend the canonical model/renderer/consumer together only if needed. Keep `APTL_HP_*` values decimal ports; do not use that channel for tokens, paths, or JSON. Preserve `APTL_MCP_DISABLE_DOTENV=1` on restricted guest launches. New identifiers follow ADR-062; existing interfaces retain their names. |
| External auth and transport: `workbench/access.py`, `GuestAdmission`, `DispatchSelector`, `ProtocolAdmission`, `browser_mcp.py`, `access_clients.py` | Retain grants, role/server restrictions, instance/generation and native identity checks, revocation, exact inventory, SSH key pins/forced commands and disabled forwarding, browser session and Origin checks. Preserve operator `api/deps.py` and BFF Host/session/CSRF gates if traversed; do not reuse an operator token as participant authority. |
| Tool validation and native effects: MCP `server.ts`, generated definitions/handlers, `endpoint-url.ts`, `http.ts`, `ssh-manager.ts`, `ssh-session.ts` | Keep Ajv closed arguments and predefined-query parameter/path checks, configured-origin HTTP restriction, current TLS/CA policy, SSH host-key verification, session ownership, command limits and teardown. Admission does not bypass these. Use existing handlers; add no parallel SSH, HTTP, or shell runner. |
| OS and secret exposure: `workbench/process.py`, `credentials.py`, `utils/pathsafe.py`, `utils/curl_safe.py`, ADR-029 | Use admitted executable/argv arrays, explicit minimal environments, private no-follow files, credential leases and process-group supervision. No credentials or secret-bearing payloads in argv, URLs, logs or exception text. No ambient provider credentials, participant daemon sockets, or evaluator mounts. Private runtime access must not become a reusable peer/control-plane credential. |
| Errors and results: RAES `Diagnostic`, `ParticipantActionApplyResult`, `ParticipantActionResultModel`, operation receipts/status, `WorkbenchConfigurationError`, `AgentExecutionError`, `BoundedProcessError` | Preserve typed refusals and native outcomes. Map JSON-RPC errors, MCP `isError`, handler payload `success:false`, exit status, timeout and unknown cleanup deliberately. A resolved Promise or `ApplyResult.success` does not prove tool success. Retain bounded safe client errors, including relay error masking; never return raw validators, provider output, stacks or secrets. Add no exception hierarchy. |
| Evidence and observability: `core/runstore.py`, `raes_participant_evidence_publication.py`, `utils/logging.py`, Python/TS `redact`, `workbench/mcp_results.py`, MCP `telemetry.ts` and `runs.ts` | Persist accepted RAES history through the existing run store and evidence owner; retain atomic source records and recoverable projections where applicable. Correlate operation/action, participant/episode, invocation/generation and admitted run/attempt. Trace IDs correlate; they do not authorize or select another run. Redact before storage, logs, traces and client serialization. Preserve typed terminal handles and tool schemas. No `_unbound` fallback for governed participant history. |
| Visibility and finalization: participant projection/exposure modules, `core/correlation/`, `core/evidence/`, ADRs 033 and 050 | Keep participant observations separate from evaluator evidence. Blue sees its permitted tool results and sensors, not red history injected into its SIEM. Drain calls and publication before the existing terminal seal; no late writes to sealed runs, second archive, evaluator, or finalization controller. |

## Failure, extensibility, and evidence boundaries

Admission is mandatory for governed participant calls. Runtime unavailability
or loss of authority fails closed before dispatch. After dispatch, cancellation,
timeout, disconnect or an unavailable completion channel can leave effects
unknown. Preserve that distinction through RAES; do not retry effects to
repair missing evidence. Recording an accepted result and publishing its
archive projection are separate concerns. Publication failure must remain
visible without erasing accepted history or replaying execution. OCSF and OTel
remain best effort and cannot substitute for required RAES recording.

Retain the existing frame/output/queue limits, per-action and outer deadlines,
revocation watchers, cancellation signals, native cleanup and taint rules.
Budget admission, execution, settlement, and cleanup together. The relay's
120-second response wait must not silently truncate a longer admitted action
and invite retry. Session creation, reads, writes, closure, and blue API calls
all need consistent invocation semantics. A background session or raw PTY
write does not prove completion of the work it starts; use observed outcomes.
Cleanup must remain available to the trusted supervisor after participant
authority is revoked, without granting further participant work.

The extensibility seam is an installed binding parameterized by participant
identity, server/tool identity, action contract, boundary, and allowed targets,
delivered through each existing harness/config adapter. It must accommodate a
second participant of the same role or another qualified server without
editing a role switch or copying admission logic. Do not introduce a second
tool catalog or action-schema registry. Standalone operator MCP use remains
explicitly distinct from governed participant execution; it cannot silently
become an unadmitted participant fallback.

Qualification should reuse the real-scheduler concurrency tests
(`tests/test_lilrae_concurrent_participants.py`), real-pipe relay tests
(`tests/test_mcp_relay.py`), dispatch/guest-binding and harness/config tests,
common `server-logic.test.ts`/`server-hook.test.ts`, HTTP security tests, and
redaction parity tests. Evidence must show red SSH and blue API calls reaching
the existing handler once, refusal before effects, repeated/stale/spoofed
requests, overlapping completion retaining both histories, disconnect and
cancellation cleanup, and credential canaries absent from every projection.
Exercise direct-harness and guest/browser paths; a session-level history event
or a hook mock alone cannot qualify this issue.

Local checks remain change-scoped under `.ground-control.yaml`: explicit paths
through `tools/run-targeted-tests.sh` and staged `pre-commit run`. Common MCP
changes select their consumers; CI rebuilds/tests all dependents. Lifecycle or
config changes also need the repository's installed-lab qualification. Full
suites, coverage, and whole-tree prose checks stay in CI. One issue retains
one delivery PR; no synthetic requirement UID or requirement transition.

## Non-goals

This issue does not replace RAES scheduling, add a participant policy engine,
reclassify OCSF events as RAES events, or promise every OS/network effect is a
tool call. It does not add model/prompt configuration, a harness, provider,
service, public endpoint, capture format, or run archive. It does not redesign
scenario composition, grant broader tools, weaken isolation, or make cleanup
equivalent to rollback. It must not claim closure of neighboring configuration,
study assembly, or pack-authoring work from tool-call admission alone.
