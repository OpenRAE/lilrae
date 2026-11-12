# ADR-015: Declarative Experiment Objectives in the SDL

## Status

accepted

## Date

2026-03-29

## Applicability

This record explains declarative objective semantics in the earlier local SDL.
[ADR-035](adr-035-raes-sdl-adoption.md) later assigns the portable language to RAES.
The [SDL guide](../sdl/index.md) links the current owner instead of defining another local schema.

## Context

[ADR-014](adr-014-scenario-description-language.md) established a deployment-independent SDL from Open Cyber Range and other existing precedents.

The first implementation kept the OCR scoring pipeline: `conditions -> metrics -> evaluations -> TLOs -> goals`. It left APTL objectives in runtime because the earlier implementation mixed:

- experiment meaning
- backend-specific validation probes
- scenario engine behavior

The separation removed runtime coupling but left no explicit objective model. Authors still needed to state actors, targets, exercise windows, and success semantics.

Research and precedent review pointed in the same direction:

- **OCR** keeps assessment semantics in the specification layer, not only in runtime.
- **CACAO** keeps agent/target/workflow intent in the playbook specification while leaving execution adapters external.
- **CybORG** places agent-facing configuration such as actions, initial knowledge, and reward-calculator choice in scenario definitions.

The design question was therefore not whether to restore the legacy APTL runtime `objectives` block, but whether the SDL itself should carry declarative experiment semantics.

## Decision

Add a first-class `objectives` section to the SDL for declarative experiment semantics.

Each objective may declare:

- exactly one actor: `agent` or `entity`
- optional `actions`
- optional `targets`
- required `success` criteria referencing declared `conditions`, `metrics`, `evaluations`, `tlos`, or `goals`
- optional `window` constraints over `stories`, `scripts`, and `events`
- optional `depends_on` links forming an acyclic ordering relation between objectives

This section is intentionally declarative. It expresses:

- who is acting
- what they are trying to affect
- when the objective matters
- how success should be interpreted

It does **not** encode backend-specific validation probes such as Wazuh queries, command execution, file checks, polling loops, or session orchestration. Those remain runtime concerns and continue to live outside the SDL.

### Relationship to ADR-014

This ADR adds declarative objectives to ADR-014's language boundary. It keeps specification separate from deployment and runtime mechanics.

## Consequences

### Positive

- The SDL now captures experiment meaning more completely, not just topology and scoring fragments.
- Agent definitions, orchestration, scoring, and objectives can be authored and reviewed together in one specification surface.
- The runtime boundary is cleaner: the SDL defines semantics, while runtime adapters define how those semantics are checked.
- Objective dependencies can be validated structurally as an acyclic ordering graph.

### Negative

- The SDL surface area grows, increasing documentation and test burden.
- The distinction between declarative objective semantics and runtime evaluation mechanics must remain explicit to avoid drift back into engine-coupled schema design.
- Real-world stress scenarios need to keep pace so the section is exercised beyond unit tests.

### Risks

- If future runtimes need loops, switch/case routing, or exception branches, the current workflow model may need further expansion.
- Authors may infer stronger execution semantics than currently implemented unless `depends_on`, `window`, workflow, and success rules are documented precisely.
- Divergence from OCR/CACAO details remains possible if future changes borrow terminology without preserving the underlying conceptual boundary.
