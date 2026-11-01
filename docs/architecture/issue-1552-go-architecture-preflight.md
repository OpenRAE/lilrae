# Issue #1552: Go architecture preflight

The supplied issue is the contract. This note constrains its architecture
decisions; it does not implement the issue, accept an ADR, or define an
implementation plan. Inspection at `04e9434b` found ADR-064 as the highest
numbered ADR and `workflow.base_branch: go-cutover` already configured.
Recheck the next free number when authoring the ADR.

The [#1510 preflight](issue-1510-code-quality-preflight.md#canonical-concerns-and-required-passage)
already records the shared boundaries. Preserve their behavior and ownership,
not the Python module arrangement. The Go decision needs the following
additional constraints.

## Architecture and authority

- Keep ADR-064's entry, application, adapter, core, foundation and plugin
  responsibilities. Entry constructs dependencies; application and adapters
  share core contracts and do not import each other. Classify by responsibility,
  not by today's directory name. In particular, `core/lab.py` is orchestration.
  Do not translate mixins into embedded structs sharing hidden state, or turn
  `foundation` into a `util`, `common` or `helper` package.
- Compile-time plugin registration conflicts with ADR-064's rule that no
  first-party package imports a plugin. The successor must name the narrow
  entry/composition exception. Ordinary application, core and adapter packages
  still cannot import plugin implementations. Use explicit construction and
  registration, not import side effects, runtime code downloads or a new
  dependency injection framework.
- One public extension package must expose a usable contract to external
  owners. Its exported signatures cannot require inaccessible `internal/`
  types. Keep implementation packages internal and interfaces as small as their
  actual consumers need. Do not mirror every concrete implementation with an
  interface or publish internal Docker/RAES machinery to satisfy this rule.
- Keep architecture metadata, issue design and runtime contracts distinct.
  The model owns components, package membership, permitted dependency edges,
  extension boundaries and per-component third-party module permissions.
  An issue design references that model and declares its packages, dependencies
  and model changes; it cannot grant an import that the model forbids.
  Neither document defines another SDL, configuration schema or workflow engine.
- The ADR must settle the model's format/location, component identity and the
  design artifact's location and issue association. Reuse the repository's
  design-note convention and `.gc/plan-rules.md`; avoid another issue database
  or approval workflow. Define the check's observable limits: package and
  dependency agreement does not prove design intent or security behavior.
- Model compilation must reject unknown keys, unmatched or overlapping package
  assignments, unknown dependencies, stale component references and invalid
  designs. State coverage for commands, helpers, guest binaries, tools, tests,
  generated code and supported OS/build-tag variants. A host-only import graph
  is not whole-repository coverage. Generated linter settings are derived
  outputs, not another editable rule source; findings need location, rule and
  actionable correction. Do not introduce enrollment, a debt baseline or
  changed-lines-only architecture checking for Go.
  Resolve package imports to their modules, including replacement/workspace
  dependencies; a module allowlist must not become a global import exemption.
- `tools/check_architecture.py` and `[tool.lilrae.architecture]` remain the
  Python gate until cutover. Its current `enrolled` and `extension-api` lists
  are empty: an installed gate is not proof of fully checked Python code.
  Preserve `tools/check_pack_boundary.py` and `.gc/pack-ownership.json`'s
  pack-ownership semantics when selecting their Go enforcement owner. The Go
  architecture model must not silently discard that separate concern.

## Required passage through existing boundaries

The documentation change itself passes ADR governance, GRC workflow platform record
validation, documentation checks and staged hygiene. It introduces no runtime
input or privilege. The design it records must preserve the following layers.
Paths abbreviated below are relative to `src/aptl/` unless otherwise stated.

| Layer and canonical incumbent | Required Go boundary |
| --- | --- |
| Web ingress: `api/{main,deps,session}.py`, `api/middleware/bff.py`, `api/routers/terminal.py`, `web/src/lib/{api,bff,session}.ts` | Preserve Host/DNS-rebinding and same-origin mutation checks, bearer validation, cookie plus port-scoped session factor, single-use launch/ticket behavior, authenticated health/unknown API routes and streaming behavior. Terminal access also checks origin, target eligibility, lab state, canonical endpoint and pinned SSH identity. Browser defenses are not authentication. Keep the bootstrap exception explicit; do not generalize it into API tokens in URLs. API auth must not be removed because ADR-061 changes the seat desktop. |
| Config, MCP and external input: `core/config.py`, `utils/strict_json.py`, `mcp/aptl-mcp-common/src/{config,server}.ts` | Preserve closed first-party config, field bounds, defaults, discovery and semantic checks before effects. MCP currently validates the advertised JSON Schema 2020-12 without coercion, inserted defaults or silently removed properties, before tracing/hooks/dispatch. Typed Go arguments alone do not replace this gate. External provider-owned extras follow their existing contract, not a blanket first-party rejection rule. |
| Credentials and environment: `core/env.py`, `core/_credential_sources.py`, `core/deployment/{_environment_bindings,_realization_primitives}.py`, `utils/placeholders.py` | Durable config carries source locators, not secrets. Preserve exact pack/consumer/variable grants, authored/generated/operator/adapter source distinctions, placeholder checks and Docker versus Compose env-file representability. Read only explicitly granted process variables. A matching name or a pack declaration grants no ambient host access. Reject unavailable or unrepresentable bindings before mutation. |
| Admission and execution: `core/scenario_bundle.py`, `backends/scenario_family.py`, `core/experiment/`, `core/execution/`, `workbench/{app,access,guest_binding,dispatch}.py` | Preserve pack identity, released RAES parsing/semantic admission, capability and participant authorization, sealed plan identity and no-replanning handoff. Follow the [released runtime boundary](issue-1465-released-experiment-tuple-preflight.md): RAES owns portable semantics, runtime progression and run/study producers. Do not recreate its DTOs, scheduler, retry policy or terminal-state machine locally. An unavailable released Go contract is a dependency to resolve, not permission to approximate it. |
| OS effects and transport: `DeploymentBackend`, `core/deployment/{_compose_resource_ownership,_compose_owner_labels,_docker_endpoint_binding}.py`, `core/lifecycle_guard.py`, `core/endpoints.py`, `core/soc_ca.py`, `utils/curl_safe.py` | Preserve daemon selection, project/workspace/native-resource ownership, lifecycle locking, bounded calls and local/SSH semantics. Secrets stay out of process argv and shell interpolation. Retain SOC CA verification and terminal SSH pins; do not broaden existing TLS exceptions. Cancellation must stop owned work and report residual resources honestly, without deleting foreign resources or starting another retry loop. |
| Seat and execution policy: `core/{appliance_boundary,execution_boundary}.py`, `appliance/policy.py`, `appliance/seat/{image_trust,launch_descriptor,namespace}.py` | Preserve signed policy/config shape checks, trusted image identity, private per-user state and physical-host/cross-seat containment. Keep VM-only and inner-seat policy versions distinct; an environment flag cannot convert one claim into another. A digest proves byte identity, not publisher trust or successful qualification. |
| Files, archives and identity: `utils/pathsafe.py`, `core/runstore.py`, `core/evidence/`, `core/archival/`, `core/correlation/` | Preserve descriptor-relative no-follow containment, private creation, atomic durable writes, finalization locks, create-once records, seal immutability and read-only export. Keep planned trial, attempt, family, snapshot and backend identities distinct. RFC 8785 and BLAKE3 choices must reproduce owner-defined bytes and digest domains; ordinary JSON serialization is not canonicalization. No new generic repository or portable record schema. |
| Errors and observability: `core/lab_types.py`, `core/deployment/errors.py`, `api/schemas.py`, shared MCP handlers, `utils/{logging,redaction}.py`, `core/telemetry_export.py` and their MCP counterparts | Preserve classified startup outcomes, timeout versus cancellation, unknown inventory versus empty inventory, CLI exits, HTTP/terminal responses and MCP `isError` results. Go error wrapping must not leak input values or raw upstream errors. One shared redaction policy protects logs, results, snapshots, persistence and OTel exporter output, including exception events. Preserve trace/correlation identities; telemetry is not evidence. Keep logs off MCP protocol stdout. |

Strict decoding needs an explicit contract for duplicate keys, exact key casing,
unknown fields, trailing documents, invalid text, numeric precision, missing
versus null/zero values and resource limits. `DisallowUnknownFields` alone is
insufficient: legacy Go JSON decoding accepts duplicate members and matches
struct fields case-insensitively. Verify the selected Go version and decoder
against the existing corpus rather than changing accepted input accidentally.
YAML decoding and JSON Schema validation must use the dialect and semantics of
the owner; one does not substitute for the other.
See the [Go JSON documentation](https://pkg.go.dev/encoding/json).

`get_logger()` does not automatically redact. `cli/web.py` enables access logs
and `api/main.py` has a token-bearing bootstrap route. Review that output path
explicitly; this inspection did not run a live leakage test. The new `slog`
policy must cover HTTP access logs, subprocess failures, structured attributes
and OTel exports, not assume a logger name guarantees sanitization. Preserve
ADR-029's distinction between operator secrets and intentional target fixtures.
Use `tests/fixtures/redaction_parity_corpus.json` and its existing parity tests
as common evidence, rather than creating a third independent redaction policy.

## Adapter, Docker and delivery seams

The [family adapter contract](../reference/family-adapters.md) distinguishes
pack acquisition from executable adapter installation, and callable API,
family API, release tuple and persisted schema versions from one another.
Static registration changes delivery, not those admission rules. Retain one
qualified owner for the six capabilities, exact atomic target matching,
bounded operations, detached trial inputs, capture finalizer identity and reset
receipt compatibility. Keep core-owned persistence and redaction outside plugin
authority. RPT's independently maintained adapter needs an explicit build and
distribution route: installing its Python wheel will no longer extend a
prebuilt Go binary. The public API/version seam must permit a separately owned
adapter without forcing it to import host internals or bundling it unasked.

The Docker comparison must cover Engine operations and Compose orchestration
separately. Replacing CLI calls with an Engine client does not by itself provide
Compose project interpretation, build/profile behavior or SSH parity. Any
hybrid design still has one typed deployment boundary and one source of daemon,
ownership, timeout and redaction policy. Account for streaming/exec behavior,
API compatibility, ambient Docker context overrides and remote artifact
availability; `SSHComposeBackend.supports_local_artifacts` is currently false.
Do not expose a generic command/HTTP passthrough or reimplement Compose.
The variation seam is the configured transport under that boundary, not a
second semantic deployment provider. Docker documents its distinct
[socket, SSH and TLS transports](https://docs.docker.com/engine/security/protect-access/).

Reuse `hatch_build.py`, `_asset_manifest.py` and `core/assets.py`'s single
asset-selection/materialization contract. The Go delivery decision must name
how release-built, target-appropriate helper binaries reach packaged build
contexts and the offline seat payload without a compiler or download at
`lilrae lab init`. Offline materialization is not a claim that every ordinary
lab start has all external images cached. Seat offline dependency closure uses
`appliance/input_images.py`, `scripts/appliance/assemble-seat-inputs.py` and
`appliance/guest/provision-offline.sh` (the latter two are repo-relative).
Retain secret/state exclusions, image digest pins and installed-artifact
qualification. Apply ADR-049 with its ADR-059/060/061 amendments: do not revive
superseded inner-seat isolation or participant web-auth claims. Proposed
ADR-054/055 are not evidence of delivered controls.

Keep release orchestration in `.github/workflows/release-please.yml` and
[releasing](../releasing.md). A selected release builder must fit GitHub
artifacts, platform-tagged binary wheels, provenance-before-publication and
SBOM coverage of the actual embedded Go dependencies, not just the wheel
wrapper. Product release version, Go module major version and extension API
version are separate decisions. Preserve `aptl` until 10.0.0 and other retained
identities under ADR-062. The pinned pack-owned sync service is outside the Go
port; its exclusion does not waive TLS, provenance or asset-closure obligations.
Keep Svelte and derive API types from one Go-server OpenAPI document, without
making HTTP DTOs the domain model or hand-maintaining a second TypeScript schema.

## Enforcement evidence and issue boundaries

The ADR must name a supported Go/toolchain policy and concrete libraries for
every concern the issue lists. Verify maintenance, license, platform support
and contract fit from upstream sources. Keep per-component module admission
separate from a repository-wide dependency list. Compatibility with the RAES
Go standard requires evidence from its owner; this repository-only inspection
does not establish that agreement.

Map rules from all three [Google Go style documents](https://google.github.io/styleguide/go/)
to exact, version-supported checks/settings, with partial coverage stated.
A list of linter names is not a complete mapping. Distinguish golangci-lint v2
[linters](https://golangci-lint.run/docs/linters/) from
[formatters](https://golangci-lint.run/docs/formatters/); keep judgment rules
in the coding-standards review checklist. Error wrapping, logging ownership,
context propagation, goroutine lifetime, bounded concurrency and cleanup need
explicit rules even when a linter covers only part of them. Do not replace
responsibility-based design with line-count splits or copy old suppressions.

Contract tests, shared fakes, golden bytes, parser/security fuzzing, `cmp.Diff`,
race checking and shuffled runs complement each other. Avoid assertion
libraries and private implementation patching. Golden updates must be reviewed
as contract changes. `testing/synctest` controls concurrent test time but does
not virtualize external socket/process I/O; retain effect seams and separate
real transport qualification. See [synctest's limitations](https://pkg.go.dev/testing/synctest).

Mutation policy needs a pinned tool proven against the selected Go version,
changed-line selection against the PR base, an explicit efficacy denominator,
and treatment of uncovered, invalid, timed-out and equivalent mutants. A tool
failure or empty selection is not a passing score. Measure the first threshold
on the first packages; record the result and only permit increases. The
scheduled full run belongs to the existing Checks workflow. This is distinct
from the zero-findings architecture rule and is not a baseline exemption.

The regression rule needs a machine-readable test selector tied to the issue,
not heuristic matching of every test changed in a PR. Base replay runs the new
test and necessary fixtures against base production code; compilation failure,
missing dependencies, no matching test, a skip or infrastructure failure is not
the required behavioral failure. Require the intended failure on base and
success on head. A test requiring packages or APIs absent from base cannot
satisfy this rule; a regression needs a base-compatible contract reproducer.
Keep new-functionality tests distinct. Run untrusted tests in
isolated CI without release credentials; never evaluate PR metadata as shell.

Reuse `tools/ci/select_checks.py`, `.github/workflows/checks.yml`,
`.github/branch-protection-baseline.json`, `.pre-commit-config.yaml`, `.pre-commit-ci.yaml`,
`sonar-project.properties`, `.ground-control.yaml` and `.gc/plan-rules.md`.
Preserve required status names, fail-closed selection, pinned tooling and the
distinction between the platform and the intentionally vulnerable targets. Both implementations
must run the same conformance vectors with isolated state until port 31;
comparison must not normalize away security or persisted-byte differences.
Follow [the cutover conventions](ci-verification.md#go-cutover-branch), without
another branch manager or early release path. Local verification remains
targeted tests and staged hygiene; full checks stay in CI.

Issue #1552 changes the ADR, coding standards, ADR index, precise supersession
marks and the 18 named requirement records in the GRC workflow platform and the repository.
Preserve UIDs, priority, lifecycle state, behavioral obligations and historical
traceability. Remove implementation prescriptions rather than substituting
Go-specific ones. Reconcile stale SCN-010/RTE-001 language with the accepted
RAES boundary and SEC-008 with cutover branch policy; do not resurrect retired
DSLs or weaken security to make language-neutral wording easy. Follow ADR-000:
supersede only named clauses in ADR-003/007/010/011/025/037/064, preserving their
remaining controls and accepted history.

This preflight does not select the final dependency set, change requirements,
mark an ADR accepted, add Go code or CI, build the architecture compiler,
inventory contracts or RAES consumers, publish artifacts or merge branches.
Those remain the issue's decisions and the explicitly assigned later ports.
