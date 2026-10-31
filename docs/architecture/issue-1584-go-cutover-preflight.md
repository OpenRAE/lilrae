# Issue #1584: Go cutover branch preflight

This issue extends the existing integration controls to `go-cutover`.
It introduces no product architecture and needs no new ADR.
The supplied issue is the delivery contract; this note records design constraints,
not an implementation plan or evidence that remote settings have changed.

## Branch and gate boundaries

- Issue #1584 targets `dev`. The remote `go-cutover` branch must start at a
  verified `dev` revision containing the merged workflow changes, never at the
  issue branch or an unfetched local `dev`.
- Later milestone feature PRs target `go-cutover`. Ordinary work outside the
  milestone retains its existing integration policy. Go port 31 opens
  `go-cutover` into `dev`; the maintainer merges that PR.
- Updates from `dev` into `go-cutover` preserve ancestry through real merges.
  Protection must permit merge commits. If live rules require linear history,
  that conflicts with this contract and needs resolution, not a bypass.
  No rebase, hard reset, force-push, or automatic conflict-side selection.
- `checks.yml` retains one set of jobs and stable required status names.
  Both its PR-base filter and push filter must cover `go-cutover`; push analysis
  keeps the target branch's SonarCloud baseline current.
  `pr-title-lint.yml` needs PR coverage; the Phase E workflow needs
  merged-PR coverage. Phase E is a finalizer, not a required pre-merge check.
- The repository has three other workflows: `release-please.yml`,
  `docs-deploy.yml`, and `scorecard.yml`. Their existing main-only push policy
  stays intact. Do not add cutover release, deployment, or Scorecard runs.
  Existing schedules and manual triggers are not per-branch schedules.
- Dependabot continues to target `dev`. Its changes reach the port through
  real `dev` merges, including Python and lockfile changes. Later conformance
  checks and vectors must expose their effect; this issue creates no Go gates.

The baseline's `dev` entry is the comparison source for cutover protection,
not its smaller `main` entry. Retain every required context, strict freshness,
PR-only changes, and the existing administrator policy. Compare effective live
protection and applicable rulesets too: the JSON records intent, not enforcement.
Preserve any stronger live restrictions and check-provider identities.
Do not weaken `dev`, add bypass actors, or replace the baseline with a second
policy file. Its descriptive fields are not a GitHub API request schema.
Use GitHub's existing administration interface or API with an explicit mapping
of writable fields, then read back the result.
See [GitHub's protection API](https://docs.github.com/en/rest/branches/branch-protection).

## Routing and completion constraints

The existing extensibility seam is `workflow.base_branch` in the repository
workflow configuration. `gc_get_repo_ground_control_context` returns and
validates this configuration. The workflow defaults to `dev`.
The installed `/implement` contract uses it for branch preparation, remote-base
synchronization, and synchronized PR creation. Keep those stages on one base.
The latter two tool interfaces expose no per-call base override: overriding
bootstrap alone cannot establish the milestone route.

This is one checkout-wide scalar, not a milestone selector. Before implementation,
resolve how milestone runs receive `go-cutover` while this bootstrap and unrelated
`dev` work retain `dev`. A branch-scoped value also needs an explicit rule for
surviving `dev` merges and for returning the setting to `dev` at Go port 31.
Do not silently change every run's default, invent an unsupported configuration
key, edit the installed skill, or use direct PR creation to bypass a refused
synchronization record. If the existing setting cannot express the selected
scope through all stages, that is a GRC workflow platform constraint to
resolve before claiming routing works.

Keep the repo-native conventions in `.gc/plan-rules.md` and
[CI verification](ci-verification.md) authoritative. The latter must eventually
record the milestone branch policy. The existing `ship` skill hardcodes `dev`
for PR creation and synchronization; it cannot substitute for milestone
`/implement` routing. The unconditional feature-to-`dev` and squash language in
[releasing](../releasing.md) and the
[promotion preflight](issue-852-devmain-promotion-preflight.md) needs a narrow
milestone qualification. Preserve `make devmain`, the exact `dev` to `main`
title exception, and release commit history. Do not add a title exception for
cutover merges; normal Conventional Commit titles already work.
Squashing the final cutover PR would collapse the milestone's release subjects;
its merge policy must preserve the history consumed by Release Please.

There is a bootstrap completion conflict to resolve: the merged-PR Phase E
workflow can finalize #1584 immediately after its `dev` merge, but the branch
and its protection must be created afterward. Phase E's existing
`grndctl@1.2.1 finalize-merged-pr` transport does not provision branches or
administer protection. Its trusted handoff must not claim these external
acceptance criteria are complete before they are observed. Establish how the
existing completion controls will retain an accurate issue state and final
report through this bootstrap boundary; do not add administrative permission,
post-merge provisioning, or another issue closer to the finalizer.
For later milestone issues, delivery into `go-cutover` is distinct from release
through `dev` and `main`. Preserve that distinction in completion reports.

## SonarCloud boundary

Reuse project `Brad-Edwards_aptl`, organization `brad-edwards`, the existing
coverage producers, scanner, `sonar-project.properties`, and
`tools/sonar/assert_no_new_issues.py`. Keep the required
`SonarCloud quality gate` job, `sonar.qualitygate.wait=true`, and the additional
new-issue assertion. Historical advisory wording in ADR-010/ADR-026 does not
override their later blocking-gate amendments or the current baseline.

Extend the existing project-level long-lived branch pattern with the exact
`go-cutover` name while preserving current matches. Classification occurs at
first analysis and cannot then be toggled; configure it before the first
cutover scan, including a scan triggered by branch creation.
See [Sonar's branch classification contract](https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/project-analysis/long-lived-branch-pattern).
An existing misclassified branch requires a supported repair decision; do not
delete analysis history as an automatic retry.

A long-lived pattern alone produces no analysis. The target needs a completed,
current branch scan before PR analysis can reliably identify new issues.
GitHub Actions already supplies branch/PR analysis identity; do not hardcode
`sonar.branch.name` in shared properties or turn PR scans into branch scans.
Verify the project's existing entitlement supports non-main target analysis;
do not assume it or change plans/services to make it work.
See [Sonar's PR analysis contract](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/pull-request-analysis).

Parity means retaining `dev`'s changed-input selection and secret restrictions,
not forcing every expensive lane on every PR. Docs-only and Dependabot events
can skip SonarCloud today. Demonstrate actual scanner and new-issue execution
on a trusted, non-bot PR selecting coverage into `go-cutover`; a green skipped
job does not prove this acceptance criterion. Forks must not receive secrets,
and a missing credential or service failure must not become a successful scan.

## Cross-cutting layers to reuse

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Configuration and MCP shapes: repository workflow YAML, `gc_get_repo_ground_control_context`, `gc_prepare_implement_branch`, `gc_synchronize_implement_branch`, `gc_create_synchronized_implement_pr` | Use the supported base field and repository/ref validation. Keep invocation-checkout identity, explicit remote refs, real merges, and fresh synchronization attestations. Preserve structured refusals and their `next_action`; no parallel routing schema or branch manager. |
| Workflow input and title validation: `tools/check_pr_title.py`, `pr-title-lint.yml` | Keep `pull_request`, trusted-base-SHA checkout for the title checker, event-file parsing, and the current narrow promotion classifier. Branch names and titles are data, never shell expressions. Retargeting does not grant trust. |
| CI selection: `tools/ci/select_checks.py`, `checks.yml` | Retain SHA-validated diff bases, NUL-delimited paths, bounded lane outputs, all-lane fallback for unknown/config/workflow inputs, and required-job refusal when selection fails. Keep complete coverage from the same revision and existing image/coverage aggregate contexts. No cutover-specific selector or successful failure masking. |
| Runner authority and supply chain: workflow permissions, `tests/test_supply_chain_pinning.py`, ADR-026 | Keep read-only defaults, pinned actions, locked/hash-checked installs, existing SARIF job permissions and fork restrictions. Never use privileged `pull_request_target` to obtain secrets. The Phase E token keeps only its existing scope. |
| Authentication and OS exposure: existing GitHub authentication and `SONAR_TOKEN` binding | Administrative operations use existing authorized GitHub access, separate from CI credentials. Bind secrets through existing credential/environment channels, never token argv, shell tracing, environment dumps, committed files, or secret-file reads. No new PAT or service. No host listener or runtime privilege is introduced. |
| Errors and diagnostics: GitHub CLI/API, MCP result envelopes, `assert_no_new_issues.py` | Preserve nonzero exits, typed tool refusals, bounded Sonar HTTP diagnostics, and missing-token failures. Auth/network errors are not evidence of absent protection or clean analysis. Do not log credentials or add an application exception hierarchy or error envelope. |
| State and evidence: git, GitHub protection/rulesets and Actions, existing Sonar project | Keep durable state with these existing owners. Record relevant refs, revisions, effective settings, and run/analysis identities. No local state database, custom audit service, OpenTelemetry signal, or new storage destination. |
| Product validators: `AptlConfig`, dotenv/environment bindings, SDL/Pydantic admission, API auth/CSRF, runtime redaction and run stores | These layers are not traversed: no product input, DTO, controller, service, listener, or persisted lab state changes. Do not add runtime branch configuration or new validation models. |

## Verification constraints and non-goals

`tests/test_promotion_workflow.py` currently asserts exactly `{main, dev}` in
two trigger tests. Extend those contracts without dropping promotion coverage.
Build on `tests/test_platform_ci_gates.py` for baseline/job parity,
`tests/test_ground_control_config.py` for workflow settings,
`tests/test_lilrae_ci_selection.py` for selection, and the existing
`test_pr_title_guard.py`, `test_sonar_assert_no_new_issues.py`, and
`test_sonar_project_properties.py` contracts where behavior changes.
Parameterize branch parity against `dev`; do not maintain another required-check
list or title parser. Static tests cannot prove live settings or scan execution.

`tools/run-targeted-tests.sh` automatically compares with `origin/dev`.
On a cutover feature branch that can select the entire milestone's changed
tests instead of the issue's tests. Use its existing explicit-path interface,
or add a narrow base parameter there if automatic discovery is required;
do not fork the helper or silently invoke broad local suites.
Local checks remain targeted tests and staged-file `pre-commit run`.
CI owns full suites, coverage, whole-tree lint, Vale, and strict MkDocs.

This preflight changes guidance only. It creates no remote branch, PR,
protection rule, Sonar setting, requirement transition, or completion record.
Issue implementation may change the named workflow filters, checked-in
protection, scoped workflow routing, branch-policy guidance, and their focused
contracts, plus perform the explicitly authorized remote setup after the
maintainer merges the bootstrap PR. It must not change product behavior,
introduce Go code or Go gates (ports 02/02b), weaken protection, reroute
Dependabot, broaden release triggers, or hand-edit versions and changelogs.
Live rules, Sonar settings/entitlement, and bootstrap completion handling remain
unverified here; neither a documentation diff nor a successful PR merge proves
the issue is done.
