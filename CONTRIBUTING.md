# Contributing to APTL

APTL is an active purple-team lab and autonomous cyber-operations research
project. Contributions are useful when they make the lab safer, more
reproducible, easier to operate, easier to test, or more precise for scenario
authors and agent integrations.

## Before Opening a Pull Request

- Open an issue before making a pull request, including documentation and test
  changes. Give the issue explicit acceptance criteria.
- **One issue = one PR.** The delivery PR must address every acceptance
  criterion of its issue. Do not split one issue across multiple PRs, including
  separate code, documentation, and test PRs. Extend an existing delivery PR
  instead of opening another PR for the same issue.
- If an issue is too large, create smaller linked issues with explicit
  acceptance criteria. Each smaller issue gets one complete PR; the parent
  tracks their delivery and remains open until its criteria are satisfied.
- Keep unrelated changes in separate pull requests.
- Base pull requests on `dev`, not `main`. `main` is the stable release line;
  `dev` is the integration branch.
- Do not add red-team capability enhancements to the public repository unless
  the maintainer has explicitly accepted the scope first.

## Development Setup

Prerequisites:

- Python 3.14 or newer
- Docker and Docker Compose
- Node.js and npm for MCP server and web UI work
- [pre-commit](https://pre-commit.com/)

Set up the Python control plane:

```shell
git clone https://github.com/OpenRAE/lilrae.git
cd lilrae
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Build the MCP servers when working on agent integrations:

```shell
./mcp/build-all-mcps.sh
```

Install the web UI dependencies when working under `web/`:

```shell
cd web
npm install
```

## Making Changes

1. Fork the repository and create a branch from `dev`.
2. Make the smallest coherent change that satisfies all of the issue's
   acceptance criteria.
3. Verify changed behavior and risk. Reuse adequate existing tests; add tests
   only for uncovered behavior. Remove redundant or obsolete cases.
4. Update scenarios, schemas, documentation, or examples when the public
   surface changes.
5. Give the PR a [Conventional Commit](https://www.conventionalcommits.org)
   title (`feat:`, `fix:`, etc.); release-please derives the changelog and
   version from it. Do not edit `CHANGELOG.md`.
6. Run the relevant checks locally.
7. Open the issue's single pull request against `dev`, or update its existing
   PR. Describe what changed, why, and how each acceptance criterion was
   verified. Follow the [coding standards](docs/CODING_STANDARDS.md).

## Verification

The local hygiene and secret check operates on staged files:

```shell
git add <files-you-intend-to-commit>
pre-commit run
```

Local commit hooks run secret detection and fast file hygiene only. Full Python,
MCP and web suites, dependency-lock freshness, complexity and prose checks run in
CI/CD. Run only the exact tests relevant to a change while developing. Do not
run bare `pytest`, package-wide `npm test`, `pre-commit run --all-files`, or the
whole-tree `.pre-commit-ci.yaml` configuration locally.

Examples of targeted checks:

```shell
pytest tests/test_specific_behavior.py
pytest -m fuzz tests/test_specific_fuzz_behavior.py
cd mcp/aptl-mcp-common && npx vitest run tests/specific.test.ts
cd mcp/mcp-red && npx vitest run tests/specific.test.ts
cd web && npx vitest run tests/specific.test.ts
```

When test files changed, `bash tools/run-targeted-tests.sh` derives those
targets from the branch and worktree. You can instead pass explicit Python or
Go test paths to the script. CI/CD remains the authority for full suites, coverage,
whole-tree lint, dependency checks, and prose/build gates.

### Go code

Milestone 44 adds the Go implementation on the `go-cutover` branch. Its pull
requests target `go-cutover`, not `dev`
([CI verification](docs/architecture/ci-verification.md#go-cutover-branch)).
[ADR-065](docs/adrs/adr-065-go-implementation-and-engineering-standards.md)
gives the rules.

- Install the Go release that `go.mod` names. With `GOTOOLCHAIN=auto`, the go
  command downloads it.
- `bash tools/run-targeted-tests.sh path/to/x_test.go` runs the whole package of
  each named test file with `go test -race -shuffle=on`. Without arguments, it
  runs the packages of the changed test files. It reads the base branch from
  `.ground-control.yaml`. It sends other arguments to pytest, and they need a
  Python test path.
- The `go-format` pre-commit hook checks the staged Go files with the gofmt of
  the pinned toolchain.
- `bash tools/ci/go-gates.sh lint` runs gofmt, go vet, `go mod tidy -diff`,
  `go fix -diff`, and golangci-lint over each first-party module.
- A regression test carries the line `regression: #<issue>` in the doc comment
  of its test function. CI replays it on the base revision, where it must fail.
- Do not run the mutation, vulnerability, or full test gates locally. CI runs
  them.

When changing files under `mcp/aptl-mcp-common`, run targeted common and
dependent-server tests while iterating. CI/CD rebuilds and tests every dependent
MCP because they consume the local package.

CI runs the ordinary Python suite once on Linux with line coverage.
macOS and Windows run focused portability tests and CLI smoke commands.
Changed inputs select relevant jobs; unknown paths select all checks.
Weekly, manual, and release-tag qualification select the full retained checks.
Superseded PR jobs are cancelled, while an active lab boot completes teardown.
Full lab startup on macOS and Windows remains an operator qualification.
See [CI verification](docs/architecture/ci-verification.md) for routing and budgets.

When changing `docker-compose.yml`, container Dockerfiles, or files under
`config/`, run only focused contract tests locally. CI/CD owns the clean lab
stop/start validation so local verification does not expand into a full system
run.

## Safety Boundaries

APTL intentionally runs vulnerable services and gives agents access to
penetration-testing tools. Keep contributions bounded to authorized lab use.
Do not include real credentials, production secrets, private target data, or
instructions for using the project against systems you do not own or have
permission to test.

The repository contains intentional test credentials for lab functionality.
Those are not production secrets. New credentials should be dummy values unless
the design explicitly renders or generates them at runtime.

## Host Privilege Escalation

Host-side APTL code must not silently escalate privileges. Do not add `sudo -n`,
passwordless-sudo assumptions, or hidden sudo repair paths. If a host action
truly needs elevated privileges, either prompt for explicit consent before
running it or stop and print the exact command for the user to run. Scenario
containers may still model sudo behavior as lab content; that is separate from
operator host escalation.

## Changelog

Release notes and version bumps are generated by
[release-please](https://github.com/googleapis/release-please) from Conventional
Commit PR titles. Do not hand-edit `CHANGELOG.md`. See
[Releasing](docs/releasing.md).

## Security Reports

Do not open public issues for suspected security vulnerabilities. See
[SECURITY.md](SECURITY.md).

## Community Expectations

Participation in this project is covered by
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
