---
id: SYS-009
title: "Code Quality and Security Practices"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-20T06:05:43.487932Z
updated_at: 2026-03-20T06:18:11.648456Z
---

# SYS-009: Code Quality and Security Practices

## Statement

The system shall maintain continuous code quality analysis, automated test coverage, and secure credential handling across all of its code.

## Rationale

A security training lab that has poor code quality or leaks credentials undermines its own credibility. Continuous quality gates prevent regression and provide confidence in the platform's reliability.

## Traceability

- IMPLEMENTS → CONFIG `eslint.config.js` (Root ESLint flat config: per-function TypeScript complexity gate (issue #286))
- IMPLEMENTS → CONFIG `.pre-commit-ci.yaml` (Python and TypeScript complexity gates and the ADR-064 architecture check run by CI)
- IMPLEMENTS → CONFIG `.github/workflows/checks.yml` (Continuous Python and TypeScript tests, pre-commit, and security checks)
- DOCUMENTS → ADR `ADR-010` (ADR-010 SonarCloud quality: TypeScript complexity gate section + backlog)
- IMPLEMENTS → CODE `tools/check_architecture.py` (ADR-064 layer, cycle, private-import, Typer, and Ruff checks for enrolled code)
- IMPLEMENTS → CONFIG `pyproject.toml` (ADR-064 layer map, enrolled scope, and Ruff rules in [tool.lilrae.architecture])
- TESTS → TEST `tests/test_check_architecture.py` (Activation and rejection of the ADR-064 checks on fixture trees)
- TESTS → TEST `tests/test_sonar_project_properties.py` (SonarCloud ignore entries name existing files)
- DOCUMENTS → ADR `ADR-064` (ADR-064 layered architecture and code conventions)
- DOCUMENTS → ADR `ADR-065` (ADR-065 Go implementation, architecture model, and engineering standards)
- IMPLEMENTS → GITHUB_ISSUE `1510` (Record the target architecture and code conventions for the code quality refactor)
