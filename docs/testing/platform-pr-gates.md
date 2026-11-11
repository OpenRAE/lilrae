# Platform pull-request gates

Pull requests to `dev` require these existing contexts:

- **Pre-commit hooks**
- **Python tests + coverage**
- **MCP TypeScript tests + coverage**
- **Dependency vulnerability scan**
- **Clean-install lab boot and teardown (DEP-008)**
- **Trivy filesystem scan**
- **Trivy IaC / config scan**
- **Trivy image scan**
- **OSV-scanner (uv.lock)**
- **RAES scenario validation gate**

Other established required quality and governance checks stay in the branch
rule. `.github/branch-protection-baseline.json` records the exact context
names. The live GitHub branch settings are the enforcement authority. While the
Go port is in progress, pull requests to `go-cutover` require the same contexts
as `dev`. See [CI verification](../architecture/ci-verification.md#go-cutover-branch).

Pull requests to `dev` merge through a merge queue. Each required context
also runs on the merge group. A failed context keeps the pull request from
merging. See [CI verification](../architecture/ci-verification.md#dev-merge-queue)
and [ADR-068](../adrs/adr-068-dev-merge-queue.md).

The dependency job fails on known Python findings in three generated exports:
CLI/runtime, API/web, and CI/build. It also fails on high or critical
production dependency findings in the web package lock and all MCP package
locks. It also fails when a lock, install, or scanner fails. ADR-026 records
the boundary and the format for a temporary platform exception. There are
currently no such exceptions.

The Trivy filesystem, IaC, and image scans fail on these findings:

- A CRITICAL, HIGH, or MEDIUM vulnerability that has an available fix.
- A secret.
- An IaC misconfiguration.

Each scan also records every finding in GitHub code scanning. This includes
vulnerabilities that have no upstream fix yet. An alert stays open until a scan
stops reporting it.

`.trivyignore.yaml` holds the only waivers. Each waiver is
scoped to exact Dockerfiles and gives its reason. OSV-scanner fails on any
`uv.lock` finding. The ADR-026 amendment for issue #1193 records the policy.

The clean-install job builds a wheel and installs it in an empty virtual
environment. It then materializes a fresh project. It starts only the
product-neutral `materialization-envelope.sdl.yaml` scenario from APTL's owned
[lab fixture pack](lab-fixture-pack.md). The job checks native effects in the
project's running container and stops the lab with volumes. It then proves
that the effective workspace project has no remaining containers, networks, or
volumes.

Anonymous volumes and ephemeral helper containers carry no project identity.
Thus the job also records what the daemon holds before the lab starts. It
fails when teardown leaves behind an anonymous volume or an ephemeral helper
container. That comparison only observes; it deletes nothing.

The scenario carries one causal realization chain. Thus none of those checks
can pass on a declaration alone. The chain has these links:

1. Inline content moves the SSH daemon off its package default port.
2. The declared service unit starts the daemon.
3. The declared listener binds the moved port.
4. An exact loopback host binding publishes that port.

`scripts/ci/assert_boot_realization.py` does these checks:

- It reads the placed bytes inside the container.
- It queries the service manager for the enabled, active, and result state of
  the unit.
- It observes the live listener from outside the trust boundary of the
  container.
- It requires the exact published-port tuple and no wider one.
- It opens a connection to that port.
- It parses the persisted workflow with the RAES execution-state contract.

`docs/testing/boot-realization-coverage.md` maps each concern that APTL's
realization envelope advertises to the tests that hold it. It also names the
concerns that this small boot deliberately does not claim.

These checks support the **generic installed-wheel materialization and lab
lifecycle profile on a GitHub-hosted Ubuntu runner with local Docker**. They do
not qualify the full TechVault or LilRAE journey. APTL #870 and #685, and
OpenRAE/lilrae #1214, #1219, and #1220 track those qualifications.
