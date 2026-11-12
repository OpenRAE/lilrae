# Issue #1646: Scoped tool affordances

This historical Reference preserves the original source record.
The record below describes its own evidence date and revision, where stated.
It does not establish current behavior, implementation completion, or installed qualification.
The preserved file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/architecture/issue-1646-scoped-tool-affordances-preflight.md).
Its last recorded file change before this rewrite was `ff7b71c1c3b2`.
Current interfaces and successor decisions take precedence for present use.


## Decision and inspection boundary

The supplied issue is the delivery contract. Extend the existing installed
participant binding and RAE admission path. Declare scoped tool support only
when that path enforces the authored scope through native dispatch. Adding a
feature name alone is insufficient. No new ADR, policy engine, schema,
scheduler, or persistence mechanism is needed.

Inspection is limited to this repository at
`37d31344dc13e09f7efb76e2d9349134aae1edb8`. It is not the issue's installed
candidate `ece3505c919e374409e3bd0518e2b5dcf0563b8f`. Here,
`_lilrae_participant_capabilities.py` declares autonomous execution and time,
but has no installed tool-binding declaration. `pyproject.toml` permits
`raes>=10.1.0,<11`; `uv.lock` and `requirements/runtime.txt` select 10.1.0.
The issue reports refusal under 10.6.1. Do not assume this checkout contains
the candidate's tool enforcement or that these dependency versions have
identical contracts. The selected released RAE models and public
`participant_tool_support_diagnostics` are the authority for field names,
support levels, required contracts, selectors, and capacity semantics.
Their compatibility with the eventual delivery source remains to be verified.

The [concurrent execution architecture](concurrent-participant-execution.md)
already assigns RAE portable semantics and LilRAE native execution. This note
clarifies its scoped-tool boundary. It is guidance, not an implementation plan
or evidence that a candidate has passed qualification.

## Contract boundaries and invariants

- Keep backend runtime capabilities, participant implementation capabilities,
  installed native bindings, authored tool affordances, and MCP inventories
  separate. A backend feature claim is not a participant grant. An MCP
  `tools/list` result is not admission of the authored policy. An outer harness
  invocation is not evidence of each inner MCP call's semantics.
- `create_aptl_manifest()` and `autonomous_manifest_options()` remain the
  declaration owners. Build claims from validated installed bindings, using
  RAE's `ParticipantRuntimeCapabilities`, feature-support records and
  controlled vocabulary. Reuse
  `PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS`; do not copy its version
  table. The backend and serialized `backend-manifest-v2` must agree on
  feature names, support strength, contracts, constraints and finite limits.
  An `EXACT` declaration requires the full claimed semantics, not merely a
  successful harness launch. Absent, unsupported, or unverified native tool
  support must not acquire scoped support from another installed executor.
- Preserve authored participant and role selectors through parsing,
  compilation, planning and dispatch. Let RAE resolve their meaning. Resolve
  authority to participant identity and its exact installed relation; a role
  is not a unique participant key. Multiple participants may have one role.
  Never grant the union of all participants' tools to a shared policy.
- `LilraeParticipantBinding` and `LilraeParticipantExecution` own native
  consistency checks. Preserve participant/action keys, manifest identity and
  digest, selection/configuration digest, observation boundary, exact targets,
  constraints, generation and execution scope. Associate admitted tool
  bindings with that same identity using the released RAE contract, rather
  than a parallel role-to-tool dictionary. Reject missing, duplicate,
  ambiguous, stale or mismatched mappings before native effects.
- `admit_raes_scenario()`, `ScenarioAdmissionSource`, `RuntimeTargetOptions`
  and `_raes_runtime_target.py` must carry the same installed binding set into
  manifest construction and execution. `plan_for_target()` calls the RAE
  planner and appends native `planning_diagnostics()`. Both the public tool
  gate and native binding checks must pass. Existing pack planning
  compatibility cannot add a missing capability or remove a selector.
- Keep one shared authored policy and implementation-manifest reference for
  the representative concurrent case, with separate participant configuration
  and tool authority. RAE owns scheduling, admission and ordered settlement;
  LilRAE owns reservations, deduplication, cancellation and native cleanup.
  Completion order must not determine which participant owns a tool or result.
- Native capacity is currently eight concurrent actions, with one active
  invocation per participant and no native retry. These are not automatically
  limits for tool count, inner calls, policies or remote MCP sessions. Derive
  each applicable public capacity field from its actual enforcement; do not
  fill unrelated limits with eight. Preconditions, effects and failure-class
  support also need their claimed enforcement, not just matching labels.

## Cross-cutting layers to preserve

This is the data path; every applicable gate remains in force:

```text
Authored scenario + operator-installed bindings + private launch inputs
  -> existing parser/resolver and configuration validation
  -> installed backend manifest + RAE capability gate + native binding checks
  -> one RAE scheduler -> exact participant's native executor
  -> verified MCP profile/transport -> tool argument validator -> service effect
  -> bounded, redacted result -> RAE ordered settlement -> existing run archive
```

| Layer and canonical incumbent | Required guardrail |
| --- | --- |
| Authentication and authority | Installation is trusted operator activity. Participants receive neither runtime managers nor deployment clients or peer credentials. Local stdio is not an authenticated network endpoint. If the existing guest-access route is used, preserve `workbench/access.py`, `dispatch.py` forced-command/key binding and generation checks, and `ProtocolAdmission`. Existing web callers retain `api/deps.py` token validation and `api/middleware/bff.py` Host/session/CSRF checks. This repair needs no new listener or auth bypass. |
| Parsing, artifacts and public schemas | Reuse the RAE SDL parser/compiler and public closed models. Existing experiment inputs retain `experiment/spec_loading.py` bounds and duplicate-key checks, `ProjectContainedResolver`, and `utils/pathsafe.py` contained opens. Resolve/hash the same admitted bytes. Do not reinterpret selector text, introduce a local affordance DTO, or put core tool semantics in a governed extension. |
| Manifest and admission | Validate the real installed manifest with `backend_manifest_v2_model()` and the selected release's public capability checks. Retain native planning checks as a separate validation of actual installation, not a copied implementation of RAE policy semantics. False or inconsistent support records, contracts, limits, profiles and bindings must fail closed before dispatch or deployment mutation. |
| Participant configuration | Reuse `lilrae_participant_configuration.py`: `opencode_manifest`, its target registry, `OpenCodeConfigurationValidator`, canonical digests and `configured_opencode_executor`. `lilrae_participant_workload.py` compares installed and planned configurations. Tool authority is not a model choice, prompt, provider credential or a new arbitrary configuration dictionary. |
| MCP configuration shape and inventory | Reuse `profiles.py` and `agent.py` private-config loading, unchanged-byte check, executable checks, explicit alias expansion and exact inventory verification. The private input has exactly `mcpServers`; each server has `command`, `args`, `env` with an absolute command and string arguments/environment. OpenCode's translated `mcp`/`permission` format is a different output shape. Do not feed one into the other's validator. Preserve default denial and reject unknown profiles or extra/missing tools. Profile inventory can exceed the authored grant: enforce the admitted subset or refuse it; never silently widen it. |
| Credentials and environment | ADR-029/052 and `EphemeralCredentialBroker.prepare_named()` already provide explicit, minimal leases. Key leases by participant/session where roles repeat. Reuse the provider-environment allowlist in `lilrae_opencode.py`; never inherit ambient secrets. If realized-node environment changes are needed, retain `AptlConfig`/`EnvironmentGrant`, `_environment_bindings.py`, `_compose_environment.py` and `environment_file_line()` checks for exact pack, consumer, source and representable value. MCP aliases and node environment grants are distinct contracts. No new secret source or direct secret-file access. |
| Native dispatch and arguments | Own-tool calls must traverse the admitted native tool path; peer-tool calls must stop before the service handler. On the guest route `ProtocolAdmission` checks protocol/inventory/name membership. `mcp/aptl-mcp-common/src/server.ts` separately compiles the advertised JSON Schema 2020-12 and rejects arguments before handlers, tracing and hooks, without coercion, inserted defaults or dropped fields. Neither validation layer substitutes for RAE participant authorization. Reuse the existing handlers and their target/session checks. |
| OS, files and process lifetime | Reuse `LilraeOpenCodeExecutor`, `OpenCodeOptions`, private no-follow files and `BoundedProcessRunner`. Prompts go on stdin; credentials stay in explicit private delivery, never argv, URLs, manifest, public plan or logs. Keep isolated HOME/XDG/cwd, disabled sharing/ambient config/plugins/downloads and bounded output/deadlines. Process supervision is not a sandbox: host administrators and same-user processes are outside the role isolation claim. Do not grant Docker sockets, mounts, extra egress or privileges. Local cleanup does not prove remote work stopped. |
| Errors and observability | Reuse RAE `Diagnostic`, `raes_diagnostics.py`, `experiment/errors.py`, `WorkbenchConfigurationError`, `AgentExecutionError` and `BoundedProcessError`; add no exception hierarchy. Preserve `participant.tool-support-insufficient` where the public gate emits it. Use stable bounded summaries and shared Python/MCP redaction at serialization; `get_logger()` alone does not sanitize. No raw model validation input, configuration, prompt, credential, stdout/stderr or provider error in CLI/API/MCP/log/span envelopes. Keep native failure distinct from failure to commit the result and from an unknown native outcome. |
| Persistence and finalization | RAE's settled snapshot owns combined history. Existing participant evidence publication, run storage and ADR-050 archival/seal owners retain provenance and terminal status after cleanup. Do not introduce a second tool-grant database, shared mutable role state, parallel history writer or new seal format. Store safe binding/artifact identities, not private launch bytes. Never redact identity-bearing canonical bytes and retain their old digest. |

## Qualification and candidate identity

Reuse `tests/lilrae_concurrent_fixture.py`,
`test_lilrae_concurrent_participants.py`, `test_lilrae_opencode.py`,
`test_lilrae_participant_configuration.py`, cancellation/workload tests, and
workbench inventory/transport tests. Their current outer-invocation coverage
does not establish complete scoped-tool support. The fixture's stub-target
manifest composition is a test scaffold, not an installed candidate manifest.

Required evidence is a representative shared-policy scenario with distinct
scoped MCP affordances, admitted by the public RAE gate and exact installed
checks. Deterministic native adapters can qualify own-tool dispatch and
peer-tool denial without a provider call. Exercise both completion orders,
retain both participants' settled history, and assert zero forbidden native
handler calls. A fake that returns role-named text without dispatching a tool
is insufficient. The installed-artifact check must exercise the public target
construction route without replacing or augmenting its manifest.

Negative evidence must retain unsupported profiles, absent scoped support,
false/inconsistent support strength or contracts, capacity overruns, binding
and identity/target mismatches, and peer-tool requests. Planning failures
must leave native/deployment effect counters at zero; runtime peer denial must
leave the forbidden handler counter at zero while preserving admitted peers.
Retain malformed-argument, inventory/config drift, secret-envelope, timeout,
cancellation, duplicate/stale dispatch and unknown-cleanup protections.
Targeted mutation checks should demonstrate that removing scope/binding checks
or falsely declaring support is detected; do not replace behavioral evidence
with assertions that mirror the manifest builder.

The candidate record must identify the full source commit, built artifact
SHA-256, installed distribution version, exact RAE and env-pack versions,
participant implementation manifest/configuration identities, policy/profile,
scenario/pack revision or digest, tool profile/MCP artifact identity and relevant
harness/runtime versions. Distinguish deterministic contract qualification from
live-provider or full installed-lab qualification. This preflight produces no
tested candidate and makes no new support claim.

Reuse `docs/releasing.md`, existing candidate QA records and experiment/family
compatibility documentation for this evidence. Publication stays on established
approved release infrastructure; no temporary hosting or new service. The
release workflow rebuilds artifacts, so source QA does not prove published
artifact byte identity. Dependency changes must keep `pyproject.toml`,
`uv.lock` and applicable hashed exports aligned through `.pre-commit-ci.yaml`'s
existing lock/export commands, not manual hashes or upstream editable installs.

## Extensibility, workflow and non-goals

The seam is the existing per-participant installed binding and verified
profile/executor input, parameterized by participant identity, exact admitted
tool relations and finite limits. A second participant with the same role,
another tool from an already admitted profile, or another qualified harness
must not require changing a central red/blue switch. New semantics or profiles
still require explicit native support and qualification.

Reuse `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/run-targeted-tests.sh`, staged `pre-commit run`, the pack-ownership check
and `.github/workflows/checks.yml`; full suites and installed-lab qualification
belong to CI. Changes to shared MCP code select all its consumers. ADR-064
layering and existing public interfaces apply; do not add private cross-layer
imports to reach profile validation. ADR-070 leaves Python rules active until
cutover; this repair does not require a second implementation in Go. Any actual
Go change also needs its existing architecture model/design gate.

This checkout configures `go-cutover` as the workflow base. The CI architecture
note reserves that lane for the Go milestone and keeps other delivery on `dev`.
Reconcile the delivery lane with that convention before claiming a consumer
candidate; an unshipped cutover artifact is not a released compatibility tuple.
Do not change versions or `CHANGELOG.md` manually. Keep one complete issue
delivery PR, and do not merge or publish through this preflight.

Non-goals are consumer manifest overrides, weakened/removed selectors,
consumer pack redesign, unrestricted tools, a new scheduler, retries, rollback,
OS sandboxing, a credential service, persistence schema, exception framework,
Go migration, live model calls or unrelated cleanup. Individual MCP-call
evidence and broader #1418 work remain separate from whole-policy admission;
that separation never excuses a scoped claim whose native dispatch can execute
a peer's tool. Any missing enforcement needed for #1646 remains inside its
delivery boundary.
