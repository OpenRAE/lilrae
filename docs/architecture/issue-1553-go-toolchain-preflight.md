# Issue #1553: Go toolchain and CI preflight

This note constrains the design for #1553. It is not an implementation plan
or evidence that a gate works. Inspection used `f327d760`, after the local
ADR-065 change. The supplied issue is the delivery contract; no formal
requirement is attached. The [#1552 preflight](issue-1552-go-architecture-preflight.md)
and [CI verification](ci-verification.md) retain their authority.

## Contract and scope

- Follow [ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md)'s
  separate developer-tool modules under `tools/`, including a module solely
  for golangci-lint. Keep `tool`, versioned `require`, and checksums together in
  each owning module. The root product module is `github.com/OpenRAE/lilrae`.
  Do not put every tool dependency into the product graph to satisfy the
  issue's older wording. Standard Go commands come from the pinned toolchain;
  they do not need third-party tool directives. An empty product module does
  not need a fabricated dependency just to produce `go.sum`.
- ADR-065 specifies the latest stable Go release, not Caddy's version.
  [Go's download page](https://go.dev/dl/) lists 1.27.3 at this preflight.
  Resolve and commit the exact supported toolchain at implementation time;
  CI reads the module declarations rather than a floating `latest` selector.
  Prove that the pinned linters and mutation tool support that compiler.
- Go port 02b owns `architecture/model.yaml`, its compiler, generated
  go-arch-lint configuration, and design validation. #1553 can pin the tool
  and prove its invocation with isolated fixtures. It must not create a
  competing layer map, design-front-matter schema, or placeholder green
  architecture status. Whole-repository architecture enforcement remains a
  dependency on 02b before product packages arrive. A fixture import rejection
  does not establish that all of ADR-065 is enforced.
- ADR-065 defines two mutation metrics, but no numeric thresholds. Measure
  both thresholds and time limits on the fixture packages, recording compiler,
  tool version, runner, counts, concurrency, and cold/warm durations. Thresholds
  can only rise. Zero, an assumed percentage, and the tool's default timeout
  are not substitutes for this evidence.
- [ADR-026's #1193 amendment](../adrs/adr-026-advisory-ci-vulnerability-scanning.md)
  makes Trivy and OSV blocking. Its original advisory text is historical.
  ADR-065 extends Vale to Go doc comments; ADR-038's original Markdown-only
  scope no longer describes the Go gate. Preserve all Python and TypeScript
  gates until port 31.

## Canonical owners and extension seams

| Concern | Incumbent and required reuse |
| --- | --- |
| Routing and status | `.github/workflows/checks.yml`, `tools/ci/select_checks.py`, and `.github/branch-protection-baseline.json` own jobs, Boolean selections, and required names. Extend these together. Retain unknown-input and unavailable-diff selection of all checks. Regression discovery must run on every PR, including test-only changes and every commit type. |
| Tool and package scope | Go module declarations own dependency versions; Go package discovery owns buildable packages. Separate product, developer tools, Caddy, vendored dependencies, and negative fixtures. A shared module/package selection seam belongs in developer tooling, not a second architecture schema or copied workflow globs. 02b owns component assignments and import permissions. |
| Lint configuration | Use the pinned golangci-lint v2 schema and its configuration validation. Pass the repository configuration explicitly. Map ADR-065 to supported settings, including non-default staticcheck/revive rules, cognitive complexity 15, tests, and the `integration` tag. Keep gofmt/goimports in the formatter configuration. No copied reference config with example exclusions, blanket test exemptions, or changed-lines-only lint. |
| Pack ownership | `tools/check_pack_boundary.py`, `.gc/pack-ownership.json`, and `tests/test_pack_boundary_policy.py` own owner discovery, admitted facts, exact historical exceptions, and safe diagnostics. Extend their source selection and identifier classification. Do not introduce another fact list, ownership schema, or Go SDL parser. |
| Coverage | `sonar-project.properties`, the existing coverage producers, and `tools/sonar/assert_no_new_issues.py` own project analysis and the no-new-issues gate. Add native Go coverage and retain the existing project/organization, quality-gate wait, and issue check. |
| Supply chain | `.github/dependabot.yml`, the existing OSV/Trivy/dependency jobs, `.trivyignore.yaml`, and `tests/test_supply_chain_pinning.py` own refresh, scanning, waivers, and integrity. Include root and tool modules without merging Caddy's graph. Keep `uv.lock`/hashed exports and npm locks as their languages' authorities. |
| Local and CI verification | `tools/run-targeted-tests.sh`, `.pre-commit-config.yaml`, `.pre-commit-ci.yaml`, `.gc/plan-rules.md`, and `CONTRIBUTING.md` define targeted development and CI-only full checks. Reuse `tests/test_lilrae_ci_selection.py`, `tests/test_platform_ci_gates.py`, and the existing pack/Sonar tests for their contracts. |
| Prose | `.vale.ini`, `.vale/styles/`, and `tools/{install-vale,vale-lint-hook,vale-lint-all}.sh` own the pinned Vale binary, styles, and entry points. Extend this path for Go comments without another style installation or extracted-prose repository. |

Module discovery must stay inside the repository and exclude installed trees.
Do not run an unqualified repository-root `./...`, or assume it crosses nested
modules. `web/caddy-build` has its own module, security test, build, and local
`go-jose` replacement with another module. Keep those owners intact; do not
rewrite vendored code to meet first-party style. Detect new first-party modules
so they cannot disappear between hard-coded lint, scan, and coverage lists.
Reject missing expected packages; distinguish the deliberately empty initial
product module from failed discovery. Fixtures must explicitly exercise the
empty-product case as well as a nonempty package.
`go mod tidy` has module-wide scope even when test and lint commands name
packages. Prove its discovery against fixture and installed-tree locations too;
package filters on another command do not constrain it.

CI must control module/workspace selection and effective toolchain settings;
an ambient `go.work`, `GOFLAGS`, or automatic compiler upgrade must not change
what was verified. Tool invocation must select the tool's dependency graph
while analyzing the intended target module. A shared workspace must not undo
golangci-lint's isolation. This follows the upstream
[dedicated-module guidance](https://golangci-lint.run/docs/welcome/install/local/).
Cache downloads by module checksums, toolchain, and host, then validate their
integrity. Do not reuse an untrusted PR's executable state or successful verdict
as trusted branch/release evidence.

## Required passage through security and validation

| Layer | Required behavior |
| --- | --- |
| Actions identity and authorization | Retain read-only default permissions and commit-SHA action pins. Fetch issue labels with narrowly scoped read access; pass no token to tests. Keep existing SARIF upload permissions local to scanner jobs and existing fork/Dependabot restrictions. Never execute PR tests through privileged `pull_request_target`, expose release credentials, or grant write access to make a check report. |
| Event and configuration shapes | Validate event kind, full commit IDs, issue number from `<issue>-<topic>`, repository identity, contained paths, and Boolean outputs before use. Failed label lookup is not an absent `bug` label. Reuse event parsing and Git-diff conventions in `select_checks.py`; use Go's parser for test declarations and upstream parsers for tool configuration/reports. Malformed config, missing executables, invalid reports, and missing expected artifacts fail visibly. Do not create a general validation framework. |
| Pack admission and environment binding | `pack_facts()` already uses `AptlConfig`/`ScenarioSourceConfig`, configured source resolution, admitted pack content, and the RAES parser. Preserve those checks and failure without an owner or facts. The checker loads installed adapters, so it is executable dependency code, not a credential-safe static sandbox. Use the existing locked environment and synthetic fixtures; do not load operator dotenv files or invent runtime env/config flags. `core/env.py` and deployment environment-grant rules remain unchanged. |
| OS execution and files | Treat paths, refs, test selectors, and branch names as data. Use argv arrays, NUL-delimited Git paths, exact escaped test names, and explicit cwd. Reject traversal and symlink escapes when copying fixtures. Replay and mutation use disposable contained directories, bounded child processes, and cleanup on failure/cancellation. Disable checkout credential persistence for these jobs. Keep tokens out of argv, shell tracing, caches, and artifacts. No host lab, Docker socket, or private key is needed by the tool fixtures. |
| Errors and observability | Reuse exit status, Go test JSON, scanner reports, Actions summaries, and short-retention artifacts. Report revision, package/test, rule, outcome, and safe location. A parse/build/tool failure must remain distinct from a policy finding or behavioral test failure. Preserve the pack checker's path-and-kind-only output; do not print authored credential facts, full environments, or raw authenticated responses. No new exception hierarchy, runtime logger, or telemetry service. |
| Persistence and runtime contracts | Store only disposable test state and established CI artifacts. Product `RunStorageBackend`/`LocalRunStore`, canonical bytes/digests, locks, redaction, API schemas/auth, and MCP `isError` conversion are not involved in this tooling change. Do not route CI records through them, copy their DTOs, or weaken their validation to simplify a fixture. Existing product paths retain the boundaries in the #1552 preflight. |

New first-party tool settings should be closed and validated by their owner.
For tool reports, parse the pinned producer's documented format and require the
fields used for the verdict; a success-looking substring in console output is
not validation. `nolintlint` must require a specific linter and explanation.
That proves comment syntax, not a false positive: review must verify the reason.

## Gate behavior that must not be conflated

**Required statuses and routing.** No workflow-level path filter may prevent a
required context from appearing. Each new required job must check routing
success and report either the executed result or explicit no-relevant-input
success. A failed, cancelled, malformed, or missing selected result cannot
become a green skip. Test these paths through the aggregate, not just the
selector function. Retain stable existing names, including `OSV-scanner
(uv.lock)`, unless every enforcing consumer is updated together. Cutover
protection remains a superset of `dev`. Require the new contexts on
`go-cutover`; do not require contexts on a live branch that lacks their workflow.
The baseline is intent, not proof of live protection or a GitHub API payload.

**Regression replay.** Use `// regression: #<issue>` attached to an actual Go
test declaration. Select added or changed marked tests, not every test in a
changed file. Parse PR base/head commit identities once: changed-line selection
uses the PR merge base; regression replay uses the explicit base revision and
head tests. Do not mistake the Actions merge checkout for either identity.
Run each selected test separately with uncached execution and verify its named
run/fail/pass events. Compilation, dependency, setup, timeout, panic unrelated
to the asserted bug, no matching test, and skip failures do not prove the bug.
Review must confirm the failure is the expected behavior, not just a nonzero exit.

Base replay overlays only the necessary head tests and test fixtures onto base
production code. Keep base dependencies and production inputs intact; do not
copy head `go.mod`, implementation helpers, generated production code, or a
`replace` pointing at head to make it compile. A regression that needs a new
API needs a base-compatible reproducer. Unrelated new tests in the same file
must not manufacture a compile failure that is counted as success. The same
selected test must pass at head. Do not use cached test results or a failing
unrelated test as evidence.

The bug-label requirement needs explicit scope during coexistence: ADR-065
governs the Go implementation, while Python/TypeScript still ship. Check every
PR for Go regressions, and enforce the matching issue marker for Go bug fixes.
Do not silently demand Go tests for Python-only bugs or add a second language's
regression framework in this issue. Reconcile the ADR wording if a broader
bug-label gate is intended. A commit prefix cannot exempt a Go regression.
Keep non-issue branches such as Dependabot and branch promotions distinct from
failed issue lookups; still inspect their marked tests. Issue labels can change
without a new commit, so the verdict must record the observed label state and
support a fresh check before relying on it.

**Mutation.** Exercise Gremlins' changed-line selection against fixed PR
revisions, including added, renamed, deleted, and test-only inputs. Use its
native selection and report rather than another mutation engine. Keep efficacy
`killed / (killed + lived)` distinct from mutant coverage
`(killed + lived) / (killed + lived + uncovered)`. Noncompiling mutants do not
count; report timeouts separately and never turn incomplete execution into a
passing score. Equivalent-mutant claims do not authorize suppressions. An empty
result with changed production Go fails under ADR-065, including changes with
no supported mutation operator; do not silently classify these as no input.
Changing that rule requires an explicit ADR correction, not a wrapper bypass.
Verify behavior against the pinned release; upstream
[command documentation](https://gremlins.dev/next/usage/commands/unleash/) includes
development-version options and is not evidence that the chosen release has them.

**Formatting, tests, and lint.** A command that prints differences is not
necessarily a failing gate: assert nonempty gofmt output fails, and prove the
selected versions' `go fix -diff` and `go mod tidy -diff` exit behavior. Do not
apply fixes in CI. Run `go vet`, govulncheck, and race/shuffled tests over the
declared package scope. The race detector needs a supported host/architecture
and C compiler; do not inherit Caddy's static-build `CGO_ENABLED=0`. Preserve
the shuffle seed for reproduction. Compilation of another OS/tag variant does
not prove its runtime tests passed. 02b must consume the same supported
OS/build-tag scope rather than silently checking only host-default imports.

**Coverage and scanners.** Extend the existing all-producer routing closure in
both directions: a Go analysis needs current Python/MCP/web coverage, and their
source changes need current Go coverage once Go is indexed. Use native Go
coverage with `sonar.go.coverage.reportPaths`; keep `_test.go` out of source
indexing and map reports to the actual checked-out files. Missing reports fail.
The [SonarCloud Go contract](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/test-coverage/go-test-coverage)
uses `go test` coverage, not converted Python XML. A small passing fixture can
prove ingestion before product code exists; do not present fixture coverage as
product coverage or include intentionally failing fixtures in normal analysis.

Keep govulncheck's reachable-code findings, OSV's dependency findings, and
Trivy's filesystem/image/IaC findings distinct. Scan developer-tool graphs as
build dependencies as well as product dependencies; inspect local replacements.
Retain OSV's failure on findings/tool errors and Trivy's fixed-vulnerability
thresholds, secret/misconfiguration gates, and tracking of unfixed findings.
New root/tool Dependabot entries must target `go-cutover`, where those modules
exist; keep existing `dev`/Caddy entries and the merge-forward convention.
No new waiver, service, upload destination, or credential store is needed.

## Local work, evidence, and delivery limits

The local Go test command needs explicit package/test targets and a base-ref
parameter consistent with `.ground-control.yaml`. Do not copy the Python
runner's hard-coded `origin/dev` into the cutover command. With no targets,
report that fact and request explicit selection; never fall back to a suite.
Run complete selected packages, not isolated `.go` files that omit their
dependencies. Local hooks receive staged filenames; full lint, tidy, mutation,
coverage, and suites remain CI-only. The existing pack hook has
`pass_filenames: false` and scans its full covered scope. Adding Go triggers
alone does not satisfy staged-only work: retain one checker with bounded local
selection and full CI coverage, updating its existing contract test accordingly.

The pack checker also skips `pack identifier` findings outside `src/aptl/`.
Go globs alone therefore miss that class. Extend generic-source classification
without broadening historical line-digest exceptions to Go. Preserve owner
facts and approved adapter boundaries; do not ban legitimate registration by
turning every adapter-owned file into generic core. Keep synthetic negative
fixtures outside normal source discovery and explicitly exercise them through
the real checker. No fixed list of scenario names or secrets.

Vale's existing installer and configuration must cover Go doc comments and
retain Go file/line diagnostics. Verify the pinned version's
[code-comment support](https://docs.vale.sh/formats/code) before writing an
extractor. Do not lint string literals as prose, lose block/package comments,
or waive symbol names and directives by disabling entire files. Update
`CONTRIBUTING.md` and `ci-verification.md` when the commands actually exist,
including the milestone's PR target instead of unconditional `dev` guidance.

Prove each gate with a passing and a violating fixture using its actual pinned
command. Existing workflow tests can verify failure propagation; stubs alone
do not prove a linter, scanner, or mutation tool detects its violation. Include
the regression test that passes on base, compile/skip/no-match rejection,
missing coverage, and pack-fact rejection. Negative dependency fixtures stay
test data, not vulnerable runtime dependencies. Keep fixture outcomes distinct
from normal job outcomes and preserve diagnostic artifacts on failure.

The scheduled full run has a deployment dependency:
[GitHub schedules execute only from the default branch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
A cron edit present only on `go-cutover` is inactive. Activate the full-run path
through a reviewed default-branch Checks change selecting a fixed cutover
revision, or explicitly resolve this delivery dependency with the maintainer.
Manual execution can prove the command but not the schedule. Do not introduce
an external scheduler, broad write token, or early product release to bridge it.

This preflight adds guidance only. #1553 delivers tooling and fixture evidence;
02b delivers the architecture model and design checker. Product packages,
runtime schemas/services/repositories, API changes, release/cutover work,
cross-language regression frameworks, and weakening existing gates are outside
this issue. Live branch protection, scheduled execution, and SonarCloud coverage
need actual service-side evidence during delivery; none is established by this
repository inspection. No branch setting or remote artifact is changed here.
