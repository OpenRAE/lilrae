---
id: DSL-010
title: "APTL ParticipantRuntime: live-action conformance for reference emulation backend"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-06-25T05:25:22.533709Z
updated_at: 2026-07-15T05:35:45.871777Z
---

# DSL-010: APTL ParticipantRuntime: live-action conformance for reference emulation backend

## Statement

The APTL backend shall realize the ACES participant/runtime action surface as a conformant emulation backend so it can serve as the ecosystem reference emulation backend fulfilling ACES requirement RUN-314. It shall (1) implement the aces_backend_protocols ParticipantRuntime protocol (initialize/reset/restart/terminate plus status/results/history) against realized infrastructure, returning standard aces_contracts DTOs; (2) promote its published backend manifest to a participant_runtime-capable conformance profile by adding the participant_runtime capability block and its required evidence contracts, passing aces conformance backend with no unsupported-capability-claim diagnostics; and (3) prove a real emulation-backed participant action by promoting the curated TechVault live-boot proof to a live-action proof that drives a meaningful participant action against realized containers and surfaces the result through the standard operation-status, runtime-snapshot, and realization-provenance contracts rather than only contract-surface or in-memory state.

## Rationale

Extends DSL-008. APTL on origin/main already realizes ACES SDL onto real Docker Compose infrastructure through the ACES runtime path and publishes the canonical backend-manifest-v2, snapshot/status, conformance, and realization-provenance contracts, but declares itself orchestration-evaluation only (no ParticipantRuntime) and its live proof stops at boot/readiness. ACES RUN-314 (aces5 #197) was reopened on a scope audit requiring proof of a real emulation-backed action surface. Closing this gap in APTL makes APTL the artifact RUN-314 traces to.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/backends/_raes_runtime_target.py` (Installed participant and shared-time components)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/_raes_participant_legacy.py` (Explicitly admitted legacy probe execution)
- TESTS → TEST `tests/test_raes_planning_compat.py` (Planning compatibility before participant admission)

- IMPLEMENTS → CODE_FILE `src/aptl/backends/lilrae_participant_execution.py` (Exact autonomous native bindings under RAES admission and settlement)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/_lilrae_participant_capabilities.py` (Installed autonomous capability declarations)
- TESTS → TEST `tests/test_lilrae_concurrent_participants.py` (Concurrent admission, peer isolation and terminal outcomes)
- TESTS → TEST `tests/test_lilrae_participant_cancellation.py` (Owned process cancellation and peer preservation)

- IMPLEMENTS → CODE_FILE `src/aptl/cli/lab.py` (aptl lab CLI surface for participant runtime)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/_live_gate_checks.py` (Live gate checks supporting participant-action conformance)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/curated_live_proof.py` (Curated live proof driver for participant runtime)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/participant_live_proof.py` (Participant live-action proof capture)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/range_snapshot_summary.py` (Range snapshot summary for participant runtime validation)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/techvault_gate.py` (TechVault static gate orchestrator (participant runtime))
- IMPLEMENTS → CODE_FILE `src/aptl/validation/techvault_live_gate.py` (TechVault live gate orchestrator (participant runtime))
- TESTS → TEST `tests/test_curated_live_proof.py` (Curated live proof driver tests)
- TESTS → TEST `tests/test_techvault_live_gate.py` (TechVault live gate tests: participant runtime)
- TESTS → TEST `tests/test_techvault_static_gate.py` (TechVault static gate tests: participant runtime)
- IMPLEMENTS → GITHUB_ISSUE `554` (DSL-010: APTL ParticipantRuntime: live-action conformance for reference emulation backend (RUN-314))
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_manifest.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_participant_actions.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_participant_runtime.py`
- TESTS → TEST `tests/test_raes_backend.py`
- IMPLEMENTS → DOCUMENTATION `docs/raes/dsl-010-participant-runtime-preflight.md`
- IMPLEMENTS → DOCUMENTATION `docs/raes/techvault-curated-live-validation-gate.md`
- IMPLEMENTS → DOCUMENTATION `docs/raes/techvault-curated-live-validation-gate/run-curated-live-proof.sh`
- IMPLEMENTS → DOCUMENTATION `docs/raes/techvault-curated-live-validation-gate/techvault-attacker-target/participant-action.json`
- IMPLEMENTS → DOCUMENTATION `docs/raes/techvault-curated-live-validation-gate/techvault-attacker-target/result.json`
- IMPLEMENTS → DOCUMENTATION `docs/raes/techvault-curated-live-validation-gate/techvault-attacker-target/snapshot.json`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/lilrae_participant_action_model.py` (Executable action invariants)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/lilrae_participant_tools.py` (Exact installed mapping and invocation admission)
- IMPLEMENTS → CODE_FILE `src/aptl/workbench/lilrae_tool_transport.py` (Bounded authenticated carrier)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/lilrae-tool-admission.ts` (Pre-handler dispatch and outcome receipt)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/server.ts` (Shared red and blue MCP enforcement)
- IMPLEMENTS → CODE_FILE `tools/check_lilrae_participant_architecture.py` (Executable dependency ownership check)
- IMPLEMENTS → DOCUMENTATION `docs/architecture/participant-action-enforcement.md` (Composition controls and qualification boundaries)
- IMPLEMENTS → DOCUMENTATION `docs/adrs/adr-063-executable-participant-action-boundaries.md` (Executable architecture decision)
- TESTS → TEST `tests/test_lilrae_participant_action_model.py` (Finite state exploration and negative controls)
- TESTS → TEST `tests/test_lilrae_participant_architecture.py` (Component dependency controls and mutations)
- TESTS → TEST `tests/test_lilrae_participant_tools.py` (Exact mapping, refusal, replay, and redaction)
- TESTS → TEST `tests/test_lilrae_tool_transport.py` (Local carrier failure and cleanup)
- TESTS → TEST `tests/test_lilrae_tool_model_fuzz.py` (Generated independent participant traces)
- TESTS → TEST `tests/test_lilrae_tool_composition.py` (Released unsupported composition refusals)
- TESTS → TEST `tests/test_lilrae_tool_runtime.py` (Real scheduler settlement and peer history)
- TESTS → TEST `tests/test_lilrae_mcp_runtime_integration.py` (Real MCP clients through common SSH/API handlers and RAES)
- IMPLEMENTS → GITHUB_ISSUE `1418` (Participant MCP action admission)
