# ADR-045: Ephemeral Lifecycle Policy Enforcement

## Status

accepted

## Date

2026-06-28

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [deployment guide](../deployment.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

DEP-003 asks the platform to support "automated provisioning and teardown of
complete range instances on demand, with defined lifecycle policies (TTL-based
auto-teardown, idle detection, scheduled provisioning)."

The on-demand half already exists. RNG-001 owns the destructive clean-boot seam
through `orchestrate_lab_start()`, `stop_lab()`, and `clean_boot_lab()` in
`src/aptl/core/lab.py`. DEP-003 adds decisions about when to invoke lifecycle operations. TTL or inactivity can trigger teardown, and a schedule can request provisioning.

The [preflight](../architecture/dep-003-ephemeral-lifecycle-preflight.md) places policy above lab operations. A range instance is the configured project. Narrow state and one execution owner prevent duplicate destructive work.

The open question the preflight leaves to this decision is the **process model**
that drives enforcement. The pure policy evaluation (compare timestamps against a
TTL, an idle timeout, and a schedule) is identical regardless of how it runs;
only the surrounding process differs:

1. A long-running daemon that owns a poll loop and a lockfile as its primary
   artifact.
2. A background task inside the API server lifespan, which enforces only while
   that server runs.
3. A single-shot tick that the operator schedules with an external timer.

## Decision

APTL enforces lifecycle policy with a **single-shot, idempotent tick**:
`aptl lab enforce` performs exactly one evaluate-and-act cycle and exits. The
operator owns cadence through a systemd timer or a cron entry. `aptl lab
monitor` is a thin loop over the same tick for hosts without an external
scheduler.

The decision has four parts:

- **No daemon and no API coupling.** Option 1 makes a long-lived process and its
  lock the main artifact for what is a few timestamp comparisons. Option 2 stops
  enforcing the moment the API server stops, which silently defeats TTL
  teardown—the property operators most depend on for cost control. A
  single-shot tick keeps the always-on concern where the host already solves it
  (the timer) and keeps the codebase to pure evaluation plus a thin shell.
- **The lab start path is unchanged.** Enforcement imports `lab_status()`,
  `stop_lab()`, and `clean_boot_lab()`; it adds no step to `_LAB_START_STEPS`.
  Each tick compares recorded provisioning time with observed running state. Scheduled and manually started ranges therefore use the same aging rule.
  TTL begins at the first running observation, not the exact start time. The uncertainty is at most one tick interval for minute-to-hour teardown decisions.
- **Idle uses capture recency.** The idle signal is the most recent evidence
  written under the active run directory (`resolve_active_run_dir`), falling back
  to provisioning time when no scenario is active. Capture recency is a narrow
  control-plane activity marker that needs no new heartbeat wiring across the MCP
  servers.
- **One owner, narrow state.** A `flock` on `.aptl/lifecycle/.lock` serializes
  ticks, so a manual `enforce` and a running `monitor` cannot act at once. State
  lives in `.aptl/lifecycle/state.json` at mode `0600` and holds only
  timestamps, the last action and result, a redacted error label, and the
  per-day fired-schedule markers. Every value passes through `redact()` at the
  persist boundary (ADR-029).

`LabLifecyclePolicyConfig` in `aptl.json` defines strict policy under ADR-025. It bounds positive TTL and idle minutes, volume-removal choice, and UTC `HH:MM` schedules. Schedules can select weekdays and a scenario ID. `aptl lab policy show` renders the resolved policy and current
state.

## Consequences

**Positive**

- The always-on concern is one line of operator configuration, not a process to
  supervise. The tick is trivially testable: the pure evaluators take timestamps
  and return decisions with no clock, Docker, or filesystem.
- TTL teardown keeps working whether or not the API server or web UI runs.
- Reusing the RNG-001 lifecycle functions and the ADR-030 result envelope means
  no second teardown path and no new error hierarchy.

**Negative / risks**

- Enforcement only happens when the operator's timer fires. A host with no timer
  and no `monitor` running enforces nothing—the feature is opt-in by design,
  but operators must wire the cadence.
- TTL and idle resolve at tick granularity, so a short interval is needed for
  tight timeouts.

**Out of scope**

- REST policy endpoints, multiple concurrent named ranges, and cron-grammar
  schedules (daily plus weekday only). A future concurrent-instance design must
  parameterize the range identity and state root, as the preflight notes.
