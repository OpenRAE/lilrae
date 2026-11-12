# CI verification

Reader purpose: Explanation.
The [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/architecture/ci-verification.md) preserves the original design cut.
Version-specific examples and qualification statements keep their original scope.
This editorial rewrite does not qualify a provider, approve a VM, or authorize a service.


The ordinary Python shards also qualify the packaged provider observer module.
Those jobs install the same pinned Node version as the native transport job.
The observer probes resolve that executable before starting their minimal child environment and pass its absolute path.

They do not add ambient PATH entries to the provider process.
In CI, [Node's built-in test runner](https://nodejs.org/download/release/v22.23.3/docs/api/test.html#coverage-reporters) emits LCOV for those exact packaged-module probes.
The test normalizes only the copied module's source path; line coverage comes from Node.

The existing Python coverage artifacts carry these reports to the combiner and SonarCloud.
All workers retain the existing Python coverage requirements; observer reports are combined across the shards.
Local targeted runs do not enable coverage collection.

Issue #1468 replaces repeated verification with checks selected by changed inputs.
The target is five minutes for Python coverage and ten minutes for ordinary PR checks.
Runner queue time is reported separately.

## Components and contracts

The existing Checks workflow owns required status names.
A change selector reads the Git diff and emits bounded Boolean lane selections.
Unknown paths, workflow changes, missing diff bases, and manual or scheduled runs select all lanes.
Every required job checks selector success before it can report success.
An unselected job reports that no relevant input changed.
The image matrix also selects descendants when a parent or shared input changes.

Source changes select all coverage producers for the existing project-wide SonarCloud analysis.
Docs and image routing remain independent.
Linux runs the retained ordinary Python suite once with line coverage.

Coverage.py uses its Python 3.12 monitoring core.
The measured serial run exceeded the budget after pruning and shared setup.
Split the retained cases into three complementary pytest-split groups.

Each group uses four pytest-xdist workers and pytest-cov's supported worker combination.
Keep each file on one worker to preserve module fixtures and avoid shared module state.
Workers keep separate process environments and pytest temporary directories.

Read-only pack fixtures share declarations and realization results within each process.
Mutation tests copy their declaration fields; backends, stores, and runtime ownership stay separate.
The existing required Python check combines all groups' data before exporting coverage.

All groups and the concurrent fuzz/smoke qualification job must succeed.
The combiner checks that all expected data files exist and uses a read-only token.
The coverage comparison also checks the planner's measured lines with two workers.

macOS and Windows run portability checks instead of repeating Linux planning tests.
The installed-wheel boot retains its independent realization and teardown observations.
Periodic qualification runs retained integration checks and scans unchanged dependencies and images.

The periodic lane pulls the pinned Dashboard prerequisite from the production catalog before test collection.
A missing prerequisite fails preparation.
Live-lab checks require an explicit operator opt-in and credentials.

The required MCP lane also tests the capture lifecycle through an extracted
production red MCP payload. It opens real SSH sessions through the shipped
capture broker, leaves a shell and a one-shot command active, then signals
the MCP process. The complete broker census must reach the configured run
archive with final metadata, faithful close reasons, and valid custody chains
accepted by the transcript collector. Real container loss and a metadata
write failure must produce evidence records and a non-zero shutdown exit.
This check uses the shared isolated SSH fixture; it does not qualify a full
TechVault SOC deployment. The generic installed-wheel smoke scenario remains
a separate installation and realization check.

The controlled HTTPS service in `tests/test_mcp_transport_processes.py` binds
only to loopback and explicitly requires TLS 1.2 or newer before wrapping its
listening socket. Its ephemeral certificate and existing MCP client policy
remain test fixtures. The indexer process test verifies that the real SSH and
MCP path can still query this service with the protocol floor enforced.

The planner builds authored field prefixes once per compatibility application.
Each requirement queries that operation's index.
The index preserves exact fields, descendants, collection entries, and explicit empty declarations.
It does not survive the operation or change scenario authority.

## Data flows and security

Redaction keeps the existing Python and TypeScript public entry points.
Each delegates command parsing to an internal shell helper, which consumes
shared pattern definitions within its language:

```text
redaction -> command helpers -> credential patterns
redaction -------------------> credential patterns
```

Pattern modules never import the recursive redactor or command helpers.
The recursive entry points retain depth and scan limits, JSON handling,
key classification, and the experiment opt-out boundary.
Moving code between these modules must preserve pattern order and output.
The shared golden corpus checks Python and TypeScript parity; focused
redaction, fuzz, and consumer tests check credential masking and bounded work.
CI rebuilds and tests every MCP consumer of the common module.

```text
Contributor changes [untrusted input]
  -> Git checkout and changed-path selector [read-only runner token]
  -> lane selections [job outputs]
  -> existing test, build, scan, and artifact jobs [isolated hosted runners]
  -> coverage and diagnostic artifacts [existing Actions storage]
  -> existing SonarCloud analysis and required GitHub statuses

Scenario declarations [operator-authored input]
  -> parser explicitness map [existing semantic authority]
  -> operation-local prefix index [derived memory only]
  -> requirement delegation and evidence decisions [existing planner boundary]
```

Changed paths are data, never shell commands.
Routing failures must fail existing required jobs rather than skip them successfully.
Untrusted PRs receive no new permissions or services.

Dependency caches hold downloads, not installed executable state or lab credentials.
Existing hash pins and vulnerability thresholds remain active.
Test collection reads no lab environment file and provisions no API key.

Superseded PR cancellation uses a PR-specific group; release and branch validation have separate groups.
Cleanup steps retain their unconditional execution conditions.

## Dev merge queue

Pull requests to `dev` merge through a GitHub merge queue ([ADR-068](../adrs/adr-068-dev-merge-queue.md), #1735).
`dev` does not require strict status checks. `main` and `go-cutover` keep them and have no queue.

- A pull request must pass the required checks before it can enter the queue.
- The queue squash-merges each pull request. The squash commit message is the PR title only.
- The `main` to `dev` back-merge and the `go-cutover` to `dev` merge use a merge commit.
  An administrator merges them with the admin bypass, outside the queue.
- The queue then runs the required checks again on a merge group.
  A merge group contains `dev`, the queued pull requests in front of it, and the pull request.
- `checks.yml` and `pr-title-lint.yml` run on the `merge_group` event for `dev`.
  A required context that does not report keeps the group from merging.
- The change selector compares the merge group with `merge_group.base_sha`.
- The PR title lint gets the pull request number from the `gh-readonly-queue` ref.
  It validates the current title from the GitHub API.
  It fails closed when it cannot read that title.
- SonarCloud analyzes the merge group ref as a short-lived branch.
- A failed required check removes the pull request from the queue. The pull request does not merge.
- The readiness step of the GRC workflow platform adds a ready pull request to the queue.

`tests/test_platform_ci_gates.py` holds these rules against `.github/branch-protection-baseline.json`.
It fails when a required producer for `dev` has no `merge_group` trigger.
It also fails when a branch has no strict status checks and no merge queue.

## Go cutover branch

Milestone 44 ports LilRAE to Go on the long-lived `go-cutover` branch (#1584).
The Python release on `dev` and `main` keeps shipping until Go port 31.

```mermaid
flowchart LR
    F[Milestone issue branch] -->|pull request| C[go-cutover]
    D[dev] -->|pull request with a merge commit| C
    C -->|Go port 31 pull request with a merge commit| D
    D -->|promotion with a merge commit| M[main]
```

- Each pull request of the milestone targets `go-cutover`. Other work keeps `dev` as its base.
- `go-cutover` has the protection and the required checks of `dev`.
  `.github/branch-protection-baseline.json` records both branches.
  A test keeps the `go-cutover` contexts a superset of the `dev` contexts.
- `checks.yml`, `pr-title-lint.yml`, and the Phase E workflow run for pull requests into each protected branch.
  `checks.yml` also runs on pushes to `go-cutover`, so SonarCloud keeps a current analysis of the branch.
  SonarCloud analyzes `go-cutover` as a short-lived branch, as it does `dev`, so each push gets a quality gate result.
- On `go-cutover`, `.ground-control.yaml` sets `workflow.base_branch` to `go-cutover`.
  `/implement` then uses `go-cutover` for branch preparation, synchronization, and pull requests.
  `dev` keeps the default base.
- `dev` merges into `go-cutover` through a pull request with a merge commit.
  Do not rebase, reset, or force-push `go-cutover`.
- Pull requests into `go-cutover` use a Conventional Commit type that does not release.
  Nothing ships before Go port 31, which records the breaking change.
- Go port 31 removes the `go-cutover` entries and the `base_branch` setting.
  Then it opens the pull request from `go-cutover` into `dev`.
  The maintainer merges it with a merge commit, so Release Please keeps each commit subject.
- The release, documentation deployment, and Scorecard workflows run only for `main`.

## Go checks

[ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md) gives
the Go gates, and [the #1553 design](issue-1553-go-toolchain-design.md) gives
their mechanics. `tools/ci/go-gates.sh` runs each gate over the first-party Go
modules: the tracked `go.mod` files, except `web/caddy-build` and test data.

| Job | Gate |
| --- | --- |
| Go lint | `go mod tidy -diff`, `go vet`, `go fix -diff`, and golangci-lint for Linux, macOS, and Windows. The golangci-lint formatters check gofmt and goimports. |
| Go tests + coverage | `go test -race -shuffle=on` with coverage, the gate fixtures of `tools/gates`, the [conformance suite](../reference/conformance-inventory.md) on the clean wheel, and each fuzz test for 30 seconds. |
| Go mutation tests | Gremlins on the changed production lines, or on each whole module with production code for a scheduled or manual run. `tools/mutation-thresholds.json` holds the thresholds. Each run leaves out the files that the tests of the module cannot cover: the files of a nested module, the files that the go command ignores, and the files that the host does not build. |
| Go product tests (macOS, Windows) | `go test -race -shuffle=on` and the mutation gate for the product module, so that the files that only these platforms build are tested and mutated. The Windows job skips the mutation gate until #1617, because Gremlins reads no coverage on Windows. The job installs Python, because the lock tests run a Python child. |
| Go regression tests | The replay of each regression test for the issue of the pull request. |
| Go architecture | `archcheck` checks the repository and the generated diagram against `architecture/model.yaml`, and the change against the design record of the issue of the pull request. |
| Go vulnerability scan | govulncheck on the packages and the tool dependencies of each module. |
| OSV-scanner (Go modules) | OSV on each first-party `go.mod`, and a fixture module with a known vulnerability that must fail. |

- The `go` lane of `tools/ci/select_checks.py` selects these jobs. Go source also
  selects the docs lane, because Vale checks Go comments.
- The conformance cases, the published schemas, and the contract inventory
  also select the `lab` lane. The clean-install lab job runs the lab cases with
  its clean wheel.
- The Go architecture job runs whatever the routing selects. The model also
  covers `web/caddy-build` and the design notes, which are not in the `go` lane.
- SonarCloud needs current coverage from each stack. The `go` lane and the
  Python, MCP, and web lanes select each other, and the SonarCloud job reads the
  Go profiles with repository paths.
- The Trivy filesystem scan reads each `go.mod`. It also proves with the same
  fixture module that it fails on a vulnerable Go module.
- The Go jobs set `GOWORK=off` and `GOTOOLCHAIN=local`.
- The `go-cutover` protection requires the seven Go jobs.
- GitHub runs a schedule and Dependabot from the default branch, which has no Go
  code before Go port 31. Until then, a manual Checks run on `go-cutover` runs the
  full mutation and scans.

The temporary default-branch routing for Go dependency updates and weekly
Checks is bounded by the [issue #1593 preflight](issue-1593-go-cutover-schedules-preflight.md).
It qualifies the earlier bootstrap guidance: existing Dependabot entries keep
targeting `dev`, while first-party Go version updates target `go-cutover`.
The target branch's Checks workflow owns the dispatched run and its Go gates.

The Monday schedule keeps the existing default-branch Checks run.
A separate job dispatches `checks.yml` on `go-cutover` without waiting for other jobs.
Only a schedule on the repository's default branch can start this job.

Push, pull request, tag, and manual events cannot forward a run.
The child uses its own workflow and checks out its own branch.
Its manual event selects all lanes, including full Go mutation and dependency scans.

A failed dispatch fails the parent job.
An accepted dispatch does not establish that the child checks passed.

Dependabot reads its version-2 configuration from `main`.
One temporary `gomod` entry selects `/`, `/tools`, `/tools/lint`, and `/tools/gates` on `go-cutover`.
It opens weekly version updates against that branch.
The existing Caddy module entry continues to target `dev`.
This policy does not enable Dependabot security updates on the cutover branch.
The existing Go scanners provide vulnerability checks there.

```text
GitHub scheduler [external entity]
  -> schedule event -> Checks dispatcher [isolated hosted job]
  -> fixed workflow/ref request, ephemeral job token
  -> GitHub Actions API [authorization boundary]
  -> workflow_dispatch event -> go-cutover Checks [separate hosted jobs]
  -> full gate results and artifacts -> existing Actions storage

main dependabot.yml [configuration store]
  -> module paths and target branch -> Dependabot [GitHub service boundary]
go-cutover go.mod/go.sum files [manifest stores]
  -> dependency versions -> Dependabot
  -> version update pull requests -> go-cutover [protected branch]
```

The protected assets are workflow authority, dependency manifests, and check results.
Only the dispatcher job has `actions: write` for this request.
It performs no checkout and executes no repository code with that token.

The token enters only the CLI environment, never command arguments or files.
The repository comes from GitHub context; the branch is a fixed job value.
These controls prevent untrusted code from using dispatch authority or selecting another target.

Parsed workflow tests check admission and authority; a stub CLI checks the actual command and failure result.
Existing selection tests check that dispatch selects all lanes.
GitHub run records provide the later evidence for actual child execution.

The workflow and Dependabot configuration are the executable architecture model.
This change extends the existing routing decision and needs no new ADR or application model.
The [Go port 31 retirement record](https://github.com/OpenRAE/lilrae/issues/1582#issuecomment-6591003613) names both temporary removals.
The issue's Tasks section also records removal of the dispatcher and replacement of the temporary Dependabot entry.
The retirement must reach `main` before deletion of `go-cutover`.

## Verification policy

Evidence follows changed behavior and risk.
Existing tests can supply sufficient evidence without a new test for each edit.
Remove duplicate assignments, obsolete source-text checks, and repeated scenario setup.
Keep distinct behavior, serialization, rejection, and product-boundary checks.
Test count and coverage percentages are measurements, not reasons to preserve duplication.
Released-kit qualification belongs in the periodic integration lane when it exceeds the ordinary budget.

## References

- [Coverage.py 7.15.2 configuration](https://coverage.readthedocs.io/en/7.15.2/config.html): monitoring core and line coverage.
- [GitHub Actions concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency): PR cancellation groups.
- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use): untrusted inputs and least privilege.
- [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html): explicit test selection.
- [pytest-split](https://jerry-git.github.io/pytest-split/): complementary groups without repeating a full suite.
- [Coverage.py combination](https://coverage.readthedocs.io/en/7.15.2/commands/cmd_combine.html): merge measured data before XML export.
- [GitHub Actions workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows): base-branch filters for `pull_request` and `push`.
- [GitHub branch protection API](https://docs.github.com/en/rest/branches/branch-protection): required status checks of a protected branch.
- [GitHub Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference): version 2, directories and target branch.
- [GitHub workflow dispatch API](https://docs.github.com/en/rest/actions/workflows): create a workflow dispatch event and Actions write permission.
- [GitHub workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow): dispatch with the existing job token.
- [SonarQube Cloud long-lived branch pattern](https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/project-analysis/long-lived-branch-pattern): branch classification at first analysis.
- [SonarQube Cloud Go test coverage](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/test-coverage/go-test-coverage): `sonar.go.coverage.reportPaths`.
- [Gremlins unleash command](https://gremlins.dev/0.6/usage/commands/unleash/): changed-line mutation and the JSON report.

This document describes the verification architecture.
The issue plan owns implementation tasks and measured delivery results.
