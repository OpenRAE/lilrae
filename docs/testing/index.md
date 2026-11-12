# Verify a change

Use this guide to select evidence for a change.
Run behavior tests only in CI or an explicitly approved, isolated VM.
Use the workstation for source review, static checks, Git, and staged hygiene.

## Select evidence

1. Identify the behavior and failure paths that changed.
2. Find existing tests of that boundary.
3. Reuse adequate tests. Add focused cases for uncovered behavior.
4. Remove redundant or obsolete cases.
5. For shared MCP changes, select common-library tests and affected consumer tests.
6. For Compose, Dockerfile, or `config/` changes, include focused contract tests.
7. Leave clean lab stop/start qualification to CI on a fresh machine.

[CI verification](../architecture/ci-verification.md) explains selection, portability, budgets, and lab qualification limits.
[Platform gates](platform-pr-gates.md) lists check contracts.

## Run targeted tests in an approved environment

For changed test files, use the existing selector:

```shell
bash tools/run-targeted-tests.sh
```

For explicit Python paths, pass those paths:

```shell
bash tools/run-targeted-tests.sh tests/test_documentation_checks.py tests/test_docs_user_journey.py
```

For a property test, select its marker and exact path:

```shell
bash tools/run-targeted-tests.sh -m fuzz tests/test_specific_fuzz_behavior.py
```

Replace the example path with an existing test for the changed boundary.
For Vitest, work in the affected package and select exact test paths:

```shell
cd mcp/aptl-mcp-common
npx vitest run tests/specific.test.ts
```

Use the same pattern for a dependent MCP server or `web/`.
Do not run bare `pytest` or package-wide `npm test` outside CI.
The selector refuses an empty changed-test selection; it does not select a full suite.

## Check staged files

Follow [Contributing](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md#verification) for staged hygiene.
Use [Write documentation](../contributing-documentation.md#run-writing-checks) for explicit-path prose checks.
CI owns full suites, coverage, whole-tree checks, dependency audits, and strict MkDocs builds.

## Qualify a release or boundary

- Follow [release candidate QA](smoke-test-plan.md) for both installation paths and human approval.
- Use the [lab fixture pack](lab-fixture-pack.md) for generic lab-machinery regressions.
- Follow [parser property-test guidance](property-based-parser-tests.md) for input-space checks.
- Consult the [boot coverage reference](boot-realization-coverage.md) for the small installed-wheel gate's limits.
