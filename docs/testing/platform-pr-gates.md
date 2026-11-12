# Platform pull-request gates

This Reference describes the existing platform checks.
Use [Verify a change](index.md) to select verification.
[CI verification](../architecture/ci-verification.md) explains routing and budgets.

## Required contexts

`.github/branch-protection-baseline.json` records intended context names and merge settings for each branch.
Live GitHub branch settings are the enforcement authority.
Pull requests to `go-cutover` retain the same required contexts as `dev` during the Go port.

The `dev` merge queue tests the candidate merge group.
Every required producer runs on `merge_group`; failure prevents the merge.
[ADR-068](../adrs/adr-068-dev-merge-queue.md) records the decision.

## Dependency checks

The dependency job checks three generated Python exports: CLI/runtime, API/web, and CI/build.
Known Python findings fail the job.
High or critical production findings in web and MCP locks also fail it.
Lock, installation, and scanner failures fail the check.
ADR-026 defines temporary exceptions. No platform dependency exceptions are currently recorded.

## Artifact and configuration scans

Trivy filesystem, IaC, and image scans fail on:

- CRITICAL, HIGH, or MEDIUM vulnerabilities with an available fix.
- Secrets.
- IaC misconfigurations.

Each scan also records findings in GitHub code scanning, including vulnerabilities without fixes.
An alert remains open until a scan stops reporting it.
`.trivyignore.yaml` owns waivers and their exact Dockerfile scope and reasons.
OSV-scanner fails on any `uv.lock` finding.
The ADR-026 amendment for issue #1193 records this policy.

## Clean-install qualification

The clean-install job builds a wheel, installs it in an empty environment, and materializes a fresh project.
It starts the product-neutral scenario from the [owned lab fixture pack](lab-fixture-pack.md).
It checks native effects, stops the project with volumes, and proves project-scoped absence.
The [boot coverage reference](boot-realization-coverage.md) lists its exact claims and gaps.

`scripts/ci/assert_project_teardown.py` checks containers, networks, and volumes using the effective workspace project identity.
It also compares anonymous/dangling volumes and ephemeral helpers against a pre-start daemon baseline.
The comparison observes state; it deletes nothing.

These checks qualify the generic installed-wheel lifecycle on a GitHub-hosted Ubuntu runner with local Docker.
They do not qualify the full TechVault or LilRAE journey.
Issues #870, #685, #1214, #1219, and #1220 track broader qualification.
