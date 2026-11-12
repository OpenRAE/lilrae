# Issue #1504: Managed OpenCode participant preflight

This historical Reference preserves the original source record.
The record below describes its own evidence date and revision, where stated.
It does not establish current behavior, implementation completion, or installed qualification.
The preserved file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/architecture/issue-1504-managed-opencode-preflight.md).
Its last recorded file change before this rewrite was `22e5638ecd79`.
Current interfaces and successor decisions take precedence for present use.


Status: architecture guidance before implementation; no installed OpenCode
release or live qualification is asserted here. The supplied issue is the
delivery contract. This note records boundaries, not an implementation plan.

The operator clarified the delivery boundary after this preflight.
Issue #1504 ends at PR merge after candidate testing and review.
The approved live check is a bounded, free-model trigger/connectivity smoke on the issue-owned GCP VM.
Release publication and full scientific control qualification are downstream work.
Code observations below refer to the checked-in baseline `5b076560`.

## Decision and current gaps

Extend the existing OpenCode executor and shared participant runtime. Do not
add another provider framework, scheduler, MCP gateway, credential broker, or
evidence store. ADR-025, ADR-029, ADR-033, ADR-044, ADR-050, ADR-052,
ADR-057, ADR-064, and ADR-070 already assign the relevant responsibilities;
no new ADR is necessary. The [action enforcement design](participant-action-enforcement.md)
and its executable component/action models remain the integration boundary.

The checkout already contains `LilraeOpenCodeExecutor` and `OpenCodeOptions`
in `src/aptl/workbench/lilrae_opencode.py`, plus `opencode_manifest()`,
`OpenCodeConfigurationValidator`, and `configured_opencode_executor()` in
`src/aptl/backends/lilrae_participant_configuration.py`. They provide fresh
private contexts, explicit model/prompt delivery, configuration commitments,
bounded process execution, verified MCP inventory, and invocation-scoped tool
sessions. Reuse them rather than treating #1504 as a new integration.

They do not yet establish the issue's installed-product contract:

- `OpenCodeOptions` has no explicit gateway endpoint or serving-route input.
  Its environment allowlist accepts several providers' keys, while the model
  syntax permits any provider prefix. Neither selects the approved route.
- `opencode_manifest(version=...)` accepts a caller-supplied version; that is
  not verification of the installed executable or its dependency/build identity.
- `_terminal_text()` reduces JSON events to text. It does not preserve the
  request/response metadata #1421 needs or prove a complete successful request
  merely because text arrived.
- Existing OpenCode tests use recording runners and a synthetic executable.
  They prove useful handoff behavior, not compatibility with a pinned OpenCode
  build, its real provider transport, or an installed release.
- `InstalledParticipantModels`, `InstalledParticipantCredentialSources`, their
  accessors, and `safe_config_projection()` currently enumerate Claude/Codex.
  A new launch path must pass its actual ingress and provenance gates; adding
  an adapter alone cannot make those paths accept or record OpenCode.

Historical #557/#862 guidance names a removed participant-readiness command
and provider builder. Do not restore that workflow as the installed entry
point. Use current entry assembly, admitted trial configuration, and the
shared runtime; keep existing Claude/Codex behavior compatible.

## Identity, configuration, and extensibility

Keep these values separate: SDL participant address; installed adapter
manifest identity/digest; verified OpenCode version/build; requested model id;
gateway and approved base URL; requested serving provider/endpoint; and the
route actually reported by the response. A workbench role/profile selects
capabilities, not any of these identities. A successful process exit does not
establish the served model or scenario success.

Resolve selection independently for each participant address. Both autonomous
roles must reach `LilraeParticipantBinding`, `LilraeParticipantExecution`, and
`AptlParticipantRuntime`/RAES `BaseParticipantRuntime`. A global provider/model
setting, a hard-coded red/blue pairing, or a consumer-specific scenario switch
cannot be the only selector. Identical roles can still name different
participants. Assembly belongs at Entry; shared values/protocols belong in
Core and provider mechanics in the agent adapter, under ADR-064. Do not extend
the incumbent backend-to-workbench imports into a new adapter dependency cycle
or import backend implementation code into the executor.

`ManagedAgentAdapter`, `AgentLaunch`, and `ManagedAgentSelectionProvider`
already cover managed bounded-choice solicitation. If that mode is exposed,
reuse `admit_decision_response_schema()`, exact candidate membership, and
`ParticipantProviderFailure`; do not equate it with the autonomous tool
executor or route autonomous execution through a fake bounded choice.

The extensibility seam is the existing provider-owned configuration registry
and validated launch handoff: participant selection, admitted route/model,
bounded request controls, committed context artifact, process/credential
inputs, and a safe result projection. Reuse RAES
`ParticipantConfigurationModel`/`ParticipantConfigurationResultModel`,
`realize_participant_configuration()`, `canonical_contract_digest()`, and
`validate_participant_configuration_selection()`. The executor's effective
configuration must equal the admitted trial result, as checked by
`run_participant_workload()`; manifest identity and configuration identity
remain distinct. Change registry/validator versions and canonical manifest
comparison together when their supported targets change.

Keep `supported_models` operator-supplied. Experiment model catalogs, prompts,
fixed inputs, and condition matrices belong in the experiment repository.
#1419 can add typed request-control targets and #1420 can deliver pinned
control-context artifacts through this same registry. Unsupported controls
must be refused explicitly, not silently discarded or replaced by defaults.
Do not add an untyped provider-options, argv, headers, environment, or plugin
dictionary. Exact context means the effective request, including harness
instructions, tool schemas, auxiliary calls, and compaction behavior; an exact
stdin prompt digest alone proves only the authored bytes delivered to stdin.

Use the supported integration facilities of one pinned OpenCode release.
The official [configuration](https://opencode.ai/docs/config/) and
[CLI](https://opencode.ai/docs/cli/) references describe merged configuration,
provider allowlists, and isolation switches. A custom config path alone does
not establish isolation. Verify every relied-on option against the chosen
release and exercise it; current web documentation does not prove an older
binary implements the switch. Do not fork OpenCode, monkey-patch its client,
or add an intercepting service to make missing controls appear supported.

## Cross-cutting security passage

Each row is an independent gate. Passing an inner adapter check does not
replace its ingress, native, or persistence checks.

| Layer and canonical incumbent | Required passage for OpenCode |
| --- | --- |
| Operator ingress: `core/config.py`, CLI `resolve_config_for_cli()`/`load_config()`, `api/routers/config.py`, API BFF middleware, workbench authorizer | Selection is management-owned. Preserve authenticated API/workbench boundaries and secret-free response DTOs; no participant-supplied executable, route, credential locator, or authority coordinates. No new public listener is needed. If installed settings are extended, update their closed accessors, validators, examples, and allowlisted provenance projection together. |
| First-party and experiment shapes: ADR-025, `ExperimentSettings`, `core/experiment/bindings.py`, RAES registry | Keep strict scalars and unknown-field rejection. Binding literals pass `_validate_literal_safety()`, `is_sensitive_key()`, and `is_secret_shaped_value()` before owner validation. Paths, executable locators, secret-shaped values, and shell expressions cannot be smuggled through controls/context references. Reuse these gates; do not weaken them to admit a provider payload. Validate finite numeric ranges and reject bool-as-int/non-finite values. |
| Route boundary: `OpenCodeConfigurationValidator`, executor validation, provider-native renderer | Require the explicit OpenRouter route, full model identity, approved endpoint, and applicable serving-provider selection. Validate URL structure and approved destination, without userinfo, secret query strings, interpolation, or redirect to an unapproved host. Keep transport-security verification enabled. No arbitrary base URL, proxy environment, alias/default route, alternate provider, or retry route supplied by the participant. |
| Credential acquisition: `ProcessEnvironmentCredentialSource`, `ProcessEnvironmentCredentialResolver`, `CredentialBindingEvidence`, workbench credential broker | Resolve only the configured reference; map only the selected provider's required credential through the shared owner. Preserve placeholder/NUL/size checks and acquisition/cleanup evidence, including turn-zero failure. No ambient `.env`, saved login, keychain, SDK chain, auth file, or unrelated provider key. Static possession and local cleanup are not a lease, expiry, or upstream revocation (ADR-052). |
| Provider and MCP environment shapes: `OpenCodeOptions`, `_validate_provider_environment()`, `profiles.render_profile_config()`, `_load_server_config()`, `_server_environment()` | Keep the internal MCP entry exactly `{command,args,env}`. Translate only after admission to OpenCode's external shape. Model credentials, MCP service credentials, and invocation tokens are different grants. Preserve minimal per-consumer environments, literal-versus-alias rules, `APTL_MCP_DISABLE_DOTENV=1`, and config digests. If reusing host-delivery rendering, preserve `_render_profile_server()`'s per-server `_MCP_RUNTIME_ENVIRONMENT` gate in `_raes_participant_transport.py`; invocation credentials are management-injected after source admission, not arbitrary source fields. Verify real MCP child inheritance: an explicit environment map need not mean replacement of the OpenCode parent's environment. No arbitrary environment expansion or model key forwarded to a range shell. |
| OS launch and files: `_admitted_executable()`, `_prepare_work_dir()`, `_read_private_config()`, `utils/pathsafe.py`, `BoundedProcessRunner` | Verify the pinned executable/build before use; ownership/mode checks alone do not pin bytes. Use fixed argv arrays, no shell, prompt on stdin, private no-follow/create-once files, and finite input/output/deadline bounds. No credential in argv, URLs, prompts, filenames, version probes, or errors. Treat secret-bearing generated config as temporary private state and remove it on every outcome. |
| Ambient OpenCode state and outbound traffic: executor private HOME/XDG/cwd, approved containment profile | Use a fresh context per trial/invocation with no resume/attach, global/project/managed configuration, history, instructions, skills, plugins, auto-update, or runtime dependency/catalog downloads. Exercise ancestor discovery and system-wide settings as well as user homes. Disable auxiliary model/default/fallback routes or bind their behavior explicitly to the admitted request contract. Sharing, snapshots, LSP/formatter helpers, subagents, built-in shell/file/network tools, and telemetry must not create another action or outbound channel. |
| Tool inventory and auth: `profiles.verify_profile_tool_inventory()`, core `ToolSession`, `LilraeToolSession`/`LilraeToolTransport`, common `lilrae-tool-admission.ts` | An exact installed inventory is necessary but not action authority. Bind each tool to the runtime-issued invocation port, participant, generation, action/argument/configuration commitments, targets, and boundary. Preserve default-deny built-ins, fresh per-server tokens, and exact inventory. Node validates socket path/length, token shape, and finite timeout; private filesystem/socket placement must work inside the selected compartment. A missing token must not turn a managed participant into the ordinary unbound operator path. |
| Native admission: common MCP `server.ts`, RAES invocation-tool port and accepted histories | Preserve strict Ajv argument validation before handlers, one-use dispatch, outcome receipt, result bounds, cancellation, and `redact_mcp_result()`. Use the existing detached effective configuration and native SSH/API handlers. No direct host shell, Docker/orchestration API, invented tool-name authority, telemetry-based admission, or replay after uncertain effects. Scenario-admitted range shell actions remain governed MCP actions, not host shell access. |
| Provider parsing and errors: `utils/strict_json.py`, `core/agent_errors.py`, `BoundedProcessError`, RAES `Diagnostic`/`ApplyResult`/`ParticipantActionResultModel` | Parse bounded provider events as untrusted structured input; reject ambiguous/malformed JSON, invalid terminal sequences, and error-after-text. Reuse strict decoding and typed boundary models; do not copy a JSON parser or exception hierarchy. Preserve cleanup proof and distinguish failed native work from failed admission and unknown effects. No raw provider bodies, stderr, validation inputs, exception chains, or stack traces in public envelopes. |
| Persistence and observability: `RunStorageBackend`/`LocalRunStore`, `utils/redaction.py`, common `redaction.ts`, `get_logger()`, existing OTel hooks | Write allowlisted safe facts before raw material can be logged or persisted. JSON/JSONL storage applies shared redaction; blob/file writes are not automatically safe. Logger acquisition alone does not redact messages. Keep Python/TypeScript redaction parity and the control-plane redaction invariant even with experiment capture opt-out. Never persist tokens, environment maps, auth files, raw generated config, or uncontrolled provider events. |

OpenCode's [OpenRouter integration](https://opencode.ai/docs/providers/#openrouter)
has native provider routing options. OpenRouter's
[routing contract](https://openrouter.ai/docs/guides/routing/provider-selection)
distinguishes provider preference order, an allowed-provider set, fallback,
and support for requested parameters. An order preference alone is not an
exclusive route. The adapter must encode the consumer's admitted restriction
and disable fallback using facilities supported by the pinned build. Requested
and observed route stay separate; missing upstream attestation is recorded as
unavailable, never inferred from the config. The approved smoke records the
requested route, available provider metadata, and its verification limits.

## Lifecycle, evidence, and containment limits

`LilraeParticipantExecution` owns native reservations/cancellation and
`run_participant_workload()` owns cancel-and-drain before returning to the
experiment owner. RAES owns scheduling, lifecycle, admission, and committed
history. Preserve peer history when one participant fails. An invocation's
failure stops its work; stopping a whole trial follows existing trial policy,
not a provider-specific scheduler. No automatic retry of native effects.

`BoundedProcessRunner` and `_pipe_exchange.py` already supervise input/output,
deadline, cancellation, and process-group teardown. Reuse `ProcessCleanup`
and `BoundedProcessError.record()` facts. Current process supervision cannot
prove cessation of detached descendants or remote effects. Preserve the
existing unknown-outcome diagnostic when trustworthy terminal cleanup is
missing; do not translate uncertain work into a clean failed action.

Private homes, denied tools, IPC tokens, and process groups are not OS
containment. Consume the shared supported containment and credential profile
owned by #1454–#1464; do not select or implement another sandbox here.
Verify its executable, MCP descendants, filesystem/mount, socket, PID/user,
resource, and egress guarantees for this build. Missing required guarantees
must refuse supported launch, without an unsandboxed fallback. The appliance
management zone is not by itself proof that the agent cannot reach host
orchestration, evaluator data, or credentials. Record actual platform/profile
limitations rather than claiming confinement of a same-user developer run.

Retain bounded safe partial evidence for launch, request, parsing, timeout,
cancellation, provider, persistence, and teardown failures. A temp directory's
deletion must not erase the only record. Counts/cleanup summaries are useful
but are not a retained partial response. Extend existing evidence builders
with typed allowlisted metadata at the provider boundary before reducing
events to text. Keep participant/trial/attempt/action/request joins, verified
build identity, configuration/context commitments, requested and reported
model/route, available usage/finish/status facts, and cleanup/uncertainty.
Missing facts remain explicitly unavailable. No raw prompt, reasoning, or
completion capture is authorized by this requirement; ADR-033 and the
experiment's capture contracts still govern it.

Reuse `raes_participant_control_evidence.py` where the invocation is a bounded
selection, and the existing autonomous runtime/evidence owners for autonomous
execution; do not fabricate selection records for a different execution mode.
Reuse provenance's `safe_config_projection()` and canonical identity/digest
owners. Version published records with their consumers if meanings change.
#1421 owns downstream evidence interpretation, not a new provider log store.
`ExperimentExecutor`, `TrialOutcome`, and `finalize_terminal_attempt()` remain
the trial result, capture, and archival owners. A persistence/cleanup failure
cannot produce a successful qualification. Fresh executors, sessions, config,
credentials, ports, and cancellation state prevent the next trial inheriting
the previous one's state.

## Repository and delivery guardrails

The whole-repository surface includes the config/CLI/API gates, experiment
bindings and trial planning, workbench launch/profiles/credential/process
modules, participant binding/runtime/tools/evidence adapters, common MCP
dispatch and native clients, run store/provenance/capture/archive, and their
tests. Also include these canonical packaging and policy owners:

- `pyproject.toml`, `uv.lock`, `requirements/`, `hatch_build.py`, and
  `src/aptl/_asset_manifest.py`: installed dependency and asset delivery.
  Reuse the lock/integrity mechanism appropriate to the chosen upstream
  distribution. Do not download or update executables during a trial. If
  appliance delivery is claimed, its offline payload, guest provisioning,
  golden-image checks, signing, and release verification must carry the same
  pin; `appliance/guest/claude/` is an incumbent packaging pattern, not a reason
  to assume OpenCode has the same runtime layout.
- ADR-064's layer map in `pyproject.toml`, `tools/check_architecture.py`,
  `tools/check_lilrae_participant_architecture.py`, and the participant action
  model: preserve dependency direction and existing effect invariants. Reuse
  public shared helpers; do not multiply private cross-package imports.
- `.gc/pack-ownership.json` and `tools/check_pack_boundary.py`: no consumer
  model catalog, prompt, or RPT experiment logic in core or a TechVault branch.
- `.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`,
  `tools/run-targeted-tests.sh`, `tools/ci/select_checks.py`, and
  `.github/workflows/checks.yml`: targeted local checks and staged hygiene;
  CI owns full suites and installed-lab qualification. Shared MCP changes
  select all consumers, including rebuilding copied `file:` dependencies.
- `docs/releasing.md`, Release Please, and the candidate manual QA gate:
  publish installation/invocation instructions and the supported LilRAE,
  RAES, OpenCode, build/platform, and containment identity with evidence.
  Do not hand-edit the LilRAE version or changelog. Native GitHub blocked-by
  relations remain authoritative; this preflight does not clear dependencies.

Reuse the config/credential/adapter tests and
`test_lilrae_opencode.py`, `test_lilrae_participant_configuration.py`,
`test_lilrae_participant_workload.py`, concurrent/cancellation tests, tool
transport/composition tests, and `test_lilrae_mcp_runtime_integration.py`.
Use the installed-wheel test conventions in
`test_pack_adapter_install_artifact.py` and the clean-install CI lane: run
outside the checkout without source imports, with the real pinned OpenCode
launcher and MCP transport. A synthetic CLI alone is insufficient. Approved
local fake-provider cases must observe emitted requests and safe failure
evidence for auth/route refusal, unsupported controls, malformed/partial
events, overflow, blocked input, timeout/cancel, descendant cleanup, peer
failure, and a subsequent clean trial. Negative mutations must demonstrate
that removing route/config/tool/cleanup enforcement is detected, reusing the
existing action-model approach rather than adding another model.

Qualification must exercise hostile ambient config/history/plugin/login
canaries and denied built-in tools through the real build. Candidate tests
must prove both roles use the shared runtime. The approved GCP smoke proves
bounded provider invocation with the declared build and requested free route.
Use only operator-approved environment,
destinations, data, and credential references. Availability of a tool or a
public provider does not authorize a transfer. No live run or external
processing is part of this preflight.

## Non-goals and anti-patterns

No experiment authoring, model catalog, prompt content, crossed experiment,
new service, universal provider gateway, raw HTTP replacement for OpenCode,
new credential source, containment redesign, RAES schema mirror, duplicate
validation/error hierarchy, transcript store, or trial workflow belongs here.
Do not equate gateway with serving provider, model with implementation,
profile with participant identity, inventory with admission, text with
completion, cleanup with revocation/rollback, or process success with a
qualified experiment. #1419/#1420 consume the request/context seam; #1421
consumes safe metadata; process and credential protection keep their existing
owners. Installation instructions and candidate verification remain #1504 obligations.
Design notes alone establish no runtime qualification.
