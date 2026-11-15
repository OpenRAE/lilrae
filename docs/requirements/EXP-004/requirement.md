---
id: EXP-004
title: "Provider-Neutral Participant and Resource Usage Metering"
status: DRAFT
type: FUNCTIONAL
priority: WONT
wave: 3
created_at: 2026-03-24T02:42:00.083510Z
updated_at: 2026-10-05T07:51:12.874346Z
---

# EXP-004: Provider-Neutral Participant and Resource Usage Metering

This Reference preserves the recorded requirement contract.
The front matter states its lifecycle status; this editorial notice does not change that status.
An ACTIVE contract is not a historical implementation or qualification result.
The statement, rationale, identifiers, and traceability below keep their recorded meaning.
The original file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/requirements/EXP-004/requirement.md).


## Statement

APTL shall capture standardized participant/runtime usage and budget events exposed through ACES contracts, together with apparatus resource observations such as elapsed time, CPU, memory, storage, and network volume where supported. Events shall retain component, participant, episode, action, run, clock, and source provenance and support per-run aggregation without discarding raw records. Optional monetary estimates shall reference an external versioned price catalog. APTL shall not authenticate directly to LLM providers, implement provider SDK adapters, infer missing token usage, or capture prompt content by default.

## Rationale

WITHDRAWN 2026-10-05: No consumer needs participant usage metering now. See GitHub issue #440. --- Original rationale: Resource and participant usage are relevant apparatus observations, but provider-specific LLM metering belongs at the participant implementation boundary. Consuming standardized events keeps APTL extensible and prevents a second agent runtime.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `#440` (EXP-004: Provider-neutral participant and resource usage metering)
