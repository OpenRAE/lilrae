# Issue #1420: Complete per-trial participant configuration preflight

This historical Reference preserves the original source record.
The record below describes its own evidence date and revision, where stated.
It does not establish current behavior, implementation completion, or installed qualification.
The preserved file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/architecture/issue-1420-trial-participant-configuration-preflight.md).
Its last recorded file change before this rewrite was `fc493be0118b`.
Current interfaces and successor decisions take precedence for present use.


Status: architecture guidance before implementation, inspected at `ece3505c`.

The user later approved one repository-owned local observer plugin.
That narrow exception supersedes the plugin prohibition below; see [the final design](trial-participant-configuration.md#approved-local-request-observer).
The supplied issue is the delivery contract. This note defines boundaries and
verification obligations; it is not an implementation plan or qualification.

## Decision and existing coverage

Compose the existing sealed trial, request owner, managed provider and runtime
contracts. Add no configuration framework, scheduler, credential broker,
exception hierarchy or evidence store. ADR-025, ADR-029, ADR-033, ADR-044,
ADR-047, ADR-050, ADR-052 and ADR-064 already assign these responsibilities.
The [request manifest design](participant-request-manifests.md),
[managed OpenCode design](managed-opencode.md) and
[participant action boundary](participant-action-enforcement.md) remain binding.

The current repository already provides:

- `backends/scenario_family.py:admit_family_trial()` and
  `AdmittedFamilyTrial.participant_configuration_results`: detached sealed-entry
  configurations joined to the instantiated snapshot and trial provenance.
- `core/participant_requests`: closed `RequestCatalog`/`RequestProfile`,
  `ParticipantRequestOwner.for_scenario()`, `prepare_request()`, immutable
  `ParticipantRequest` and independent `ParticipantRequestBinding`. These own
  complete target validation, model/profile compatibility, asset pins, bounded
  UTF-8 content verification, exact ordering and trusted dispatch coordinates.
- `workbench/opencode_bootstrap.py:managed_opencode_executor()`,
  `configured_opencode_executor()`, `OpenCodeOptions` and
  `workbench/participant_request.py`: configured credential acquisition and the
  sealed-request handoff to the incumbent native executor.
- `LilraeParticipantBinding`, `LilraeParticipantExecution` and
  `run_participant_workload()`: selection/configuration joins, installed tool
  authority, native cancellation/drain and equality with the planned trial.
- Real pinned-launcher transport tests and installed-package qualification for
  request controls, both roles, hostile ambient state and failure cleanup.
  See the [#1419 evidence](../testing/participant-request-1419-qualification.md)
  and [#1504 evidence](../testing/opencode-1504-qualification.md).

Those parts do not establish automatic application at every trial start.
Important gaps must remain visible:

- The bounded-choice path imports fixed proposal/action limits and a 600-second
  episode limit from `raes_participant_driver.py`. The autonomous invocation
  path is different; changing those constants alone cannot apply trial controls.
- `RequestProfile` currently allows only `stdin-prefix` placement, unsupported
  seeds and no fallback. Each catalog's profiles must order the same complete
  slot set. A seed request, another placement or a different slot arrangement
  cannot be silently accepted under this contract.
- `OpenCodeInvocationEvidence` retains safe invocation summaries, not the
  actual outgoing request configuration. Its served identity fields are not
  populated by `opencode_events.py`; generation identity is not retained.
  Usage is aggregated across step finishes. It cannot prove per-request joins.
- Prompt checksum verification does not detect unresolved template variables
  or prove instruction roles in the provider's effective context.

## Invariants and concept boundaries

The selected sealed entry is authoritative for participant configuration and
execution controls. Preserve plan, entry, run, attempt and instantiated snapshot
identities; use full participant addresses as keys. Reject duplicates, missing
participants, peer substitutions and conflicting bindings before affected
requests. Role labels, list position, model aliases and condition names are not
identities. Project `participant_models` settings cannot override a sealed
trial selection or supply a missing value.

Trusted entry composition supplies each trial's owner bound to its instantiated
scenario, approved content resolver, request binding and managed executor.
Keep the complete request profile path; do not project it back into the older
model/prompt/timeout-only OpenCode target set. The configuration digest remains
a commitment, not execution evidence or tool authority. RAES models and
`canonical_contract_digest()` remain the portable schema and identity owners.
Do not copy their models or validation into local DTOs. Boundary revalidation
against a trusted owner is necessary; a second independent ruleset is not.

Separate execution bounds from generation controls. Trial turns, proposals,
native action attempts, provider HTTP retries and model tokens count different
events. Map the trial's declared turn/time semantics through the public RAES
execution controls and existing lifecycle policy. A process timeout, tool
timeout and whole-attempt timeout are different scopes. Respect the remaining
attempt deadline without restarting its budget per invocation; retain the
declared clock semantics separately from monotonic process supervision.
Installed resource ceilings are admission limits: refuse an unsupported trial
bound instead of silently clamping it to 600 seconds, 3600 seconds or another
local default. Do not count native provider retries as participant turns or
advertise new RAES lifecycle capabilities to implement a local timeout.

Content resolution returns approved bounded bytes; a descriptor URI grants no
permission to fetch, read a host path or disclose content. Preserve exact
versions, checksums, size, participant scope, slot order and instruction
placement. Keep preamble-only and preamble-plus-selected-playbook treatments
explicit in the admitted asset/profile contract. The current same-slot-set
rule must be accounted for; do not bypass it with an omitted slot, stale
playbook or an implicit empty-string default. Exact composition adds no newline,
template expansion or hidden wrapper. Reject unresolved authored placeholders
before dispatch using the producer's declared template vocabulary; do not add
a general template engine or treat every brace in a prompt as a placeholder.
`utils/placeholders.py` remains the credential-placeholder owner, not a prompt
template parser. Verify public provider message roles, placement and ordering;
an stdin prefix is not evidence of a system instruction.
Authored assets are only part of the effective context. Keep native harness
instructions, tool schemas, continuations, auxiliary calls and compaction
behavior explicit and separate from the selected asset commitment. Do not
claim complete context equivalence from matching authored bytes.

Each supported control must reach the pinned provider transport unchanged, or
have its declared omission preserved. Null/unsupported/provider-managed are
different dispositions. Zero, omission and provider defaults are not equivalent.
Reasoning effort and budget differ; combined-generation and output limits
differ. Preserve the existing coupled budget validation. Unsupported seed
requests fail before dispatch; an unsupported disposition does not promise a
seed or determinism. Provider refusal never permits stripping a parameter,
switching route/model or falling back to ambient state. Required omission must
also exclude harness-injected values. New support needs owner validation and
native transport evidence together, with versioned profile/manifest commitments.

## Cross-cutting passage

Paths in this table are relative to `src/aptl` unless otherwise stated.
Every row is a separate obligation, including layers outside the edited file.

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Authority and ingress: `core/config.py`, CLI config resolution, `api/deps.py:verify_token`, BFF/workbench authorization | Trusted management assembly supplies executable, route approval, credentials and artifact authority. Preserve existing authenticated API and safe response DTO boundaries if reached. No new listener, participant-selected locator or route authority; a manifest's support for an endpoint does not authorize a new data transfer. |
| Strict configuration and bindings: `AptlConfig`, `ExperimentSettings`, `core/experiment/bindings.py`, RAES sealed-plan validators | Preserve unknown-field rejection, strict finite scalars, `_validate_literal_safety()`, secret-shape checks and owner/manifest/configuration joins. Reuse sealed `TrialUnitRequest.execution_controls`; legacy `PlannedTrial` equality checks do not confer these controls. No raw provider payload, argv, environment map or silent missing-value defaults in experiment bindings. |
| Artifact and disclosure boundary: `core/experiment/{resolver,admission_artifacts,spec_loading}.py`, `ParticipantRequestOwner`, SDL control-context validator, existing ACT-620/runtime gates | Reuse `ArtifactResolver`/approved resolver authority and associated-artifact pinning. The project-contained resolver uses bounded no-follow single-handle reads; hash and parse the same bytes. Extend the existing content handoff where necessary without inventing URI lookup. Recheck instantiated participant scope and disclosure independently of checksum validity. |
| Credentials: `core/_credential_sources.py`, `ProcessEnvironmentCredentialResolver`, `EphemeralCredentialBroker`, `CredentialBindingEvidence` | Resolve exactly the configured source through `managed_opencode_executor()`. Preserve name/shape, placeholder, NUL and size checks, failure evidence and cleanup. Model credentials, MCP service credentials, invocation tokens and pack `EnvironmentGrant`s are distinct grants. Do not widen `EnvVars`, add an implicit `.env`/login/provider chain or hash secret values as commitments. Local cleanup is not upstream revocation. |
| Environment/config shapes: `profiles.render_profile_config()`, `agent.py` config/alias validators, `opencode_configuration.py` | Internal MCP entries remain exactly `{command,args,env}` with string environments and approved aliases. Translate to OpenCode's native shape only after admission; preserve per-server gates, `APTL_MCP_DISABLE_DOTENV=1` and config-change detection. OpenCode inherits parent state into MCP children: keep model keys excluded from those children. Pack environment grants retain their own consumer/variable gates. |
| Provider route and request: `RequestCatalog`, `OpenRouterRoute`, `validate_opencode_request()`, `render_opencode_config()` | Validate exact model, approved gateway and exclusive serving-provider policy, supported controls and deliberate omissions. Keep TLS verification, fixed endpoint admission, no userinfo/query credentials and no ambient proxies. Loopback endpoints serve synthetic offline qualification, not arbitrary live destinations. Recheck the pinned build and trusted request binding before every invocation. |
| Host/process state: `agent.py` executable/private-config helpers, `utils/pathsafe.py`, `BoundedProcessRunner`, `_pipe_exchange.py`, `ProcessCleanup` | Fixed argv arrays, no shell, prompt on stdin, private no-follow files, finite output/deadlines and process-group teardown. No control-plane secrets in argv, URLs, prompts, filenames or diagnostics; retain ADR-029's separate treatment of admitted target fixtures. Fresh HOME/XDG/cwd/config/session/history for each trial; no resume/attach, managed/project defaults, plugins, skills or undeclared auxiliary model requests. Private directories and minimal environments are not OS containment; preserve ADR-049/057 appliance, PID/user, mount and egress controls where required. |
| Runtime/action authority: `LilraeParticipantBinding`, `AptlParticipantRuntime`, `LilraeParticipantExecution`, `participant_tools`, common MCP `server.ts` and `lilrae-tool-admission.ts` | Preserve exact inventory, independent participant/configuration joins, runtime-issued generation/action/target authority, strict Ajv argument checks, one-use dispatch, cancellation and safe results. Node socket-path/token/finite-timeout validators must still accept the management-injected carrier. Model or prompt changes grant no tool authority. Autonomous execution and bounded-choice selection remain distinct modes. |
| Untrusted responses and errors: `utils/strict_json.py`, `opencode_events.py`, `core/agent_errors.py`, `BoundedProcessError`, `WorkbenchCredentialError`, `core/experiment/errors.py`, RAES `Diagnostic`/action results | Bound and strictly parse events and metadata. Reject malformed/ambiguous JSON, mixed sessions, invalid terminal sequences and errors after text. Reuse stable error envelopes and `normalize_raes_failure()`; no raw provider errors, validation inputs, exception chains, stdout/stderr or prompt text in public errors. Preserve cleanup proof and distinguish pre-request refusal, terminal failure and uncertain native effects. |
| Evidence, storage and logs: `OpenCodeInvocationEvidence`, existing evidence/provenance builders, `RunStorageBackend`/`LocalRunStore`, `utils/redaction.py`, common `redaction.ts`, `get_logger()`, existing OTel hooks | Extend allowlisted facts at the provider boundary, then existing run-scoped evidence and create-once storage. Keep credentials, headers, environment maps, raw config/events and secret capabilities out. `get_logger()` does not sanitize messages; emit safe IDs, codes, counts and durations. Structured storage uses shared redaction; blob/copy writes require already-safe bytes. Canonical records must fail with `SecretInvariantError` if redaction would alter identity. Export is packaging, never the first filter. |
| Settlement and persistence: `run_participant_workload()`, `LilraeTrialUnit`, `TrialOutcomeReporting`, `ExperimentExecutor`, `finalize_terminal_attempt()` | RAES owns scheduling, durable history, admitted failure disposition and replacement policy. Cancel and drain before releasing executors/credentials or sealing. Preserve peer observations, partial evidence and unknown cessation; retain durable fences when reuse is unproved. A response, exit zero, matching digest or valid archive seal is not an evaluator verdict. Keep the released trial-reporting path and legacy terminal-attempt path distinct at their established handoffs. |

## Actual delivery and the #1421 handoff

Record selected intent, verified launch application and actual transport
observation separately. A rendered config, stdin hash, echoed model option or
matching configuration digest alone does not prove the outgoing request.
Use supported public facilities of the pinned native provider/context path;
do not fork or monkey-patch OpenCode, inject a plugin or add a recording proxy
service. If that build cannot expose required safe application facts, report
the unsupported boundary rather than labelling launch intent as observation.
Fake-provider request inspection qualifies transport construction but does not
substitute for the required runtime evidence handoff.

Agree the safe projection with #1421 at the existing evidence owner. Preserve
plan/entry/run/attempt, participant, action, invocation/session and request joins,
build and configuration/asset commitments, observed message placement/order and
control values or omissions. Correlate generation ID, requested versus reported
model/provider, token categories, cost and finish/status when actually available.
Validate bounded metadata before retention. A session may contain several
requests, retries or tool continuations; never join them by completion order or
infer one request from an aggregated invocation total. Missing or unattested
facts stay unknown, including cost units or generation identity. Preserve safe
partial facts on rejection, timeout, cancellation and evidence/cleanup failure.
No prompt/completion/reasoning capture is authorized by this metadata requirement;
ADR-033 and admitted capture contracts still govern content capture.

## Extension seam, evidence bar and non-goals

The seam is the existing participant-addressed sealed configuration plus its
trusted owner, bounded resolved context bytes, trial execution controls and
managed launch handoff. Reviewed model/control combinations and context slots
belong in consumer-supplied catalogs/domains; native encoding belongs in the
provider adapter. Another model, playbook, participant or supported control must
not require a scenario-name branch, a red/blue-specific selector or editing a
core experiment catalog. New native semantics extend the existing closed
profile/validator/renderer and versioned evidence contract, not an untyped
options bag. Keep composition at Entry and shared values/interfaces in Core;
existing backend/workbench imports are not permission to create new cycles or
private cross-package imports under ADR-064.

Reuse `tests/participant_request_fixture.py`, `tests/opencode_fixture.py`,
request content/binding/dispatch tests, `test_opencode_transport.py`,
`test_opencode_installed_actions.py`, participant workload/cancellation tests
and trial snapshot/serving tests. The decisive evidence traverses sealed-entry
assembly through the real pinned transport for both roles. Qualify the fixed
control first, then generic independent model/prompt variation. Consecutive
changed trials, including after failure, must demonstrate fresh participant
process/context/configuration/history/cancellation/tool authority. Exercise
preamble-only and added playbook message placement/order, required omissions,
provider rejection, stale/swapped assets, unsupported controls, deadlines and
cancellation. Assert absence of secret markers from errors and persisted facts.
Focused mutation checks must catch dropped controls, bypassed binding checks,
stale selection reuse and success claims after evidence/cleanup failure.

Repository owners in scope also include `aptl.json`, the architecture layer map
in `pyproject.toml`, `tools/check_architecture.py`,
`tools/check_lilrae_participant_architecture.py`, `.gc/pack-ownership.json`,
`tools/check_pack_boundary.py`, `.ground-control.yaml`, `.gc/plan-rules.md`,
`.pre-commit-config.yaml`, `tools/run-targeted-tests.sh`,
`tools/ci/select_checks.py` and `.github/workflows/checks.yml`. Reuse the pinned
binary installer and existing wheel/asset packaging; no trial-time downloads.
Local checks stay targeted with staged hygiene; CI owns full suites and
installed-lab qualification. Shared MCP changes select every consumer, and
config/lifecycle changes select installed-lab evidence. Native GitHub blocked-by
relationships remain authoritative; this note neither infers dependency status
nor marks the issue implemented.

Non-goals: implementation, an implementation plan, full matrix live scientific
qualification, paid/live model calls, new hosting or data transfers, study
content/catalog authoring, portable RAES schema changes, new retry/replacement
policy, a containment redesign, broad legacy refactoring or a parallel report
store. No runtime or mutation tests are claimed by this documentation preflight.
