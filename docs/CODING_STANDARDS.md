# Coding Standards

## Issue Delivery

**One issue = one PR.** Open an issue with explicit acceptance criteria before
opening its delivery PR. The PR must address every acceptance criterion of that
issue, including the required code, documentation, and tests.

Do not split one issue across multiple PRs. When a delivery PR already exists,
extend it and consolidate any duplicate partial work into that PR.

If an issue is too large, create smaller linked issues with explicit acceptance
criteria. Each smaller issue gets one complete PR. The parent records those
links and remains open until its acceptance criteria are satisfied through the
child issues.

The PR description must map each acceptance criterion to the resulting change
and its verification. Passing checks alone do not establish that the issue's
scope is complete.

## Architecture And Code Conventions

[ADR-064](adrs/adr-064-layered-architecture-and-code-conventions.md) defines
the layers, the import direction, and the module, pattern, typing, reuse, and
idiom rules. Apply it to all new and changed Python code.

`tools/check_architecture.py` checks the code that `[tool.lilrae.architecture]`
in `pyproject.toml` enrolls. CI runs the check in the **Pre-commit hooks** job.

When an issue completes the refactor of a package or a module:

1. Add the package or the module to `enrolled`.
2. Update the layer map when the issue moves or adds code.
3. Run `uv run --frozen --only-group ci python tools/check_architecture.py`.
4. Fix each finding in the code. Do not change the layer map to hide a finding.

## Go Code

[ADR-065](adrs/adr-065-go-implementation-and-engineering-standards.md) defines
the architecture, the architecture model, the design step, the style, and the
gates of the Go implementation. Apply it to all Go code. ADR-064 stays in force
for the Python code until Go port 31 removes that code.

Before you write code, record the design and run the design check. The tools
enforce each style rule that a tool can check. Review checks the rules in this
list:

1. A name is clear and in proportion to its scope. It does not repeat its
   package name, and a getter has no `Get` prefix.
2. A package has one responsibility. Split a package by responsibility, not by
   size.
3. An interface belongs to the package that uses it. Add an interface only for
   a second implementation or a test double that a test needs now.
4. An error message adds information that the caller does not have. A function
   returns an error or handles it. It does not log the error and also return
   it.
5. Each goroutine has a clear owner and end. Prefer synchronous functions, and
   let the caller add concurrency.
6. Use the least mechanism that does the job. Do not add generality, options,
   or reflection that no caller needs. Use the standard library or a selected
   module before custom code.
7. A doc comment states behavior and contract, not implementation steps. A
   public API package has examples.
8. A test checks behavior through the API of its package. A failure message
   gives the input, the result, and the expected result. Do not export a name
   only for a test.
9. The zero value of a type is useful where that is possible. Do not use a
   pointer to an interface.
10. External output matches its conformance cases. A port adds no behavior.

## Implementation And Verification

Reuse existing libraries, configuration, validators, and runtime boundaries.
Keep changes small and readable. Update documentation with changed behavior.
Select verification by behavior and risk; adequate existing tests are sufficient.
Remove redundant or obsolete tests. Test counts and coverage percentages do not
justify duplication. Preserve secret handling and project ownership checks.

Follow the [contribution guide](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md)
for targeted local checks and staged hygiene. CI/CD owns full suites, coverage,
prose, builds, and clean lab lifecycle qualification.
