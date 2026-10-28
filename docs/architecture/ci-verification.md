# CI verification

Issue #1468 replaces repeated verification with checks selected by changed inputs.
The target is five minutes for Python coverage and ten minutes for ordinary PR checks.
Runner queue time is reported separately.

## Components and contracts

The existing Checks workflow owns required status names.
A change selector reads the Git diff and emits bounded Boolean lane selections.
Unknown paths, workflow changes, missing diff bases, and manual or scheduled runs select all lanes.
Every required job checks selector success before it can report success.
An unselected job reports that no relevant input changed.
The image matrix also selects descendants when a parent or shared input changes.

Source changes select all coverage producers for the existing project-wide SonarCloud analysis.
Docs and image routing remain independent.
Linux runs the retained ordinary Python suite once with line coverage.
Coverage.py uses its Python 3.12 monitoring core.
The measured serial run exceeded the budget after pruning and shared setup.
Split the retained cases into three complementary pytest-split groups.
Each group uses four pytest-xdist workers and pytest-cov's supported worker combination.
Keep each file on one worker to preserve module fixtures and avoid shared module state.
Workers keep separate process environments and pytest temporary directories.
Read-only pack fixtures share declarations and realization results within each process.
Mutation tests copy their declaration fields; backends, stores, and runtime ownership stay separate.
The existing required Python check combines all groups' data before exporting coverage.
All groups and the concurrent fuzz/smoke qualification job must succeed.
The combiner checks that all expected data files exist and uses a read-only token.
The coverage comparison also checks the planner's measured lines with two workers.
macOS and Windows run portability checks instead of repeating Linux planning tests.
The installed-wheel boot retains its independent realization and teardown observations.
Periodic qualification runs retained integration checks and scans unchanged dependencies and images.
The periodic lane pulls the pinned Dashboard prerequisite from the production catalog before test collection.
A missing prerequisite fails preparation.
Live-lab checks require an explicit operator opt-in and credentials.

The planner builds authored field prefixes once per compatibility application.
Each requirement queries that operation's index.
The index preserves exact fields, descendants, collection entries, and explicit empty declarations.
It does not survive the operation or change scenario authority.

## Data flows and security

```text
Contributor changes [untrusted input]
  -> Git checkout and changed-path selector [read-only runner token]
  -> lane selections [job outputs]
  -> existing test, build, scan, and artifact jobs [isolated hosted runners]
  -> coverage and diagnostic artifacts [existing Actions storage]
  -> existing SonarCloud analysis and required GitHub statuses

Scenario declarations [operator-authored input]
  -> parser explicitness map [existing semantic authority]
  -> operation-local prefix index [derived memory only]
  -> requirement delegation and evidence decisions [existing planner boundary]
```

Changed paths are data, never shell commands.
Routing failures must fail existing required jobs rather than skip them successfully.
Untrusted PRs receive no new permissions or services.
Dependency caches hold downloads, not installed executable state or lab credentials.
Existing hash pins and vulnerability thresholds remain active.
Test collection reads no lab environment file and provisions no API key.
Superseded PR cancellation uses a PR-specific group; release and branch validation have separate groups.
Cleanup steps retain their unconditional execution conditions.

## Verification policy

Evidence follows changed behavior and risk.
Existing tests can supply sufficient evidence without a new test for each edit.
Remove duplicate assignments, obsolete source-text checks, and repeated scenario setup.
Keep distinct behavior, serialization, rejection, and product-boundary checks.
Test count and coverage percentages are measurements, not reasons to preserve duplication.
Released-kit qualification belongs in the periodic integration lane when it exceeds the ordinary budget.

## References

- [Coverage.py 7.15.2 configuration](https://coverage.readthedocs.io/en/7.15.2/config.html): monitoring core and line coverage.
- [GitHub Actions concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency): PR cancellation groups.
- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use): untrusted inputs and least privilege.
- [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html): explicit test selection.
- [pytest-split](https://jerry-git.github.io/pytest-split/): complementary groups without repeating a full suite.
- [Coverage.py combination](https://coverage.readthedocs.io/en/7.15.2/commands/cmd_combine.html): merge measured data before XML export.

This document describes the verification architecture.
The issue plan owns implementation tasks and measured delivery results.
