# CI performance

Issue #1468 sets two budgets, excluding runner queue time:

- Ordinary Python tests and line coverage: five minutes.
- Required PR checks: ten minutes.

## Baseline

The investigation sampled 35 Checks runs and found 13 successful runs.
Their median elapsed time was 52.4 minutes, with a 40.8–71.4 minute range.
[Run 40564600048](https://github.com/OpenRAE/lilrae/actions/runs/40564600048)
ran 7,261 passing ordinary tests, 63 skipped tests, and 260 deselected tests.
Its Python coverage job took 47.7 minutes.
The duplicate Ubuntu suite took 31.7 minutes, and macOS took 20.3 minutes.
Those jobs ran in parallel; their durations are not additive elapsed time.

## Removed and consolidated work

The first pruning pass removes 122 test functions:

| Category | Removed functions | Reason and retained evidence |
| --- | ---: | --- |
| Legacy smoke and full-range modules | 78 | Fixed container identities duplicate scenario-owned live verification. Use `lilrae lab validate-live` and distinct native active-response/continuity probes. |
| Constructor/default/type assertions | 32 | Assignments repeat model declarations. Keep serialization, validation, lifecycle, scoring, and correlation behavior. |
| Duplicate and workflow-text assertions | 4 | Remove repeated manifest assertions, an exact timeout value, and retired workflow details. Keep actual audit failure and cleanup checks. |
| Repeated complete-scenario account checks | 8 | Keep the composed released gate. Six small rejection cases replace six full-pack cases. |

The removed attack-model file contained two of the constructor checks.
The counts describe deleted functions, not a net execution-count reduction.
New regressions and parametrized replacements are counted separately by pytest.
The paper checks share one parsed plan.
Six modules share one read-only released realization per test session.
Wheel verification shares the build but keeps separate clean install environments.
No runtime manager or live lab is shared between tests.

Source changes select all current coverage reports for the project-wide analyzer.
Linux now executes the ordinary suite once.
macOS and Windows execute focused portability checks.
Retained integration tests run through existing required boundaries or periodic qualification.
Live-lab tests require explicit marker selection and their documented environment opt-in.
Ordinary test collection neither reads lab credentials nor provisions an API key.

## Measurements

Hosted comparison runs must use the same revision and runner class.
Record the coverage core, worker count, cache state, selected counts, and slowest calls/setup.
Keep elapsed required-check time separate from summed runner minutes and queue delay.
Python and periodic integration jobs retain JUnit results and print durations.
The toolchain-change check compares executed lines under `sysmon` and `ctrace`.
The current configuration has no parallel Python workers.
First remove repeated setup and measure before adding worker isolation and coverage machinery.

Three successful hosted comparisons are required before claiming the budgets are met.
The issue and delivery PR hold those run links and results.
Local focused checks alone do not establish whole-suite performance.

## Qualification ownership

The ordinary budget does not expand to plan every released kit.
Issue #1099 must use representative PR coverage and periodic released-kit qualification.
Issue #1321's marker gaps are addressed for the retained tests.
The periodic/manual/release-tag lane selects all retained integration tests without a live lab.
Its local image prerequisites come from the existing workflow image matrix.
The pinned Dashboard image is pulled from the production catalog before collection.
Weekly scans also reassess unchanged images and dependency locks against current advisories.
These qualification costs are reported separately from ordinary PR feedback.

See [CI verification](../architecture/ci-verification.md) for routing and security boundaries.
