# Issue #1593: Go cutover dependency updates and weekly Checks

This historical Reference preserves the original source record.
The record below describes its own evidence date and revision, where stated.
It does not establish current behavior, implementation completion, or installed qualification.
The preserved file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/architecture/issue-1593-go-cutover-schedules-preflight.md).
Its last recorded file change before this rewrite was `5913199f82f6`.
Current interfaces and successor decisions take precedence for present use.


This is a temporary routing change for milestone 44, delivered through `dev`
and activated when it reaches `main`. It needs no new ADR or product component.
The supplied issue is the delivery contract; this note sets boundaries, not an
implementation plan or a claim that the automation is active.

## Existing contracts and branch ownership

The working tree has the Python Checks workflow. The local Git ref
`origin/go-cutover` at `6d3e220b` also contains the #1553 design, its decision
14, and the Go gates. Those branch contents were inspected without changing
checkouts. Reconfirm the target revision during delivery; this is local-ref
evidence, not a fresh observation of GitHub.

- `.github/workflows/checks.yml` owns the checks and their status names on
  each branch. Dispatch that file on `go-cutover`; checking out Go code inside
  the default branch's Python workflow would execute the wrong job graph.
- `tools/ci/select_checks.py` treats `workflow_dispatch` as an all-lanes run.
  On the inspected cutover ref, that includes the Go lane. Its mutation jobs
  supply no diff base for a dispatch, which selects whole-module mutation in
  `tools/ci/go-gates.sh`. Periodic integration already accepts dispatches.
  Preserve those contracts; no additional input or simulated schedule event
  is needed. Regression replay remains PR-only by design.
- On cutover, `go-gates.sh`, the pinned tool modules, and the existing mutation,
  govulncheck, OSV, and Trivy gates own Go verification. Preserve their module
  discovery, thresholds, tool pins, and failure behavior. Do not copy them to
  `dev` or `main` to solve routing.

## Routing decisions

Keep the existing Monday cron and the default-branch Checks run. Add only a
dispatch job to that workflow, admitted by the actual `schedule` event and the
repository's default-branch ref. It must have no dependency on test or selector
success, so a failing default-branch check cannot suppress cutover coverage.
PRs, pushes, tags, and manual dispatches must not forward runs. In particular,
the cutover child must never dispatch another child when this change reaches it.

Reuse the hosted runner's GitHub CLI and the `GH_TOKEN`/`GH_REPO` environment
binding pattern in `release-please.yml`. Address the current repository and
`checks.yml` explicitly, with `go-cutover` as the target ref. The dispatcher
needs its own job-scoped `actions: write` permission and no checkout, project
code execution, dependency installation, or third-party dispatch action.
Keep every other job's existing permissions; do not grant workflow-wide write.
[GitHub supports dispatch with the job token](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow).

The dispatch API owns the request shape: workflow filename, repository, `ref`,
and only inputs declared by the target workflow. Use no inputs for the current
contract. API/authentication failures, a missing branch, or a disabled workflow
must fail the dispatch job. Do not substitute a successful skip, suppress an
exit status, or retry an ambiguous dispatch blindly and create duplicate runs.
Acceptance of the request does not prove that the child checks succeeded.
Record the target and, where the selected API version returns it, the child
run URL/ID in Actions diagnostics. No custom polling service is needed.
See the [dispatch API contract](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

Extend `.github/dependabot.yml` using its existing version-2 `gomod` pattern:
weekly version updates, a nonzero PR limit, the existing `build` commit prefix,
and `target-branch: go-cutover`. Name the four manifest directories explicitly:
`/`, `/tools`, `/tools/lint`, and `/tools/gates`. A `directories` list can share
this policy. Preserve all current entries targeting `dev`, including
`/web/caddy-build`; do not retarget the existing Caddy updater.

Do not scan all nested directories with a wildcard, duplicate an ecosystem /
target / directory combination, or include scanner fixtures and vendored
modules. Root is a manifest directory, not a promise to discover every nested
module. These are version updates; `target-branch` does not extend Dependabot
security-update coverage to a non-default branch. Existing scanners provide
the separate vulnerability gates. See [Dependabot's options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).

## Cross-cutting boundaries

| Layer and canonical incumbent | Required passage |
| --- | --- |
| GitHub admission and permissions: `checks.yml`, branch-protection baseline, ADR-026 | The dispatch writer runs only on the trusted default-branch schedule, with job-local authority. The child receives its own workflow's permissions, never the parent's token. Preserve required status names, PR protections, fork/bot secret restrictions, and existing SARIF write scopes. Never use `pull_request_target` or a PAT to bypass these restrictions. |
| Configuration parsers: Dependabot v2 and Actions workflow schemas | Use their native keys, explicit target branch and workflow file, and no undeclared inputs. `check-yaml` checks syntax, not GitHub semantics. Existing YAML tests use `yaml.safe_load`, where unquoted `on` is the Boolean key `True`; reuse that convention rather than adding a second parser or schema. |
| Environment and OS boundary: existing `GH_TOKEN`/`GH_REPO` convention, ADR-029 | Bind the ephemeral token only to the dispatch step. Repository and ref are quoted data; keep secrets out of command arguments, request-header flags, shell tracing, environment dumps, files, and summaries. Use no token-bearing curl command. No checkout means no persisted Git credential or project code sharing the write token. No listener, Docker privilege, or lab environment is introduced in this job. |
| Selection and execution: `select_checks.py`, `go-gates.sh`, `tools/internal/mutation` on cutover | Preserve all-lanes dispatch selection, whole-module mutation without a base, fail-closed selector checks, pinned tools, `GOWORK=off`, and `GOTOOLCHAIN=local`. The child uses the target branch's workflow and checkout revision. Never bolt Go gates onto the Python parent or fork the selector. |
| Go architecture admission on cutover: `architecture/model.yaml`, `tools/internal/architecture`, `go-architecture` job | This routing adds no Go package, import, or component. Preserve the existing model and strict design-record schema when the change reaches cutover; do not invent a component or a parallel model for workflow YAML. |
| Diagnostics, errors, and storage: GitHub CLI/API and Actions job results/artifacts | Keep nonzero failures and native API diagnostics without exposing headers or credentials. Report dispatch acceptance separately from child results. GitHub runs, Dependabot update logs/PRs, and existing scan artifacts remain the state owners; no database, new log envelope, exception hierarchy, audit service, or storage destination. |
| Product validation: `AptlConfig`, `core/env.py`, API auth/CSRF, SDL admission, shared redaction, run stores | These layers are not traversed. There is no product configuration, DTO, controller, service, persistence, or application error change. Do not import runtime validators or invent runtime branch settings for CI routing. |

The extensibility seam is declarative configuration: one fixed, job-local
target-branch value and the native Dependabot directory list. Keep repository
identity derived from GitHub context, not hardcoded to an owner or checkout.
The next first-party module extends that list; gate discovery already belongs
to `go-gates.sh`. A future target change edits the routing value and Dependabot
target, not the canonical verification jobs. No caller-selected arbitrary
branch input, branch registry, workflow matrix, or general scheduler is needed.

## Evidence, retirement, and non-goals

Reuse `tests/test_platform_ci_gates.py` for parsed workflow/permission contracts
and execution of shell steps with a stub CLI; `tests/test_supply_chain_pinning.py`
for existing supply chain coverage; and `tests/test_lilrae_ci_selection.py` for
selection. Evidence must distinguish schedule forwarding from PR/push/manual
non-forwarding, API failure from success, and a cutover full run from a green
parent. Retain promotion contracts in `tests/test_promotion_workflow.py`.
Do not write tests that merely mirror YAML text or introduce a workflow-engine
emulator. Any new executable selection logic needs focused negative cases;
existing cutover mutation gates remain the canonical mutation machinery.
Local checks stay targeted via `tools/run-targeted-tests.sh` with explicit test
paths and staged-file `pre-commit run`; full suites, whole-tree prose checks,
and full mutation runs belong in CI.

Static checks cannot prove activation. A `dev` merge alone does not activate
default-branch configuration. Delivery evidence must identify the `main`
revision, Dependabot's module update jobs and eligible PRs targeting cutover,
and a scheduled parent linked to the dispatched child at its actual commit.
The child must execute the full mutation and Go scan gates. A module with no
available update may produce no PR; record that separately from misconfiguration.
An exhausted PR limit can delay updates. GitHub schedules can be delayed or
dropped, so this issue promises forwarding of each schedule that runs, not a
new scheduling SLA. The existing Phase E finalizer must not report unobserved
default-branch activation as proven delivery.

The implementation must record both temporary removals in Go port 31 (#1582),
not just mention them in this note: remove the forwarding job and its write
permission, and remove/replace the cutover-targeted Dependabot policy with the
normal post-cutover Go update policy. Propagate retirement through `main`
before deleting the target branch. Deleting only the branch leaves failing
scheduled dispatches and Dependabot jobs on the default branch.

Non-goals are changing Go gates, dependency versions, mutation thresholds,
branch protection, release/deployment/Scorecard routing, product architecture,
or workflow completion machinery. This preflight changes guidance only; it
does not dispatch jobs, edit issues, alter remote settings, or implement #1593.
