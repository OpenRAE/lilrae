---
id: DSL-009
title: "Simulated User Behavior Profiles in SDL"
status: DRAFT
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-03-31T02:56:37.902697Z
updated_at: 2026-10-11T00:00:00.000000Z
---

# DSL-009: Simulated User Behavior Profiles in SDL

## Statement

The APTL backend shall drive RAES-declared user-behavior profiles in a realized range. These profiles cover browsing, email, login schedules, file access, and other baseline traffic. They make the range generate realistic background activity alongside adversarial and defensive activity. The RAES SDL owns how authors declare the profiles. The backend runs the declared profiles against the lab.

## Rationale

The SDL currently has no first-class mechanism for user simulation. Injects model discrete narrative events, not continuous behavior. Green entities declare organizational identity but carry no behavioral specification. Without declarative user behavior, the full exercise model is incomplete: defenders cannot distinguish attack traffic from normal traffic unless the range generates realistic baselines, and that generation has no specification-layer anchor. CybORG Green agents are the closest precedent. Already noted in docs/sdl/limitations.md as a specification-layer gap. Tracked in GitHub as #242.

NOT DEPRECATED 2026-10-11: ADR-035 deprecates DSL-002 to DSL-009 as requirements on the retired in-tree DSL. This record stays DRAFT, not DEPRECATED, because its statement now covers how the APTL backend drives RAES-declared user-behavior profiles, not a LilRAE scenario DSL. Open issue #436 still tracks the realization work together with REP-004. On 2026-07-03 the issue moved profile authoring to RAES (rae#659, later folded into rae#216) and kept only the backend realization. No other record covers declared user activity: REP-004 covers only network traffic profiles, and its traceability already points at #436. See GitHub issue #436.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#436` (DSL-009: Simulated User Behavior Profiles in SDL)
