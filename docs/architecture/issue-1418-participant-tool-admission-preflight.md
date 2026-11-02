# Issue #1418: Participant MCP action admission

This preflight covers the supplied #1418 contract: admit and observe red and
blue MCP tool calls through the RAES participant runtime. It is guidance, not
an implementation plan. The supplied issue links DSL-010; the original
[DSL-010 preflight](../raes/dsl-010-participant-runtime-preflight.md) records
the earlier #554 backend-profile milestone. This issue extends that runtime;
it does not repeat the manifest promotion or establish all of RUN-314 alone.
Its native blocked-by dependencies remain authoritative; “issue-plan items 11
and 34” are not enough information to infer their contracts or completion.

Inspection baseline: `9ae37a5f`, with existing uncommitted architecture notes.
This preflight inspected only this repository. Earlier external qualification
reports below were not rerun or independently verified in this pass.

Delivery update: the [enforcement design](participant-action-enforcement.md)
records the subsequent implementation and qualification under RAES 10.2.0.
Retained tests now exercise the scoped adapter, released refusal boundaries,
real scheduler settlement, and real MCP clients with deterministic native substitutes.
The baseline findings below explain the controls this delivery must preserve.

## Decision and current boundary

RAES owns participant admission, episode lifecycle, action identity, ordering,
and accepted behavior history. LilRAE binds a tool invocation to that authority
and executes its existing MCP handler only after admission permits execution.
ADRs [003](../adrs/adr-003-mcp-common-library.md),
[029](../adrs/adr-029-control-plane-secret-handling.md),
[033](../adrs/adr-033-agent-reasoning-trace-boundary.md), and
[050](../adrs/adr-050-terminal-attempt-archival-and-atomic-seal.md) already own
the relevant boundaries. This preflight adds no new ADR or policy engine.

The concurrently added [proposed ADR-065](../adrs/adr-065-executable-participant-action-boundaries.md)
and [enforcement design](participant-action-enforcement.md) describe scoped
tool sessions, local IPC and finite verification models. Their proposed
status does not establish support or acceptance. Verification models must
check the existing RAES semantics without becoming another runtime policy
owner; refusal cases must not count as delivery of the requested composition.

At the inspection baseline, the complete consumer design was not yet
qualified. `pyproject.toml` and `uv.lock` selected RAES 9.1.0. The existing
[architecture assessment](participant-tool-admission.md) reports that the
released invocation tool port refuses participant-crossing policy,
resource-governed v3 policy, and shared-time-bound tool actions. This matters
locally: `raes.py` installs `participant_runtime_options()` from
`_raes_participant_crossing.py` for authored participant deliveries. The
autonomous manifest also installs shared-time support. An outer action's time
support does not establish time support for its individual tools.

Do not disable crossing/control policy or change time semantics to make the
tool path run. A supported autonomous subset cannot silently become the
scope of all red/blue participation. Required profile combinations and the
manual participant lifecycle need resolution before selecting the bridge.
An upstream contract gap stays an explicit refusal, not local policy emulation.

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

The common tool dispatch boundary is the shared integration seam for both
roles. Enforcement also depends on the launcher's trust boundary and all
supported ingress paths. The management side supplies a narrow connection to
the existing RAES runtime owner. It must not expose a runtime manager, deployment client,
arbitrary backend method, or evaluator store to the participant. Guest relay
authorization remains an additional gate. Any process boundary needed to
reach the runtime must be private, authenticated, bounded, and tied to its
owning invocation; no general operator API or externally published listener
is justified by this issue.

Private files, minimal environments, and process-group supervision do not
isolate code running as the same OS user. Keep admission authority outside
participant-controlled code and state the launcher's trust assumptions. Reuse
the qualified guest/seat boundary for containment claims; a new private socket
alone cannot establish them. Proposed ADR-057 is not evidence of installed
isolation, and this issue does not implement a new sandbox.

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

Tool names alone do not identify semantic actions: `kali_run_command`, raw
session writes, and generic API calls can perform different work with different
arguments. The trusted binding must account for exact arguments, session
ownership, effective query/template configuration, method and resolved target.
Bind that configuration before dispatch; a changed request, target, controller,
or policy requires the applicable fresh RAES admission. Do not parse arbitrary
shell text into a fictitious finite action model. Where only broad shell
authority is enforceable, declare that limitation and its containment boundary.

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
Reuse the published request identity/commitment rules. Do not invent a second
canonicalizer or publish secret argument fingerprints as correlation IDs.

The earlier qualification reports RAES 10.1.0's
`participant-invocation-tool-actions/v1` as a candidate for scheduled autonomous
invocations. Within a qualified combination, use its scheduler-issued port
for admission, dispatch, and completion. Do not use recursive `manager.apply()`
or direct nested `admit_action()` calls. The architecture assessment leaves
the broader consumer boundary open; it is not an accepted universal bridge.

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
RAES #1740 subsequently merged and shipped in RAES 10.1.0.
Consumer qualification on 2026-10-31 used the published wheel and the real scheduler.
The original concurrent red/blue baseline passed.
A separate probe admitted and dispatched a distinct tool action for each participant.
Blue completed first, and both participants retained their tool and outer history triples.
The probe caused no model requests or native lab effects.
It required an exact execution offer and explicit tool feature claims.
Duplicate outer execution offers cannot substitute for an unambiguous tool offer.
These reported results address the isolated tool/outer-history settlement gap.
They do not qualify crossing policy, controller handoff, shared-time tools,
manual sessions, native effects, or crash recovery. At that baseline, no retained test
exercised the invocation tool port. Dependency selection must
qualify the required combination and retain its consumer tests; a version
bump or a temporary probe alone is insufficient.
All repository changes remain in the invocation checkout.

## Cross-cutting layers the design must pass

| Layer and canonical incumbent | Required behavior |
| --- | --- |
| Scenario, implementation, and configuration admission: `ParticipantPlanAuthority`, `LilraeParticipantBinding`, `_raes_participant_manifest.py`, `raes_manifest.py`, RAES contracts | Use the compiled action/target relation, installed manifest and selection, and active episode/generation. Preserve manifest capability checks and configuration digests; advertise only qualified tool behavior. |
| Harness configuration: `workbench/agent.py`, `codex_agent.py`, `_raes_participant_transport.py`, `lilrae_opencode.py`, `profiles.py` | Preserve private-file ownership, no-follow reads, unchanged-config digests, exact inventory, credential aliases, allowed environment sets, and default-deny tools. Internal generated entries require exactly `{command,args,env}`; external client serializers have their own shapes. Do not smuggle context in unknown fields. |
| Durable config and environment: `core/config.py`, `core/env.py`, MCP `config.ts`, `workbench/guest_binding.py` | Retain strict first-party models and typed binding validation. Extend the canonical model/renderer/consumer together only if needed. Keep `APTL_HP_*` values decimal ports; do not use that channel for tokens, paths, or JSON. Preserve `APTL_MCP_DISABLE_DOTENV=1` on restricted guest launches. New identifiers follow ADR-062; existing interfaces retain their names. |
| External auth and transport: `workbench/access.py`, `GuestAdmission`, `DispatchSelector`, `ProtocolAdmission`, `browser_mcp.py`, `access_clients.py` | Retain grants, role/server restrictions, instance/generation and native identity checks, revocation, exact inventory, SSH key pins/forced commands and disabled forwarding, browser session and Origin checks. Preserve operator `api/deps.py`, `api/middleware/bff.py` and `api/session.py` Host/session/CSRF gates if traversed; do not reuse an operator token as participant authority. |
| Tool validation and native effects: MCP `server.ts`, generated definitions/handlers, `endpoint-url.ts`, `http.ts`, `ssh-manager.ts`, `ssh-session.ts` | Keep Ajv closed arguments and predefined-query parameter/path checks, configured-origin HTTP restriction, current TLS/CA policy, SSH host-key verification, session ownership, command limits and teardown. Admission does not bypass these. Use existing handlers; add no parallel SSH, HTTP, or shell runner. |
| OS and secret exposure: `workbench/process.py`, `credentials.py`, `utils/pathsafe.py`, `utils/curl_safe.py`, ADR-029 | Use admitted executable/argv arrays, explicit minimal environments, private no-follow files, credential leases and process-group supervision. No credentials or secret-bearing payloads in argv, URLs, logs or exception text. No ambient provider credentials, participant daemon sockets, or evaluator mounts. Private runtime access must not become a reusable peer/control-plane credential. |
| Errors and results: RAES `Diagnostic`, `ParticipantActionApplyResult`, `ParticipantActionResultModel`, operation receipts/status, `WorkbenchConfigurationError`, `AgentExecutionError`, `BoundedProcessError` | Preserve typed refusals and native outcomes. Map JSON-RPC errors, MCP `isError`, handler payload `success:false`, exit status, timeout and unknown cleanup deliberately. A resolved Promise or `ApplyResult.success` does not prove tool success. Retain bounded safe client errors, including relay error masking; never return raw validators, provider output, stacks or secrets. Add no exception hierarchy. |
| Evidence and observability: `core/runstore.py`, `raes_participant_evidence_publication.py`, `utils/logging.py`, Python/TS `redact`, `workbench/mcp_results.py`, MCP `telemetry.ts` and `runs.ts` | RAES owns accepted operational history; use the existing run store and evidence owner for admitted retained projections. Retain atomic source records and recoverable projections where applicable. Correlate operation/action, participant/episode, invocation/generation and admitted run/attempt. Trace IDs correlate; they do not authorize or select another run. Redact before storage, logs, traces and client serialization. Preserve typed terminal handles and tool schemas. No `_unbound` fallback for governed participant history. |
| Visibility and finalization: participant projection/exposure modules, `core/correlation/`, `core/evidence/`, ADRs 033 and 050 | Keep participant observations separate from evaluator evidence. Blue sees its permitted tool results and sensors, not red history injected into its SIEM. Drain calls and publication before the existing terminal seal; no late writes to sealed runs, second archive, evaluator, or finalization controller. |

The config path includes `.mcp.json.example`, `core/lab.py`'s
`_sync_mcp_config_keys()` / `_sync_native_mcp_ingress()`,
`core/mcp_ingress.py`, `render_profile_config()`, `_render_profile_server()`,
and `GuestAdmission._service_environment()`. Each selected adapter must carry
the admitted binding through its existing serializer and allowlists. A field
accepted by one launcher can be rejected or dropped by another. MCP
`LabConfig` is a TypeScript interface with partial loader checks, not a strict
runtime schema; it cannot attest participant authority. In particular, keep
decimal host ports separate from the validated native IP and capture-container
channels. Do not edit generated secret-bearing `.mcp.json` as a source artifact.

The host/runtime boundary also includes `DeploymentBackend` ownership receipts,
native-container readback, `appliance_boundary.py`, and
`deployment/boundary_compiler.py`. A management-side MCP's admitted Docker
endpoint is not authority to hand that endpoint to the participant. Preserve
the Kali capture broker ingress and workspace-scoped sidecar. Route any
management inspection through the existing backend; existing SSH/API tool
effects stay with their MCP handlers, not a second `container_exec()` runner.

## Failure, extensibility, and evidence boundaries

Direct harness calls do not inherit the guest relay's result redaction and
error masking. The common handler's `errorMessage()` only extracts a message;
it does not sanitize it. Admission and completion errors need bounded,
redacted serialization on every path, including stderr and hook failures.
Existing API handlers already use a bounded redacted error formatter; reuse
the shared redaction policy. Validator property names, paths, unknown tool
names and exception metadata are also untrusted text. Avoid echoing them
unbounded even when rejected values are omitted. Redact data without damaging
`tools/list` schemas or the typed caller-local terminal handles.
Those live handles are not an exception to retained-evidence redaction; use
the existing retained transcript projection when that capture is requested.

Operational history is required for admitted actions. Experimental capture,
retention and export remain separately selected through the admitted
`PlannedTrial` capture pins, capture registry, evidence coordinator and archive
owner. Tool admission does not authorize retaining every prompt, response or
transcript, adding a capture source, or enabling export. Keep mandatory
operational outcomes available even when optional research capture is absent.

Admission is mandatory for governed participant calls. Runtime unavailability
or loss of authority fails closed before dispatch. After dispatch, cancellation,
timeout, disconnect or an unavailable completion channel can leave effects
unknown. Preserve that distinction through RAES; do not retry effects to
repair missing evidence. Recording an accepted result and publishing its
archive projection are separate concerns. Publication failure must remain
visible without erasing accepted history or replaying execution. OCSF and OTel
remain best effort and cannot substitute for required RAES recording.

Replay protection must cover concurrent duplicates and reconnects within its
declared lifetime. An in-memory cache or JSON-RPC ID does not establish replay
safety across a runtime restart. Native effects and history publication are
not one atomic transaction: after an uncertain dispatch, use the existing
operation receipt/status and recovery contracts, or refuse further execution
while the outcome is unknown. Do not promise exactly once effects across
crashes or add a second action ledger to simulate that guarantee.

The experimental capture redaction opt-out must not reach admission history,
client results, diagnostics, or OTel. Reuse the always-redacting shared helpers
at those boundaries; do not copy the red capture sink's opt-out behavior into
the required history path.

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
identity, controller/invocation context where applicable, server/tool identity,
action contract, boundary, effective arguments/configuration and allowed targets,
delivered through each existing harness/config adapter. These are coordinates
in existing contracts, not a proposed new universal request DTO or mandatory
SDL tool inventory. Resolve unspecified installation detail in backend admission;
retain any explicit author constraints. The seam must accommodate a
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
cancellation cleanup, uncertain dispatch/reconnect behavior, and credential
canaries absent from every projection even with the capture opt-out enabled.
The autonomous and manual participation boundary is not decided.
Manual guest/browser sessions lack an outer RAES invocation.
Their grants do not establish RAES participant authority.
System-wide research and review must determine the required control and lifecycle composition.
Exercise each supported ingress path selected by that decision.
A session-level history event or hook mock alone cannot qualify tool admission.
Include two participants of the same role, argument-dependent targets, and
tools with crossing/control policy actually installed. Existing control tests
such as `tests/test_raes_participant_delivery.py` and shared-time concurrency
tests are complementary, not evidence that those features compose with tools.
#1418's extension of DSL-010 needs a bounded real red/blue action proof against realized
infrastructure, with operation status, settled snapshot and realization
provenance through the existing live-proof/qualification owners. Transport
tests and model-free scheduler fixtures cannot establish that live claim.

Local checks remain change-scoped under `.ground-control.yaml`: explicit paths
through `tools/run-targeted-tests.sh` and staged `pre-commit run`. Common MCP
changes select their consumers; CI rebuilds/tests all dependents. Lifecycle or
config changes also need the repository's installed-lab qualification. Full
suites, coverage, and whole-tree prose checks stay in CI. Reuse
`mcp/build-all-mcps.sh`, `utils/mcp_packaging.py`, `tools/ci/select_checks.py`
and `.github/workflows/checks.yml`; copied `file:` dependencies must be rebuilt
before consumer qualification. Keep `.gc/pack-ownership.json` and
`tools/check_pack_boundary.py` authoritative for pack-owned facts. New names
use LilRAE, and new CLI callers use `lilrae`, per ADR-062. One issue retains
one delivery PR linked to the supplied DSL-010 UID. This documentation pass
does not transition the requirement or claim implementation evidence.

## Non-goals

This issue does not replace RAES scheduling, add a participant policy engine,
reclassify OCSF events as RAES events, or promise every OS/network effect is a
tool call. It does not add model/prompt configuration, a harness, provider,
service, public endpoint, capture format, or run archive. It does not redesign
scenario composition, grant broader tools, weaken isolation, or make cleanup
equivalent to rollback. It must not claim closure of neighboring configuration,
study assembly, or pack-authoring work from tool-call admission alone.
It does not rename historical ACES contracts into local compatibility schemas,
invent an autonomous wrapper for human participants, or make each MCP process
or tool a separate participant. No universal gateway, new sandbox, mandatory
experimental collection, or external processing service is selected here.
