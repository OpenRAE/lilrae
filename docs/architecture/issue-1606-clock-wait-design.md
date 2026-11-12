---
design: 1
issue: 1606
packages:
  - path: internal/clock
    component: clock
  - path: internal/wait
    component: deadline-wait
model_changes:
  - component:clock
  - component:deadline-wait
---

# Issue #1606: Clock and deadline waits design

This design adds two foundation packages of Go port 06
([#1557](issue-1557-go-foundation-design.md)): the host clock with the UTC
text forms, and the deadline wait. The front matter of this note is its design
record.

## Evidence

| Fact | Source |
| --- | --- |
| `correlation.clock.utc_now` writes `datetime.now(UTC).isoformat()` with `Z` in place of `+00:00`. `continuity._utc_now_iso` writes the same text with `+00:00`. | Source; `utc-now` and `continuity-now` vectors. |
| `isoformat` writes the seconds, then a six-digit microsecond fraction only when the microseconds are not zero. A `datetime` holds whole microseconds. | Python documentation of `datetime.isoformat`; vectors `trailing-zero-microseconds`, `whole-second`. |
| `core/services.py:wait_for_service` checks at once, treats a check that raises as not ready, never sleeps past the deadline, and checks once more at the deadline (#1002). Its progress messages are a caller concern. | Source and its tests. |
| `testing/synctest` runs code in a bubble with a fake clock, so a test of a wait needs no injected clock. | Go 1.25 release notes; ADR-070. |

## Decisions

1. **The clock is a concrete type.** ADR-070 puts each interface at its
   consumer. `clock.System` reads the host clock and returns UTC; a consumer
   that needs a fake clock defines `interface{ Now() time.Time }`, and
   `System` satisfies it.
2. **One function for each text form.** `clock.ISO` writes the
   `continuity-now` form and `clock.ISOZ` writes the `utc-now` form. Both
   drop the nanoseconds below a microsecond, as a Python `datetime` does, and
   write the fraction only when it is not zero. The workflow timestamp rule
   (`workflow-next-timestamp`) stays with its owner.
3. **One wait loop.** `wait.Until` calls a probe at once and then once each
   interval, never sleeps past the deadline, and calls the probe once more at
   the deadline. It returns the time that the wait took, and `ErrTimeout` or
   the error of the context when the probe did not report ready. A caller
   acts on a timeout, so `ErrTimeout` is a sentinel.
4. **The probe gets the remaining budget.** The wait derives one probe
   context with the wait deadline, capped by any earlier caller deadline.
   Every attempt gets that same deadline, so a retry cannot restart the
   budget. A blocking probe uses its context for cancellation and derives
   its remaining time from the context deadline. The caller's context still
   controls cancellation of the wait. The final probe is invoked at the wait
   deadline even though its remaining budget is zero; it can report an
   immediately available result. Cancellation is cooperative: a probe that
   ignores its context can finish after the deadline. The wait starts no
   additional goroutine to abandon such a probe.
5. **Tests.** The clock tests read the `utc-now` and `continuity-now`
   vectors. The wait tests run in `testing/synctest`, so the fake clock
   proves the call times, the last call at the deadline, and the
   cancellation.

## Data flows and threat model

```text
host clock -> clock.System.Now -> caller -> clock.ISO / clock.ISOZ -> record
caller probe <- wait.Until (timer, bounded probe context) -> elapsed, ErrTimeout, or context error
```

| Threat | Mitigation |
| --- | --- |
| A stored timestamp changes its text, so a record no longer matches. | The vectors fix each text form. |
| A blocking probe receives no budget, or a retry restarts it. | Every probe receives the same bounded context deadline and uses its remaining budget for blocking operations. The wait never sleeps past the deadline and stops on caller cancellation. |
| A busy loop uses the CPU. | `Until` rejects an interval that is not positive. |
