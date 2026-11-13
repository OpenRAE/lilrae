# Contribute to LilRAE

Use this guide to deliver a complete change through one pull request.

## Before Opening a Pull Request

1. Open an issue with explicit acceptance criteria, including documentation and test changes.
2. Check for an existing delivery PR. Extend it instead of opening another PR for the same issue.
3. Deliver all acceptance criteria in one PR, including code, documentation, and verification.
4. If the issue is too large, create smaller linked issues with explicit acceptance criteria.
5. Give each smaller issue one complete PR. Keep the parent open until its criteria are satisfied.
6. Keep unrelated changes in separate PRs.
7. Base the PR on `dev`. Use `main` only for the documented release process.
8. Get maintainer acceptance before adding public red-team capability enhancements.

## Development Setup

Use Python 3.14, Docker with Compose, and [pre-commit](https://pre-commit.com/).
For MCP or web work, also install the supported [Node.js toolchain](docs/getting-started/host-requirements.md).
Keep lab execution on CI or an explicitly approved, isolated VM.

Set up the source checkout:

```shell
git clone https://github.com/OpenRAE/lilrae.git
cd lilrae
python3.14 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

For agent integration work, build the MCP artifacts:

```shell
./mcp/build-all-mcps.sh
```

For web work, install the frontend dependencies:

```shell
cd web
npm ci
```

## Making Changes

1. Fork the repository and create a branch from `dev`.
2. Make the smallest change that satisfies all acceptance criteria.
3. Select verification for the changed behavior and risk. Reuse adequate existing tests.
4. Add tests for uncovered behavior. Remove redundant or obsolete tests.
5. Update affected scenarios, schemas, documentation, and examples.
6. Follow the [coding standards](docs/CODING_STANDARDS.md).
7. Run staged hygiene as described below.
8. Open or update the issue's single PR against `dev`.
9. Map each acceptance criterion to its change and verification in the PR description.
10. Use a [Conventional Commit](https://www.conventionalcommits.org/) title with one type and an optional scope.

## Verification

Stage only the intended files, then run local hygiene:

```shell
git add <files-you-intend-to-commit>
pre-commit run
```

Run behavior tests only in CI or an approved isolated VM.
Follow [Verify a change](docs/testing/index.md) for targeted commands and consumer selection.
CI owns full suites, coverage, whole-tree lint, dependency checks, and strict documentation builds.
Do not run `pre-commit run --all-files` or `.pre-commit-ci.yaml` on the workstation.

## Documentation changes

Select one reader purpose: Tutorial, How-to guide, Reference, or Explanation.
Verify changed claims against code and configuration.
Preserve facts, conditions, obligations, commands, identifiers, and useful URLs.

Use the existing shared `documentation` skill. Keep it outside repository version control.
Follow [Write documentation](docs/contributing-documentation.md) for setup, writing checks, and source records.
Record source paths, revision, checks, and corrected differences in the PR.

## Go code

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
  `.ground-control.yaml`. It sends other arguments to pytest, which runs
  first. A pytest plugin stops the run unless each test path that pytest
  reads names a test file.
- The `go-format` pre-commit hook checks the staged Go files with the gofmt of
  the pinned toolchain.
- `bash tools/ci/go-gates.sh lint` runs gofmt, go vet, `go mod tidy -diff`,
  `go fix -diff`, and golangci-lint over each first-party module.
- `bash tools/ci/go-gates.sh fuzz 30s` runs each fuzz test for 30 seconds.
- `LILRAE_CONFORMANCE_BINARY="$PWD/.venv/bin/lilrae" go test -C conformance ./...`
  runs the conformance suite against an installed binary. The suite is a Go
  module of its own. The
  [inventory](docs/reference/conformance-inventory.md) lists its cases.
- A regression test carries the line `regression: #<issue>` in the doc comment
  of its test function. CI replays it on the base revision, where it must fail.
- Do not run the mutation, vulnerability, or full test gates locally. CI runs
  them.

## Safety Boundaries

Keep contributions within authorized lab use.
Do not include real credentials, production secrets, or private target data.
Include instructions only for systems you own or have permission to test.

Existing test credentials are lab fixtures.
Use dummy credentials unless the design explicitly generates or renders them at runtime.

## Host Privilege Escalation

Do not add silent host privilege escalation, `sudo -n`, or passwordless-sudo assumptions.
Before an elevated host action, request explicit consent.
Alternatively, stop and print the exact command for the user to run.
Scenario containers may model sudo behavior as lab content. That permission does not apply to the operator host.

## Changelog

Do not hand-edit `CHANGELOG.md` or release versions.
Follow [Releasing](docs/releasing.md) for the release process and title rules.

## Security Reports

Report vulnerabilities privately through [SECURITY.md](SECURITY.md).
Do not put details in public issues, PRs, or discussions.

## Community Expectations

Follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) in project spaces.
