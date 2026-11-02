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

## Implementation And Verification

Reuse existing libraries, configuration, validators, and runtime boundaries.
Keep changes small and readable. Update documentation with changed behavior.
Select verification by behavior and risk; adequate existing tests are sufficient.
Remove redundant or obsolete tests. Test counts and coverage percentages do not
justify duplication. Preserve secret handling and project ownership checks.

Follow the [contribution guide](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md)
for targeted local checks and staged hygiene. CI/CD owns full suites, coverage,
prose, builds, and clean lab lifecycle qualification.
