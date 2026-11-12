---
id: SEC-008
title: "Platform Safety Pull Request Gates"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-09-20T00:00:00Z
updated_at: 2026-09-20T00:00:00Z
---

# SEC-008: Platform Safety Pull Request Gates

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/SEC-008/requirement.md).


## Statement

Pull requests to `dev` shall require the existing pre-commit, control-plane test, MCP
test, platform dependency audit, and clean-install lab boot checks. The audit
shall fail for actionable vulnerabilities in shipped CLI/API and MCP
dependencies while intentionally vulnerable target assets remain advisory.
The installed-distribution check shall start one supported small lab scenario, verify
a native container effect, stop the lab, and prove project-scoped cleanup.
The supported profile and any temporary platform vulnerability exception shall
be documented with its affected component and reason.

## Rationale

APTL's control plane handles operator credentials and host resources. A
successful workflow run without required branch protection, or an advisory
platform audit that hides actionable findings, does not protect the merge
boundary. One bounded installed-wheel lifecycle smoke catches packaging and
cleanup failures without claiming full scenario or participant qualification.

## Traceability

- IMPLEMENTS → CONFIG `.github/workflows/checks.yml` (Blocking platform audit, one installed-wheel lifecycle smoke, and the Go gates)
- IMPLEMENTS → CONFIG `.github/branch-protection-baseline.json` (Exact required check contexts of dev and go-cutover)
- IMPLEMENTS → CODE_FILE `scripts/ci/assert_project_teardown.py` (Workspace-scoped container, network, and volume absence proof)
- IMPLEMENTS → ADR `docs/adrs/adr-026-advisory-ci-vulnerability-scanning.md` (Platform versus intentional-target vulnerability policy)
- IMPLEMENTS → DOCUMENTATION `docs/testing/platform-pr-gates.md` (Supported gate profile and exception policy)
- TESTS → TEST `tests/test_platform_ci_gates.py` (Required context, fail-closed audit, smoke cleanup, and Go gate regressions)
- TESTS → TEST `tests/test_assert_project_teardown.py` (Effective workspace resource cleanup regression)
- IMPLEMENTS → GITHUB_ISSUE `969` (Required platform safety and installed-lab smoke checks)
