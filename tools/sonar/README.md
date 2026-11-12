# Check SonarCloud findings

Use this guide to investigate the repository's new-code issue gate.
Keep `SONAR_TOKEN` in the existing CI environment. Do not put it in command arguments or reports.

## Layout

Find scanner settings in root `sonar-project.properties`.
Use `tools/sonar/assert_no_new_issues.py` for the additional new-code issue check.
The helper selects a PR or branch and queries all result pages.

## New-issue gate

1. Inspect the **SonarCloud quality gate** job for the candidate revision.
2. Confirm the scanner completed with `-Dsonar.qualitygate.wait=true`.
3. Inspect the subsequent `assert_no_new_issues.py` result.
4. Fix each open new-code issue, then rerun the job through the normal PR workflow.

The helper reads `SONAR_TOKEN` from the environment for HTTP Basic authentication.
It sends the configured project and organization keys.
It selects explicit scope first, then the PR event, then the branch environment.
It fails when the token is absent, lookup fails, or open new-code issues remain.

Issue failures include severity, type, rule, location, and message.
API failures can include a bounded response-body excerpt.
Review diagnostics before sharing them. Do not assume every failure contains only issue metadata.

Use [platform gates](../../docs/testing/platform-pr-gates.md) for repository check policy.
