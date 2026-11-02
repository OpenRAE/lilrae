# Issue #1468 CI Feedback and Test Suite Preflight

Issue #1468 is the delivery contract; no GRC requirement is attached.
This note sets implementation boundaries. It changes no runtime, test selection,
CI behavior, or testing policy. The performance targets and substantial pruning
both require evidence; neither parallelism nor moving work establishes success.
The companion `ci-verification.md` describes the intended verification
architecture; neither document establishes that its performance choices work.

## Planner authority stays unchanged

Keep the optimization inside `apply_planning_compatibility()` in
`src/aptl/backends/raes_planning_compat.py`. Build any explicitness index once per
operation and pass it through both authored-concern callers. Its lifetime ends
with that operation: a later call must see mutations to the scenario map.
No global cache, scenario-attached cache, persisted index, or new public option
is needed. Preserve the early return when no compatibility decision applies.

The parser's explicitness map is authoritative. Lookup must preserve equality,
dot descendants, bracket descendants, explicitly empty collections, absent
defaults, and the current permissive fallback for a missing/non-mapping map or
non-string requirement path. Prefixes must respect separators: `node.a` must
not match `node.ab`. Do not substitute Pydantic fields-set state, values, or
truthiness. Keep indexing bounded by input size; avoid generating every character
prefix or scanning all keys again for every query.

Reuse `plan_aptl_scenario()`/`AptlPlanningOptions`, `AptlRuntimeManager`, RAES
compile/plan contracts, and the existing requirement/authority identity tuple.
`scenario_planning_compatibility_discovery.py` still validates exact pack/backend
identity, provider cardinality, permitted concern sets, and finite runtime limits.
Keep requirement and authority adjustments paired; optimization must not change
delegation, EXACT authority, observation strength, or configuration corroboration.
`_runtime_value_limits()` retains its lock and restoration in `finally`.
Do not patch the upstream planner or widen provider decisions to gain speed.

## Test value and effect boundaries

`tests/fixture_pack.py::admit_fixture_pack()` and the owned
`tests/fixtures/packs/materialization-envelope/` already supply small scenarios
through production pack validation. Use those for generic machinery and small
synthetic cases for isolated rejection behavior. Keep representative released
pack qualification through `env_pack_bundle()` and the composed static gate;
an adapter's own declaration cannot independently prove pack compatibility.
Reconcile #1099 around that representative budget, rather than adding every
released kit to the ordinary suite.

Share parsed scenarios and admitted realization results only for read-only
assertions. Copy mutable projections for negative cases. A shared runtime manager,
evaluator, snapshot, backend, or mutable test environment is not a read-only
fixture. Session/module fixtures run once **per worker**, so adding workers can
multiply expensive pack setup. The static gate currently also stages a pack at
module import; setup belongs under fixture lifetime and cleanup, not collection.

`tests/conftest.py` globally permits the TestClient host and shrinks RSA keys.
These are test conveniences, not production security evidence. Retained Host
rejection and production key-policy evidence must exercise their actual boundary.
Prune by distinct failure detection, setup cost, duration, and maintenance cost;
dataclass assignments, duplicated assertions, and exact workflow text are not
contracts merely because existing tests assert them. Preserve public wire formats
and meaningful rejection/security cases with the smallest adequate evidence.
Record major removals/consolidations and reasons once; no per-test approval ledger
or one-for-one replacement tests.

### Selection is separate from live authorization

`pyproject.toml` currently defines `integration` as local filesystem/process work;
`tests/helpers.py::LIVE_LAB` instead uses `APTL_SMOKE`, and the curated live gate
also uses `APTL_LIVE_GATE`. These are different concerns. A filename, slowness,
or the existing integration marker does not establish permission to contact a lab.
Classify retained live effects before replacing `-k "not integration"`.
Keep lane/marker definitions in pytest configuration and fixture/collection
behavior in `tests/conftest.py`; no independent test-discovery framework.
Retained ordinary tests with `integration` in their filename must remain eligible.
Every retained integration test needs an executable lane with prerequisites;
selected lanes must fail if required tools are missing or all work is skipped.
This resolves #1321 for retained tests without resurrecting deliberately deleted
tests. Useful fuzz tests remain explicitly selected.

Ordinary import and collection must neither acquire credentials nor provision
API keys, even for deselected tests. `tests/helpers.py` currently reads `.env`
and can renew a TheHive key at import, and ordinary tests import it for unrelated
helpers. Move live acquisition behind explicit fixture execution and live opt-in;
keep inert pack/parsing helpers import-safe. Do not hide acquisition in lazy
module attributes or retain stale imported credential constants. Selecting live
tests authorizes neither silent key renewal nor arbitrary external endpoints;
required provisioning must be explicit. Missing required live configuration is a
visible lane failure, not a default credential or a successful skip.

## CI routing and completion contracts

`.github/workflows/checks.yml` owns ordinary checks;
`.github/branch-protection-baseline.json` records required context names, while
live GitHub rules enforce them. Keep those names stable. Extend the existing
`trivy-image-gate` aggregation pattern: a required completion job runs even after
a dependency fails, checks the routing result, and requires success for every
selected job. A deliberately unselected job is distinguishable from missing,
failed, cancelled, or unexpectedly skipped work. Unknown paths, malformed routing,
and unavailable diffs must fail visibly or conservatively select all relevant work.
Workflow-level path filters must not leave required contexts pending.

There is no incumbent general change router to reuse. A small CI-owned routing
boundary is sufficient; do not introduce a service or policy framework. Use one
set of selection rules for PR, periodic, and release modes. Periodic/release
qualification can request the full **retained** suite without copying commands
and diverging from PR lanes. Diff against the PR base correctly; handle pushes,
renames/deletions, new packages, and events without a PR payload. Pass paths and
event values as data, never shell source; preserve filenames safely, including
whitespace and shell metacharacters. Routing results are non-secret booleans
or validated package identities, never executable command fragments.

| Inputs and canonical owners | Required propagation and extension seam |
| --- | --- |
| Docs, `mkdocs.yml`, `.vale.ini`, `tools/vale-lint-*.sh` | Documentation gates; agent/testing/policy docs also affect policy verification. A prose edit does not justify blanket runtime work. |
| `src/aptl`, `src/aptl_techvault`, `tests`, pytest config | Python behavior and relevant API/CLI/portability/qualification consumers. Backend versus adapter ownership stays as documented in `pack-boundary-design.md`. |
| `web/package*.json`, `web/src`, `src/aptl/api`, API schemas | Frontend and API consumers of changed behavior; frontend-only selection cannot hide a changed Python API contract. |
| `mcp/*/package.json`, adjacent locks, TypeScript/build config, `mcp/build-all-mcps.sh` | Discover packages from manifests and honor common-first builds. `aptl-mcp-common` changes select all consumers and transport coverage. Run retained Wazuh, Indexer, and Reverse suites; remove the stale build-only description. Do not trust `--passWithNoTests` as proof. |
| `pyproject.toml`, `uv.lock`, generated `requirements/*.txt`, Hatch build/assets | Dependency, packaging, installed-artifact, API-extra and image consumers. Reuse `hatch_build.py` and `src/aptl/_asset_manifest.py`; sharing a wheel never replaces clean install environments or negative artifact variants. |
| Compose, `config/`, container Dockerfiles, copied sources/scripts | Follow real build contexts, COPY inputs, and base-to-derived image dependencies. Node22's derived image copies Python source/runtime requirements; `web/Dockerfile.api` consumes Python/API dependencies, while `web/Dockerfile` consumes frontend/Caddy sources. A Dockerfile-only filter is insufficient. |
| Workflow/routing/build scripts, pre-commit configs, `.gc/plan-rules.md` | Conservatively select affected checks, routing and supply chain verification. No second hand-maintained package or image registry competing with manifests and the existing image matrix. |

Remove the duplicate Ubuntu suite while retaining Linux CLI/import/init smoke.
macOS exercises focused filesystem/permissions, process, config, CLI, and host
behavior; retain appropriate Windows checks, including Windows process/handle
paths excluded from Linux coverage. POSIX shell snippets are not portable lane
definitions. Keep the installed-wheel boot's native causal assertions and
`scripts/ci/assert_boot_realization.py`/`assert_project_teardown.py`: fresh venv,
empty working directory, validated project plus node labels, and absence proof
for stopped resources, anonymous volumes, and helper containers. No daemon-wide
prune or shared warm lab can substitute for this proof.

Supersession cancellation is keyed by workflow, event, and PR identity. Pushes,
scheduled runs, and release qualification must not collide with PR cancellation.
Preserve teardown opportunity on cancellation and bound resource-owning work;
`always()` alone does not prove cleanup survives runner termination. Keep the
owned lab on an ephemeral runner, allow active resource-owning teardown to finish,
and verify cancellation/partial-start behavior.

## Security, validation, errors, and state

| Layer | Canonical incumbent and required passage |
| --- | --- |
| Actions auth and untrusted inputs | Keep read-only default token permissions, SHA-pinned actions, fork/Dependabot secret restrictions, and job-scoped SARIF write permission. No privileged `pull_request_target` execution of PR code or PAT. An unprivileged job must not contaminate trusted release caches/artifacts. |
| Supply chain and cache trust | `pyproject.toml` -> `uv.lock` -> `.pre-commit-ci.yaml` generated hashed exports; adjacent npm locks -> `npm ci`; `tests/test_hashed_requirements.py` and `test_supply_chain_pinning.py` enforce integrity. Cache downloads by OS/runtime/lock identity; revalidate installs. No unpinned coverage plugin/tool fetch or stale common build. `mcp/build-all-mcps.sh` already demonstrates script-free install plus explicit build; avoid duplicate `prepare` builds without omitting required lifecycle work. |
| Vulnerability policy | ADR-026's **#1193 amendment** supersedes its original advisory wording. Preserve blocking exit semantics, tracked unfixed findings, `.trivyignore.yaml` scoping, and fork-safe upload. Deduplicate record/gate execution only if findings and failure semantics survive. Cache databases with freshness handling; never cache a successful verdict indefinitely. Scheduled full scans must reevaluate unchanged locks/images against new advisories; release qualification must name and scan the artifacts actually shipped. ADR-058 remains proposed. |
| Product config and admission | `AptlConfig`/`load_config()` retain strict Pydantic shapes and project-name validation; `ScenarioBundle`/`env_pack_bundle()` retain pack/import/content admission; RAES compile/plan and `interpret_provisioning_plan()` retain model validation. No CI bypass flag, parallel SDL schema, or fast path around admission. |
| Environment binding | `core/env.py` owns dotenv parsing/hydration. `core/deployment/_environment_bindings.py` binds declared variables via generated values, authored values, explicit pack/node grants, or admitted startup adapters. Matching environment names do not grant authority. Keep missing/empty source refusal and env-file name/value validation; no ambient env injection to make synthetic fixtures pass. |
| Secrets, OS exposure, TLS | ADR-029 and `utils/curl_safe.py` already protect headers/basic auth/bodies using temporary `0600` files. Live helpers currently duplicate curl handling and expose secrets in argv; reuse the safe wrapper when refactoring that boundary, with explicit assertion of its failure result. Keep lab-CA verification and existing SSH identity boundaries. No credentials in argv, test IDs, exception text, shell tracing, caches, coverage artifacts, or uploaded project directories. Never access the user's secret file. |
| API/MCP auth and error envelopes | `api/deps.py`, `api/middleware/bff.py`, API schemas, and common MCP config/SSH/telemetry remain unchanged authority boundaries. Retained evidence covers token, Host/session/CSRF and restricted transport behavior where affected. Preserve `ScenarioPlanningCompatibilityError`'s bounded codes, RAES diagnostics, `LabResult`/startup diagnostics, and redaction at Python/TypeScript serialization boundaries. No new exception hierarchy or raw provider/environment payloads in CI failures. |
| Observability and persistence | Reuse Actions conclusions/summaries, pytest durations/counts, coverage reports, existing SARIF artifacts and code scanning. Product logging stays with `utils/logging.py::get_logger()` and common MCP telemetry/redaction. No runtime CI metrics, OTel pipeline, qualification database, or parallel runstore. Temporary projects and worker state have explicit ownership/cleanup; evidence uses existing approved infrastructure and retention. |

## Coverage and evidence boundaries

`pyproject.toml` owns line-coverage scope for both shipped Python packages;
`sonar-project.properties` owns report paths. The lock currently selects
Coverage.py 7.15.2 and CI Python 3.12. That version permits `sysmon` line coverage
on 3.12 but has plugin/context/concurrency restrictions and cannot measure branch
coverage there; compatibility must be checked against actual execution features.
See the [versioned coverage configuration reference](https://coverage.readthedocs.io/en/7.15.2/config.html#run-core).
Adoption requires equivalent measured files/executed lines on the same selection,
explained differences, and no silent fallback mistaken for a speedup.

`pytest-xdist` is already declared; `pytest-cov` is not currently locked.
`coverage run -m pytest -n ...` alone is not worker coverage. If bounded workers
are justified after pruning, use supported worker collection and combination,
with locked dependencies and per-worker files/state. The documented
[pytest-cov xdist integration](https://pytest-cov.readthedocs.io/en/latest/xdist.html)
is one supported option, subject to version qualification. Worker coverage and
coverage of child processes are separate concerns. Isolate temporary directories,
cwd/environment changes, ports/sockets, generated keys, build outputs, and Docker
project identities; do not schedule shared lab mutation concurrently. Keep portable report paths,
transport coverage, and accurate LCOV source paths. Sonar dependencies/downloads
must understand selected producers: missing expected reports fail; omitted lanes
are disclosed, not filled with stale or fabricated zero-cost coverage.

The evidence seam is lane/mode plus exact revision, runtime, runner class, worker
count, core, and cache state. Report selected/executed/skipped counts, actual
deletions/consolidations separately from parametrization changes, slow setup/calls,
queue time, required-check elapsed time, and summed runner minutes. Parallel job
durations are not elapsed time. Three comparable successful runs must establish
the issue's five-minute Python and ten-minute required-check targets; document
remaining qualification costs separately. This preflight provides no such proof.

## Policy ownership and non-goals

The delivery must reconcile `.gc/plan-rules.md`, `AGENTS.md`, `CONTRIBUTING.md`,
`docs/CODING_STANDARDS.md`, testing/static/live-gate guidance, applicable ADR-026
scheduling language, and workflow contract assertions together. Require evidence
proportionate to changed behavior/risk; adequate existing tests may supply it.
Do not preserve blanket new-test rules through workflow-shape tests. Reuse the
behavioral shell-stub pattern in `tests/test_platform_ci_gates.py` for failure
propagation and existing promotion/consistency/pinning contracts where useful;
exact job text, a 60-minute timeout, and historical test counts are not invariants.
`docs/testing/boot-realization-coverage.md` should describe retained evidence
accurately. Local verification stays targeted through `tools/run-targeted-tests.sh`
and staged `pre-commit run`; full suites, coverage, and whole-tree checks stay in CI.

No new runtime schemas, DTOs, controllers, repositories, services, caches, plugin
registries, or validation frameworks are needed. This issue does not redesign
RAES, application authentication, scenario ownership, product lifecycle, release
publication/provenance, or dependency authority. It does not authorize new hosting
or third-party processing, protected-branch changes, PR merging, unrelated issue
closure, blanket security waivers, hiding failures, timeout inflation, or moving
the existing suite wholesale to nightly runs. Performance evidence and the
coordinated one-issue/one-PR implementation remain downstream work.
