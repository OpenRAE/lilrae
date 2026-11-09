---
id: OBS-002
title: "Experiment Correlation Identity and Clock Context"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-03-21T07:50:36.167211Z
updated_at: 2026-07-20T05:59:40.442552Z
---

# OBS-002: Experiment Correlation Identity and Clock Context

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/OBS-002/requirement.md).


## Statement

APTL shall assign and preserve stable experiment-spec, task, condition, planned-trial, attempt/run, participant episode, action, capture, and evidence identifiers across its control, observability, and archive surfaces. It shall record clock sources, synchronization status, offset/uncertainty, and timestamp domains for each evidence source. Correlation metadata may be propagated into range components only through supported non-secret channels and with observer effects disclosed; causal links shall be based on explicit identifiers or declared evidence rules rather than timestamp proximity alone.

## Rationale

Reliable action-to-observation linkage requires both identity and clock evidence. Timestamp-only correlation overstates causality, while undisclosed instrumentation can alter the experiment being measured.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#447` (OBS-002: Experiment correlation identity and clock context)
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/models.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/clock.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/identity.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/rules.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/_assemble.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/_extract.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/builder.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/correlation/persistence.py`
- IMPLEMENTS → CODE_FILE `src/aptl/core/lab.py`
- IMPLEMENTS → DOCUMENTATION `docs/architecture/obs-002-correlation-identity-clock-preflight.md`
- TESTS → TEST `tests/test_correlation_builder.py`
- TESTS → TEST `tests/test_correlation_clock.py`
- TESTS → TEST `tests/test_correlation_identity.py`
- TESTS → TEST `tests/test_correlation_models.py`
- TESTS → TEST `tests/test_correlation_persistence.py`
- IMPLEMENTS → GITHUB_ISSUE `447`
