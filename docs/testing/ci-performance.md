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

The pruning removes 125 test functions:

| Category | Removed functions | Reason and retained evidence |
| --- | ---: | --- |
| Legacy smoke and full-range modules | 78 | Fixed container identities duplicate scenario-owned live verification. Use `lilrae lab validate-live` and distinct native active-response/continuity probes. |
| Constructor/default/type assertions | 32 | Assignments repeat model declarations. Keep serialization, validation, lifecycle, scoring, and correlation behavior. |
| Duplicate and workflow-text assertions | 7 | Remove repeated manifest and catalog assertions, an exact timeout value, retired workflow details, a historical file-inventory equality check, and a distinct-profile check already proved by exact expected sets. Keep actual audit failure and cleanup checks. |
| Repeated complete-scenario account checks | 8 | Keep the composed released gate. Six small rejection cases replace six full-pack cases. |

The removed attack-model file contained two of the constructor checks.
The counts describe deleted functions, not a net execution-count reduction.
New regressions and parametrized replacements are counted separately by pytest.
The paper checks share one parsed plan.
Curated variants share each realization and one acquired catalog with explicit cleanup.
That focused local module fell from 87.11 seconds to 38.34 seconds.
It retains 16 cases; the removed case repeated the exact-profile assertions.
Released-pack readers share one read-only parsed scenario and realization per test process.
Cases that change runtime declarations copy those fields first.
Database cases parse their unchanged declarations once and keep separate backend doubles.
Startup unit cases stub source acquisition before their existing admission stub.
The credential-hydration case retains the real released source.
Content-owner checks materialize their two relevant services once.
API rejection cases use the small admitted fixture pack; the released list/detail checks remain.
Catalog projection and selection checks share one owned catalog with explicit cleanup.
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
The first hosted serial trial exceeded the ordinary budget.
The next trial uses four workers after pruning and shared setup.
Files stay on one worker; pytest-cov combines worker measurements.
The toolchain check compares the planner's executed lines against a two-worker run.
This trial must report worker count and runner minutes alongside elapsed time.

[The first four-worker trial](https://github.com/OpenRAE/lilrae/actions/runs/40627971905)
took 699.86 seconds for ordinary tests and coverage.
It selected 7,247 cases: 7,239 passed, four failed, and four skipped.
The target was not met; this failed run is diagnostic evidence only.
Its startup class consumed 457.70 summed case seconds across 51 cases.
Database cases consumed 218.52 seconds; two content-owner checks consumed 164.49 seconds.
These case durations overlap across workers and are not pipeline elapsed time.
The next revision removes their repeated setup and repairs the stale helper checks.

[The corrected four-worker run](https://github.com/OpenRAE/lilrae/actions/runs/40630625357)
selected 7,250 ordinary cases: 7,246 passed and four skipped.
Ordinary tests and coverage took 457 seconds; core/worker coverage comparisons also passed.
The five-minute target was not met.
The next trial uses two complementary groups, with four workers in each.
Fuzz, coverage comparisons, Docker readback, and CLI smoke run concurrently.
The required Python check waits for all three jobs and combines both groups' coverage.
Record their summed runner time; the groups do not repeat the whole suite.

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
