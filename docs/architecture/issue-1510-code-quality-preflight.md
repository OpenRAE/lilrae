# Issue #1510 Code Quality Architecture Preflight

Issue #1510 is the delivery contract under SYS-009. This note records design
constraints for its implementation, not an implementation plan or an accepted ADR.
It changes no production code, checks, configuration, or public behavior.

## Decisions the ADR must make explicit

Directory names do not currently identify layers. `core/deployment` contains
both contracts and Docker implementations; `backends` contains RAES adapters,
contracts, and orchestration. A rule such as `core -> backends -> deployment`
would preserve dependencies in both directions. In particular,
`deployment/_compose_base_container_realization.py` imports RAES materializers,
while `backends/raes_realization.py` imports deployment internals.

The target dependency direction is construction -> application -> contracts,
with concrete adapters also depending on contracts. Application code receives
adapters through existing protocols. Construction selects implementations.
Contracts and leaf utilities never import application or concrete adapters.
Adapters must not call back into application orchestration. Separate adapters
communicate through admitted values and existing operations contracts, rather
than importing each other's implementation. Every layer must also be acyclic.

| Responsibility | Current owners that the ADR must classify |
| --- | --- |
| Construction and external surfaces | `cli/main.py`, `api/main.py` and dependency wiring, workbench bootstrap, service entry points; CLI commands and API routers retain transport presentation. |
| Application orchestration | `core/lab.py`, lifecycle, experiment, evidence and provenance coordinators, RAES orchestration, appliance and workbench workflows. These are not all contract modules merely because they live under `core`. |
| Concrete adapters | Docker/SSH implementations in `core/deployment`, RAES lowering/readback in `backends`, filesystem/run-store and external-service implementations, `aptl_techvault` providers. |
| Shared contracts and validated values | `DeploymentBackend`, `LabResult`/`LabStatus`, deployment realization/boundary values, `BackendIdentity`, `PackIdentity`, configuration, capture/provenance contracts and existing errors. Classify contracts separately from implementations in their current packages. |
| Leaf utilities | `utils/pathsafe.py`, `strict_json.py`, `redaction.py`, `curl_safe.py` and other existing bounded helpers; no application imports or new miscellaneous dumping ground. |

These are responsibility assignments, not instructions to create five new
packages. The accepted ADR must give exact package/module ownership, including
mixed-package exceptions awaiting migration. Include `appliance`, `workbench`,
`validation`, `services`, `core/archival`, `core/evidence`, `core/evidence_bundle`,
`core/execution`, `core/experiment`, `core/provenance`, `core/correlation`,
`core/runtime`, `src/aptl_techvault`, and developer tooling in that classification;
a Python layer contract does not describe the MCP/web process boundaries.
Runtime call direction and import direction are different: an injected operation
can call a backend without the backend importing its caller. Shared contracts
must have one definition, not
parallel application/backend DTOs. Importing a contract also executes package
initializers: `core/deployment/__init__.py` eagerly imports both implementations
and owns `get_backend()`. Merely moving an import into a function or
`TYPE_CHECKING` does not establish a sound boundary.
`core/config.py` combines models with loading, and `core/runstore.py` combines a
protocol with an implementation. Neither whole module becomes a pure contract
by classification alone; retain its canonical validators and storage rules.

[ADR-037](../adrs/adr-037-docker-compose-backend-cohesion.md) remains the authority
for project-scoped Docker access, local/SSH runner parity and existing errors.
The new ADR must explicitly reconcile its composition policy with ADR-037's
issue-specific rejection of strategy objects and delegation solely for length.
Real responsibility collaborators are permissible; moving shared private state
into mixins or proxy modules is not. Protocol inheritance is not implementation
mixin inheritance. Layer checks alone cannot enforce that distinction.

[ADR-010](../adrs/adr-010-sonarcloud-quality.md) keeps its required no-new-issues
gate and global C901 threshold of 15. Its older "C901 only" description needs
an explicit successor clause for scoped idiom checks. Follow
[ADR-000](../adrs/adr-000-use-adrs.md): name which clauses the new decision
supersedes, preserve accepted history, and update the ADR index.
Meet S104 by responsibility; do not add exclusions or split validators from
the contracts they protect.
Keep rules concise in the ADR and link it from coding standards; do not create
a competing rule catalogue in both documents.

Each module owns one responsibility and an explicit public interface. Prohibit
cross-module private imports without turning all internals into a public API.
Reuse one implementation for each shared concern; prefer the standard library
or an established dependency over custom machinery. Comments explain behavior
and constraints, not review history.

## Canonical concerns and required passage

Paths below are under `src/aptl` unless stated otherwise. #1510 does not execute
these runtime layers; its conventions must preserve every boundary for later
refactors. Dependency checks are not evidence that security behavior is intact.

| Layer | Existing owner and required guardrail |
| --- | --- |
| Ingress and authentication | `api/deps.py`, `api/session.py`, `api/middleware/bff.py` and terminal routing own token/session, Host/Origin and WebSocket checks. CLI/API controllers retain their current presentation and call shared application behavior. `api/schemas.py` and `web/src/lib/types.ts` own the existing HTTP projections; introduce no second controller or auth policy. |
| MCP configuration and arguments | `mcp/aptl-mcp-common/src/config.ts::loadLabConfig()` owns config loading, substitution, budgets and capability checks. `server.ts` closes advertised tool schemas and compiles Ajv validators without coercion, inserted defaults or removal of unknown fields. Rejection precedes tracing, hooks and effects and uses the existing `isError` envelope. Preserve handler-specific session/path checks, HTTP TLS/CA handling and SSH policy. A TypeScript interface or cast does not validate runtime JSON. |
| First-party config and contracts | `core/config.py::load_config()`/`AptlConfig` and nested Pydantic models reject unknown fields under ADR-025. `core/contracts.py` owns pure orchestration predicates under ADR-031, not filesystem or backend probes. Tool configuration belongs in developer tooling, not `aptl.json` or a new runtime flag. |
| Pack and RAES admission | `core/scenario_bundle.py::env_pack_bundle()` and `PackIdentity`, env-packs public validation, RAES parse/compile/plan, and `backends/raes_realization.py::interpret_provisioning_plan()` retain their authority. Use published models from the installed RAES dependency. Scenario identity, pack identity, backend target identity and deployment transport remain distinct. Do not reproduce SDL semantics, env-pack schemas or workflow planning locally. |
| Environment shapes and secret sources | `core/env.py` owns `load_dotenv()`, `EnvVars` and placeholder checks. `core/_credential_sources.py::EnvironmentGrant`, config validators, `deployment/_environment_bindings.py` and `_realization_primitives.py` distinguish authored, generated, granted and adapter-supplied values. Preserve exact pack/consumer/variable matching, classification, source selection, Docker versus Compose env-file representability and rejection before mutation. A matching environment variable name is not permission to read it. Promote existing contracts when needed; do not copy private validators. |
| OS execution and resource ownership | `DeploymentBackend`, Docker/SSH runner hooks, deployment boundary/owner-label checks and `core/lifecycle_guard.py` retain argv arrays, cwd/env, bounded timeouts, project/node ownership and mutation locking. `utils/curl_safe.py` keeps auth headers and bodies in private temporary files, outside argv. Injection must preserve those controls, TLS/SSH verification and teardown order. No raw Docker escape hatch or generic host-command runner. |
| Files and persistence | `utils/pathsafe.py` owns containment, no-follow access and private creation/replacement; `utils/strict_json.py` owns duplicate-key/non-finite rejection where required. `core/runstore.py::RunStorageBackend`/`LocalRunStore`, archival and experiment admission retain locks, create-once/seal rules, canonical serialization, digest domains and post-write verification. New dataclasses or model serialization must not change bytes, ordering, defaults, identifiers or hashes. No replacement repository or universal persistence schema. |
| Errors, logs and evidence | Reuse `deployment/errors.py`, run-store errors, `LabResult`, `LabStatus`, startup diagnostics, `api/schemas.py`, CLI exit handling and existing MCP result conversion. Preserve observation failure versus empty inventory and partial readiness versus success. `utils/redaction.py`, its MCP counterpart, `utils/logging.py`, `core/telemetry_export.py` and snapshot serialization retain redaction before each outward boundary. No parallel exception hierarchy, raw Pydantic input/causes in envelopes, or logging setup at import. Telemetry does not replace admitted evidence. |
| Tests and clocks | Reuse `core/correlation/clock.py::ClockProvider`, existing runner seams, `tests/fixture_pack.py` and fixture lifetime in `tests/conftest.py`. Inject the smallest existing effect boundary, not a generic I/O service. Keep real security/parser rejection tests and installed-artifact evidence; move test patch targets with implementation rather than retaining private re-exports solely for tests. Public compatibility exports require a separate compatibility decision. |

Structured internal data needs an existing typed model or a justified dataclass;
external JSON remains untrusted until the owning boundary validates it. Replacing
`object`/`getattr` with casts, permissive defaults, `model_construct()` or duplicate
models hides invalid data. Do not indiscriminately forbid dictionaries, `object`
at genuine untyped ingress, or tolerant external-provider models. Stronger
annotations must not silently change accepted inputs or error behavior.
Use exports from the locked RAES release, not assumed historical import paths.
Distinct trust boundaries can check different invariants on the same data;
"remove duplicate validation" must not remove backend or storage safety checks.

Logging and storage helpers are not universal secret filters: `get_logger()`
does not redact, MCP `errorMessage()` only normalizes exceptions, and
`LocalRunStore.write_file()`/`copy_file()` pass opaque bytes through. Callers
must retain explicit redaction/classification at each sink, including hooks
and error responses. Reuse `tests/fixtures/redaction_parity_corpus.json` for
Python/TypeScript parity and `workbench/mcp_results.py` for authorized MCP
session-handle preservation. Do not change secret classification or redact
away handles needed to continue an authorized session.

## Registries and extension seams

There is no universal installed-plugin registry today. Entry-point declarations
live in `pyproject.toml`; discovery lives in `backends/*discovery.py`,
`validation/scenario_verification_discovery.py` and other purpose-specific owners.
`backends/scenario_family.py::select_family_provider()` and
`resolve_family_contribution()` already share family selection and validated
callbacks. Build on that incumbent for family extensions before extracting
more discovery mechanics. The seam is the existing group, selector, API version,
capability and owner-supplied validator, preserving pinned installation identity.
Retain each contract's exact identity, compatibility, cardinality, provenance
and failure rules. Filter
metadata before loading; never turn pack/config text into executable imports.
Installed extensions remain trusted executable code, not sandboxed data.

Do not merge these plugin contracts with `CollectorRegistry`,
`ProvenanceProviderRegistry`, endpoint tables, or the RAES runtime registry.
They describe different authorities. The
[pack boundary](pack-boundary-design.md),
[ADR-053](../adrs/adr-053-pack-backend-deployment-serving-interaction-seam.md),
`tools/check_pack_boundary.py` and `.gc/pack-ownership.json` remain canonical for
adapter ownership. A dependency checker complements that checker; it cannot
replace pack-fact admission. Provider registries or polymorphism should replace
duplicated provider dispatch, not ordinary value-based validation branches.

## Enforcement boundaries

Use the existing tooling owners: `pyproject.toml`, `.pre-commit-ci.yaml`,
`.github/workflows/checks.yml`, `tools/ci/select_checks.py`,
`.github/branch-protection-baseline.json`, `uv.lock`, generated hashed
`requirements/*.txt`, and `sonar-project.properties`. Local staged hygiene stays
in `.pre-commit-config.yaml`; full checks remain CI-owned. Keep required status
names and the existing read-only Actions permissions, pinned actions and hashed
installation path. A lint job needs no product credentials, daemon, pack download
or network service. Static layer analysis must not import application modules or
load installed plugins. Report paths, rules and edges, not source values.

The extension seam is explicit package/module enrollment and named import
contracts, independent of changed-file routing. CI must check the full enrolled
scope on every applicable run. New scopes extend data/configuration, not copied
commands. Missing enrolled paths, malformed configuration or a missing checker
must fail visibly; an explicitly empty initial scope is different from an
accidentally empty discovery result. Do not exempt indirect paths through legacy
modules or hide local, relative, package-initializer or type-only imports.
If no existing scope can pass without a production edit, report enrollment as
empty; do not claim the repository now satisfies the target architecture.

Keep global C901 active. Add idiom rules only for enrolled code, without blanket
ignores, `noqa`, `NOSONAR` or `type: ignore`. Ruff configuration needs explicit
inheritance when using another config; an explicit `--config` also needs an
explicit target version. See the
[Ruff configuration rules](https://docs.astral.sh/ruff/configuration/).
The project requires Python 3.14, not 3.12; interpret the issue's wording as
modern typing, not a runtime downgrade. Preserve the capture broker's py313
override. Use `datetime.UTC` and Typer `Annotated` without altering timestamp
formats or CLI defaults, help, validation, messages and exit codes.
Ruff's `src` setting identifies import roots, not the set of files to lint;
pre-commit's `files` selects when a hook runs, not its analysis scope when
`pass_filenames: false`. Make enrollment explicit in the invoked check. Keep
CI checks read-only; no automatic rewrites of untouched production code.

Preserve root `eslint.config.js`, the existing per-MCP configs, strict
TypeScript builds and Svelte checks, Vitest coverage producers and Sonar report
paths. The Python layering work neither replaces these gates nor authorizes a
TypeScript refactor. Add any analyzer as developer/CI tooling through the
existing lock/export path; an isolated pre-commit hook must also have its
dependencies available in that environment, not merely in the project venv.

No import-graph tool is configured. Prefer an established analyzer such as
[Import Linter](https://import-linter.readthedocs.io/en/stable/contract_types/)
over a custom dependency engine. Its layer and cycle contracts address imports;
private-symbol imports and forbidden implementation mixins need explicit policy
coverage, not a claim that Ruff complexity checks detect them. Prove activation
and rejection with small boundary fixtures, including indirect violations and
untouched legacy scope. Coordinate the type-checker choice/configuration with
#1327; this issue must not introduce a competing checker or claim lint proves
RAES type compatibility.

At preflight, Sonar has 62 resource entries; 25 refer to nine missing literal
paths. Do not use the issue's older count as a deletion list. Evaluate literal
paths and globs separately; keep the multicriteria ID list and rule/resource
pairs consistent. Remove stale entries without broadening surviving suppressions
or deleting legitimate wildcard rules. Preserve `tools/sonar/assert_no_new_issues.py`.

## Non-goals and delivery limits

This preflight does not deliver the accepted ADR, coding-standards update, lint
configuration, CI changes or Sonar cleanup required by #1510. That delivery must
contain no production refactor. Later issues own moves, composition changes,
registry consolidation and model substitutions. No new feature, public alias,
runtime dependency upgrade, schema migration, security-policy change,
service or hosting is authorized by this refactor. Follow ADR-062 for naming
while preserving existing `aptl` imports, entry-point groups and identifiers.

Retain behavior, wire formats, messages, exit codes, persisted bytes and security
checks throughout the milestone. Before deleting apparently unused code, check
open issues for planned consumers. Update incoming docs and existing traceability
when paths move. Use the supplied UID `SYS-009`; a documentation preflight is
not evidence that the requirement or #1510 is implemented or verified.
Use targeted local evidence and staged `pre-commit run`; whole-tree suites,
coverage, lint and lab qualification remain CI/CD-owned under
[CI verification](ci-verification.md).
