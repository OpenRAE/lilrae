# Architecture documentation source checks

This Reference records the #1667 rewrite.
The source baseline is `6d35d245f11a7fffcaac1645cd25ccfafbad4599`.
Current descriptions use that implementation and the candidate documentation tree.
Historical descriptions keep their stated evidence dates and source revisions.
No runtime, dependency, credential, or requirement-lifecycle change is part of this delivery.

## Preservation boundaries

The five assigned directories contained 386 Markdown pages at the source baseline.
The rewrite also owns its new explanation, lookup, integration, and verification pages.
The assignment register records those paths and reader purposes.

The 123 historical preflight, review, and qualification records receive status and source-revision notices.
Their original record text remains exact.
The terminology inventory also receives one dated maintenance row; its original text remains unchanged.
Their embedded outputs, quotations, dates, and qualification limits are source evidence rather than current procedures.
The original revision remains available through each notice.

The 156 requirement files keep their original front matter, identifiers, contractual statements, rationale, and traceability.
Their new notices describe Reference contracts without changing lifecycle state.
An ACTIVE requirement remains active; it is not a retired implementation record.
These notices do not claim implementation or verification.

ADR numbers, dates, statuses, amendment headings, and decision meaning remain in place.
The index follows recorded status and preserves partial supersession information.
The source revision preserves the original wording for comparison.
Exact quoted evidence and literal output remain unchanged.

## Source correspondence

Each row covers the maintained sections in its page group.
The section inventory below identifies the headings within those groups.
Named tests identify existing verification owners; they are not claims of workstation execution.

| Page group | Source paths and revision evidence | Corrected differences and verification |
| --- | --- | --- |
| Architecture overview, networking, enterprise design, root topology Reference | `docker-compose.yml`; `src/aptl/core/deployment/_compose_port_realization.py`, `_operator_access_endpoints.py`, `_operator_access_proof.py`; ADR-046, ADR-051, ADR-060, ADR-063 | Separate root compatibility stubs from admitted topology. Remove current mail/reverse and blanket Falco claims. Keep old phase/resource estimates historical. Existing network-readback, port-binding, and documentation contracts own behavior evidence. |
| ADR-000 through ADR-009 | Original ADRs and Git history; `src/aptl/cli/main.py`, `core/config.py`, `core/lab.py`; `mcp/aptl-mcp-common/src/{http,ssh,ssh-session,ssh-manager,ssh-contracts,server,index}.ts` | Keep original costs, timings, counts, and decision dates as historical facts. Correct current command names, heap/container-memory distinction, queued background submissions, merged PTY output, and chunk-based buffer limits. Existing SSH and CLI contracts remain unchanged. |
| ADR-010 through ADR-018; CI explanation | `.github/workflows/checks.yml`, `.github/branch-protection-baseline.json`, `tools/ci/select_checks.py`, `pyproject.toml`, `eslint.config.js`; removal commit `79eaab7a0894a4212045909378935c5e6737c3d6` for the local SDL | Preserve dated quality-gate chronology. Distinguish global complexity from enrolled rules. Label removed local SDL/runtime contracts and old versions; link current RAES ownership. CI owns complete coverage and prose gates. |
| ADR-019 through ADR-024; capture and response reasons | `config/wazuh_cluster/wazuh_manager.conf`; `containers/_wazuh-agent/aptl-firewall-drop.sh`; `src/aptl/services/misp_suricata_sync/{config,misp_client,translator,main}.py`; original network experiment output | Preserve IDS versus host enforcement, whitelist policy, tagging, deterministic SIDs, reload refusal, and TLS amendments. Correct the false claim that all four root networks are internal. The security network is external. Original network experiments remain revision-bound evidence. |
| ADR-025 through ADR-034 | `src/aptl/core/config.py`, `credentials.py`, `soc_ca.py`, `lab.py`; `src/aptl/utils/{redaction,pathsafe,curl_safe}.py`; common MCP `http.ts`, `redaction.ts`, telemetry; existing configuration and redaction contracts | Preserve strict parsing, generated-state ownership, containment, atomic writes, permissions, secret classification, and distinct readiness failures. Keep shared helpers and exact refusal boundaries. No new secret taxonomy or error model is introduced. |
| ADR-035 through ADR-053; realization, family, cleanup, reporting, and recovery designs | `src/aptl/backends/{scenario_family,scenario_family_models,raes_runtime_observation,trial_serving,trial_recovery,trial_services,readiness,installed_readiness}.py`; `src/aptl/core/{trial_readiness,trial_ownership,trial_intent,readiness_record,runstore}.py`; deployment materialization owners | Preserve portable RAES ownership, typed native operations, observed state, admission before effects, separate identities, cleanup fences, and immutable evidence. Original dependency versions and preflight inventories are historical. Source metadata owns the current dependency range. |
| Capture ADRs and participant action designs | `docker-compose.capture.yml`; `containers/kali-capture/broker.py`; common MCP `runs.ts`, `captures.ts`, `lilrae-tool-admission.ts`, `lilrae-tool-outcome.ts`; `src/aptl/backends/participant_tools/` and `src/aptl/core/participant_tools/` | Preserve PTY-master ownership, broker completion markers, cross-session isolation, and unknown outcomes. Link supersession of workload-fed transcripts and withdrawal of audit/accounting witnesses. Source supervision is not described as host containment. |
| Participant request, concurrency, and native-observation designs | `src/aptl/core/participant_requests/`; `src/aptl/workbench/{trial_participants,provider_capture,opencode_history,opencode_observation,opencode_configuration}.py`; `src/aptl/core/provider_observation.py`; `src/aptl/workbench/provider_capture.mjs` | Preserve exact participant/configuration/content joins, request-control omissions, private observation, unknown served identity, and bounded processes. Move integration tasks to linked How-to guides. Existing participant and native-transport contracts own runtime evidence. |
| ADR-054 through ADR-067; seat designs and records | Recorded ADR status/amendments; `src/aptl/appliance/`, `src/aptl/cli/seat.py`, `scripts/appliance/`; `src/aptl/core/mcp_policy.py`; participant architecture model and layer map | Proposals remain proposed. One-host observations do not become signed or multi-host qualification. Keep VM-only containment, later browser-desktop scope, authority exceptions, and current readback/smoke contracts distinct. |
| Web design and component kit | `src/aptl/cli/web.py`; `src/aptl/api/{main,deps,session}.py`, `middleware/bff.py`, terminal routes; `web/src/lib/session.ts`; `web/src/app.css`; `web/src/lib/components/kit/tone.ts`, `index.ts`, `Menu.svelte`, and `Field.svelte` | Separate design targets from shipped routes. Keep API bearer, browser factors, CSRF/Host checks, WebSocket tickets, and asset discovery distinct. Correct the XSS limit, remove the clone-only delivery claim, and move operating steps to the existing guide. Component tables move to one Reference page. |
| Design-check and documentation pages | `tools/check_architecture.py`, `tools/check_lilrae_participant_architecture.py`, `tools/design_wiring.py`, `tools/design_acceptance.py`; `.ste.yml`, `.vale.ini`, `.ste-required.txt`, `mkdocs.yml`; existing documentation tests | Compilation creates bytecode and is not a type check. Acceptance execution is a behavior test and stays in CI or an approved VM. Preserve useful URLs and headings while moving task and lookup material. Reuse existing tools and publishers. |

## Editorial review

Reader purpose, technical accuracy, and language receive separate review.
Current reasons use Explanation; operating tasks use How-to guides; exact facts and historical records use Reference.
The source owner, rather than a directory name, determines a claim's authority.

The review uses the official ASD-STE100 Issue 9 rules and technical-term guidance.
The standard and dictionary are not copied into the repository.
Sentences keep explicit subjects, simple structure, and original conditions and obligations.
New instructions keep one action per sentence.
Paragraph divisions separate related topics without changing quoted evidence.

Technical names retain their source meanings.
Examples include admission, binding, provenance, placement, capture, realization, snapshot, seal, and qualification.
Run, trial, attempt, planned identity, observed state, and cleanup state remain distinct concepts.
A digest does not become authentication, successful execution, or scientific eligibility.

The local checks use the existing explicit-path Vale and STE wrappers.
Finished owned prose enters `.ste-required.txt`.
The new notices for exact source records use the existing passage-check boundary.
A linter result does not establish full technical correctness or language conformance by itself.

## Pre-push review repairs

The required review covered all 397 changed files in seven sections.
It found two prose defects and no concrete exploitable security regression.
The ADR-064 rewrite now keeps the original requirement for one implementation per shared concern.
The moved readiness guide now links to its design in `docs/architecture/`.
An unrelated web-reference link was also removed from ADR-032.

The repaired prose passes the existing explicit-path Vale and STE checks.
There is no executable surface for a regression test in these repairs.
CI still owns the strict site build and existing navigation checks.

## Verification boundary

Static comparison checks requirement metadata and preserved record bodies against the baseline.
Non-Markdown evidence artifacts remain unchanged.
Heading comparison checks old fragments and the explicit compatibility anchor for the continuity decision.
Navigation uses the existing MkDocs configuration and real destination pages.

The first documentation CI run passed 72 checks and found one missing inventory update.
The existing terminology inventory now lists the five additional Scenario Pack pages.
The new row is dated and does not rewrite its historical source text.
No test or inventory-matching rule was changed.

CI owns the strict MkDocs build, full prose checks, and behavior tests.
The existing documentation lane runs its targeted tooling and navigation cases.
The STE enrollment change also retains the selector's broad fallback; this rewrite does not weaken lane selection.
No application test, lab command, lifecycle operation, or provider request ran on the workstation.

The final consistency check compared the candidate with decisions, source records, and root topology.
It found a remaining mail-service entry in the new root topology table.
The corrected row now names only the declared webapp and DNS roles.
All 275 navigation targets and 208 added local links resolve to existing paths.
The 123 historical bodies, 156 requirement records, and 68 ADR metadata values remain preserved.

The delivery PR records actual review, hygiene, CI, and SonarCloud outcomes.
Those outcomes do not imply live lab or provider qualification beyond their stated tests.

## Section inventory

The following inventory names maintained sections reviewed in the page groups above.
A page without a level-two heading uses its introduction as the maintained section.
For preserved historical and requirement records, review covers the added status notice; the original source body is not rewritten.

| Page | Maintained sections |
| --- | --- |
| `docs/adrs/README.md` | ``Format``, ``Principles``, ``Index`` |
| `docs/adrs/adr-000-use-adrs.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-001-docker-compose-deployment.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-002-wazuh-siem.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-003-mcp-common-library.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-004-persistent-ssh-sessions.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences``, ``Update (2026-05-12): Contract hardening guardrails``, ``Update (2026-05-18): Effective session-mode metadata``, ``Update (2026-05-18): Awaitable remote-close boundary`` |
| `docs/adrs/adr-005-docker-compose-profiles.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-006-four-network-segmentation.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-007-python-cli-control-plane.md` | ``Status``, ``Date``, ``Context``, ``Decision``, ``Consequences``, ``Python 3.14 dependency boundary`` |
| `docs/adrs/adr-008-soc-stack-integration.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-009-scenario-engine.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-010-sonarcloud-quality.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision``, ``Consequences``, ``Update (2026-06-21): SonarCloud gate is required again (issue #502)``, ``Update (2026-05-10): SonarCloud gate stayed advisory``, ``hard complexity gate added``, ``Update (2026-09-20): Platform dependency gate (issue #969)`` |
| `docs/adrs/adr-011-web-ui.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision (Proposed)``, ``Consequences`` |
| `docs/adrs/adr-012-opentelemetry-integration.md` | ``Applicability``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-013-deployment-abstraction.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision``, ``Consequences``, ``Subsequent Changes`` |
| `docs/adrs/adr-014-scenario-description-language.md` | ``Applicability``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-015-declarative-sdl-objectives.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-016-workflows-targetable-subobjects-and-enum-variables.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-017-sdl-runtime-layer.md` | ``Applicability``, ``Context``, ``Decision``, ``Consequences``, ``Scope Boundaries`` |
| `docs/adrs/adr-018-control-flow-primitives.md` | ``Status``, ``Date``, ``Applicability``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-019-suricata-ids-only-prevention-via-wazuh-ar.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Consequences``, ``Related`` |
| `docs/adrs/adr-020-wazuh-agents-in-process-vs-sidecar.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Related`` |
| `docs/adrs/adr-021-active-response-whitelist-via-wrapper.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Related`` |
| `docs/adrs/adr-022-misp-driven-suricata-rules.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Verification``, ``Related`` |
| `docs/adrs/adr-023-container-interaction-in-deployment-backend.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``References`` |
| `docs/adrs/adr-024-orchestrator-side-purple-continuity-carve-out.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Alternatives considered``, ``References`` |
| `docs/adrs/adr-025-strict-first-party-config-schema.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``References`` |
| `docs/adrs/adr-026-advisory-ci-vulnerability-scanning.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Amendment: OpenSSF Scorecard and dependency pinning (issue #847)``, ``Amendment (2026-09-20): Required platform dependency audit (issue #969)``, ``Amendment (2026-10-04): Blocking scanner gates with tracked unfixed findings (issue #1193)`` |
| `docs/adrs/adr-027-red-team-structured-logging.md` | ``Status``, ``Date``, ``Status update—2026-05-17``, ``Status update - 2026-05-18``, ``Reader boundary``, ``Context``, ``Decision``, ``Guardrails``, ``Consequences`` |
| `docs/adrs/adr-028-runtime-rendered-service-config.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Guardrails``, ``Security Layers``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns`` |
| `docs/adrs/adr-029-control-plane-secret-handling.md` | ``Status``, ``Date``, ``Status update—2026-07-25``, ``Reader boundary``, ``Context``, ``Decision``, ``Artifact Boundary Audit``, ``Security Layers``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns`` |
| `docs/adrs/adr-030-startup-partial-readiness-classification.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Guardrails``, ``Security Layers``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns`` |
| `docs/adrs/adr-031-lab-orchestration-contract-guards.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Guardrails``, ``Security Layers``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns`` |
| `docs/adrs/adr-032-conversation-surface-hardening.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-033-agent-reasoning-trace-boundary.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Security layers``, ``Maintainability``, ``Extensibility``, ``Non-goals``, ``Anti-patterns`` |
| `docs/adrs/adr-034-lab-managed-soc-tls-ca.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Security Layers``, ``Guardrails``, ``Gotchas``, ``Known Constraints``, ``Host Exposure Amendment``, ``Non-Goals``, ``Anti-Patterns``, ``References`` |
| `docs/adrs/adr-035-raes-sdl-adoption.md` | ``Status``, ``Date``, ``Last Updated``, ``Status update—2026-06-29``, ``Status update—2026-07-12``, ``Status update—2026-07-19``, ``Reader boundary``, ``Context``, ``Decision``, ``Backend Profile Choice``, ``Parity Gate``, ``Parity Inventory Boundary``, ``RAES Backend Integration Guardrails``, ``Legacy Cleanup Reconciliation``, ``Historical Migration Plan``, ``Consequences``, ``Alternatives Considered``, ``Related Requirements``, ``Related Issues`` |
| `docs/adrs/adr-036-snapshot-endpoint-registry.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Security Layers``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns`` |
| `docs/adrs/adr-037-docker-compose-backend-cohesion.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Guardrails``, ``Consequences``, ``Non-Goals``, ``Anti-Patterns``, ``References`` |
| `docs/adrs/adr-038-docs-style-lint-and-published-site.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Amendment: Dual Publishing On Read The Docs``, ``Amendment: STE checks and reader routes``, ``Consequences``, ``Non-Goals``, ``References`` |
| `docs/adrs/adr-039-web-control-plane-authentication.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Security Layers``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns``, ``References`` |
| `docs/adrs/adr-040-terminal-ssh-host-key-verification-boundary.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Security Layers``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns``, ``References`` |
| `docs/adrs/adr-041-kali-capture-sidecar-ownership-boundary.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``RPC Contract``, ``Security Layers``, ``Maintainability``, ``Extensibility``, ``PTY transcript authenticity (residual)``, ``Consequences``, ``Non-Goals``, ``Anti-Patterns``, ``Related`` |
| `docs/adrs/adr-042-sidecar-owned-pty-master.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Attacker Model``, ``Security Layers``, ``Maintainability``, ``Extensibility``, ``Verification Guardrails``, ``Non-Goals``, ``Anti-Patterns``, ``Related``, ``Session finalization at MCP shutdown (#1541)`` |
| `docs/adrs/adr-043-suricata-runtime-config-ownership-boundary.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Rejected Options``, ``Guardrails``, ``Security Layers``, ``Maintainability``, ``Extensibility``, ``Whole-Repo Surface``, ``Non-Goals``, ``Anti-Patterns`` |
| `docs/adrs/adr-044-raes-aligned-run-reproducibility-record.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Security Layers``, ``Maintainability``, ``Extensibility``, ``Non-Goals``, ``Anti-Patterns``, ``References`` |
| `docs/adrs/adr-045-ephemeral-lifecycle-policy-enforcement.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-046-dynamic-raes-scenario-realization.md` | ``Status``, ``Date``, ``Last Updated``, ``Reader boundary``, ``Context``, ``Decision``, ``Paper Scenario Spine Addendum``, ``Paper Scenario Evidence Modeling Addendum``, ``Image Realization Addendum``, ``Network Realization Addendum``, ``Runtime Service and SEM-218 Execution Addendum``, ``Heavy Stateful Service Realization Addendum``, ``Account and Identity Realization Addendum``, ``Declared Fixture Credential Addendum``, ``Credential-Bearing Apply Result Addendum``, ``Owner-Declared Image Content Addendum``, ``TechVault Operational Standup Addendum``, ``Capture Inventory and Parity-Inventory Removal Addendum``, ``TechVault Full Dynamic Cutover Addendum``, ``Security Layers``, ``Maintainability``, ``Extensibility``, ``Consequences``, ``Non-Goals``, ``Anti-Patterns``, ``Descendant recording and attestation addendum``, ``References`` |
| `docs/adrs/adr-047-raes-experiment-admission-and-trial-plan-boundary.md` | ``Status``, ``Date``, ``Released-contract successor boundary (issue #1465)``, ``Reader boundary``, ``Context``, ``Decision``, ``Security layers``, ``Canonical incumbents``, ``Extensibility``, ``Testing contract``, ``Gotchas``, ``Non-goals``, ``Anti-patterns``, ``References`` |
| `docs/adrs/adr-048-image-free-placement-realization.md` | ``Status``, ``Date``, ``Last Updated``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Supersession`` |
| `docs/adrs/adr-049-sealed-disposable-lab-appliance.md` | ``Status``, ``Current scope clarification``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Explicit contracts``, ``Threat model``, ``Credentials, evidence, capture, reset, upgrade, and recovery``, ``Migration of existing contracts``, ``Cross-cutting layers and canonical incumbents``, ``Arsenal milestone controls``, ``Follow-on issue reconciliation``, ``Acceptance evidence``, ``Consequences``, ``Non-goals``, ``Anti-patterns``, ``References`` |
| `docs/adrs/adr-050-terminal-attempt-archival-and-atomic-seal.md` | ``Status``, ``Date``, ``Released-producer successor boundary (issue #1465)``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Non-Goals``, ``References`` |
| `docs/adrs/adr-051-component-level-raes-realization.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``Supersession``, ``Non-Goals`` |
| `docs/adrs/adr-052-configured-participant-credential-sourcing.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Terminology``, ``Threat Model``, ``Research Considered``, ``Options And Tradeoffs``, ``Decision``, ``Cross-Cutting Passage And Canonical Incumbents``, ``Extensibility``, ``Consequences``, ``Non-Goals``, ``Anti-Patterns``, ``References`` |
| `docs/adrs/adr-053-pack-backend-deployment-serving-interaction-seam.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Cross-Cutting Incumbents``, ``Security And Host-Layer Passage``, ``Consequences``, ``Extensibility``, ``Anti-Patterns``, ``Non-Goals``, ``References`` |
| `docs/adrs/adr-054-lilrae-core-and-experience-ownership.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Proposed decision``, ``Existing ADR disposition``, ``Consequences and verification`` |
| `docs/adrs/adr-055-local-runtime-authority-and-ownership.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Proposed decision``, ``Failure and recovery``, ``Existing ADR disposition``, ``Acceptance evidence and owners`` |
| `docs/adrs/adr-056-scenario-led-capability-qualification.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Proposed decision``, ``Existing ADR disposition``, ``Consequences and verification`` |
| `docs/adrs/adr-057-agent-execution-compartments.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Proposed decision``, ``Existing ADR disposition``, ``Verification and delivery`` |
| `docs/adrs/adr-058-adoption-and-security-release-gates.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Proposed decision``, ``Existing ADR disposition``, ``Consequences and implementation`` |
| `docs/adrs/adr-059-canonical-techvault-delivery-and-host-mcp-access.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Cross-cutting validation and reuse``, ``Consequences and implementation boundaries`` |
| `docs/adrs/adr-060-vm-only-seat-containment.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Image delivery and trust``, ``Consequences`` |
| `docs/adrs/adr-061-gateless-vm-seat-access.md` | ``Status``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-062-lilrae-name-and-naming-convention.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-063-remove-thehive-and-cortex.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-064-layered-architecture-and-code-conventions.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences``, ``References`` |
| `docs/adrs/adr-070-executable-participant-action-boundaries.md` | ``Status``, ``Reader boundary``, ``Context``, ``Decision``, ``Consequences`` |
| `docs/adrs/adr-071-runtime-readback-reports-realized-state.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Alternatives considered``, ``Consequences``, ``Relation to other decisions`` |
| `docs/adrs/adr-067-admitted-participant-smoke-providers.md` | ``Status``, ``Date``, ``Reader boundary``, ``Context``, ``Decision``, ``Alternatives considered``, ``Consequences`` |
| `docs/architecture/ci-verification.md` | ``Components and contracts``, ``Data flows and security``, ``Go cutover branch``, ``Verification policy``, ``References`` |
| `docs/architecture/concurrent-participant-execution.md` | ``Ownership and composition``, ``Participant configuration and harnesses``, ``Execution and failure``, ``Data flow and security``, ``Existing architecture and verification``, ``Integration and qualification limits``, ``Related issue coverage``, ``References`` |
| `docs/architecture/design-checks.md` | ``The four design checks``, ``The acceptance adapter``, ``Run the checks`` |
| `docs/architecture/documentation-assignments.md` | ``Revision and use``, ``Page assignments``, ``Mixed sections``, ``Source documentation and generated sources``, ``Non-Markdown source records`` |
| `docs/architecture/documentation-boundaries.md` | ``Components and contracts``, ``Data flows and trust boundaries``, ``Security and failure behavior``, ``Policy and executable architecture``, ``Sources`` |
| `docs/architecture/enterprise-infrastructure.md` | ``Where We Started``, ``The Core Design Question``, ``Network Segmentation`` |
| `docs/architecture/exp-011-resource-readiness-design.md` | ``Boundaries``, ``Owner inputs``, ``Evidence and failure behavior``, ``Data flow``, ``Security and verification``, ``Released public API``, ``References`` |
| `docs/architecture/family-adapter-contract.md` | ``Interfaces and identity``, ``Admission and data flows``, ``Security and failure behavior``, ``Architecture and policy``, ``References`` |
| `docs/architecture/index.md` | ``Network Topology``, ``Container Layout``, ``Ports``, ``Data Flow``, ``Components``, ``CI verification``, ``Preflights`` |
| `docs/architecture/interrupted-trial-recovery.md` | ``Components and contracts``, ``Data flows and trust boundaries``, ``Security and failure controls``, ``Architecture and extension points``, ``References`` |
| `docs/architecture/issue-1017-native-runtime-attestation-design.md` | ``Existing owners``, ``Native values and provenance``, ``Data flow``, ``Removed compatibility``, ``Verification and release qualification`` |
| `docs/architecture/issue-1127-seat-component-protection-design.md` | ``Evidence``, ``Scope And Threat Model``, ``Signed Contract``, ``Components``, ``Network Enforcement``, ``Runtime And Custody Enforcement``, ``Data Flow And Trust Boundaries``, ``Start And Qualification Sequence``, ``Probe Coverage``, ``Failure Behaviour``, ``Policy And Architecture As Code``, ``Verification``, ``Residual Risks And Limits`` |
| `docs/architecture/issue-1130-owned-descendant-reporting-design.md` | ``Native runtime decision``, ``Components and contracts``, ``Observation coverage``, ``Data flows and trust boundaries``, ``Initial apply and later refresh``, ``Provenance and observation coverage``, ``Security controls and failure behavior``, ``Experiment evidence handoff``, ``Repository contracts``, ``References`` |
| `docs/architecture/issue-1244-mcp-service-selection.md` | ``Introduction`` |
| `docs/architecture/issue-1372-capture-spec-version-design.md` | ``Evidence``, ``Architecture``, ``Systems Security``, ``Data Flow``, ``Supporting Artifacts`` |
| `docs/architecture/issue-1420-request-observation-decision.md` | ``Existing OpenCode records``, ``Existing Claude Code proof``, ``Implementation implications``, ``References`` |
| `docs/architecture/issue-1421-capture-design.md` | ``Existing interfaces``, ``Participant data``, ``Responsibilities and limits``, ``Verification``, ``Capture implementation boundaries`` |
| `docs/architecture/issue-1422-wazuh-dashboard-owned-config-design.md` | ``Evidence``, ``Architecture``, ``Systems Security``, ``Data Flow``, ``Start Sequence``, ``Policy and Architecture as Code`` |
| `docs/architecture/issue-1424-runtime-retry-ownership-design.md` | ``Evidence``, ``Architecture``, ``Systems Security``, ``Data Flow``, ``Retry Sequence`` |
| `docs/architecture/issue-1447-runtime-owner-handoff.md` | ``Ownership Decision``, ``Authority And Failure Handling``, ``Verification``, ``Security Gate Repairs`` |
| `docs/architecture/issue-1465-released-experiment-tuple-design.md` | ``Decisions``, ``Architecture``, ``Data flows``, ``Systems security``, ``Policy and architecture as code``, ``ADR impact``, ``References`` |
| `docs/architecture/issue-1510-code-quality-design.md` | ``Evidence``, ``Architecture``, ``Systems Security``, ``Data Flow``, ``Enrollment Sequence`` |
| `docs/architecture/issue-1603-released-module-design.md` | ``Dependencies and interfaces``, ``Data flow and security``, ``References``, ``Released contract adjustments`` |
| `docs/architecture/issue-1646-scoped-tool-affordances-design.md` | ``References`` |
| `docs/architecture/issue-1667-documentation-preflight.md` | ``Record status``, ``Documentation boundaries``, ``Contract owners and security boundaries``, ``Architecture distinctions``, ``Navigation and future changes``, ``Evidence and verification limits``, ``Non-goals`` |
| `docs/architecture/issue-435-declared-cleanup-design.md` | ``Ownership``, ``Supported behavior``, ``Evidence and recovery``, ``Data flows and trust boundaries``, ``Architecture and verification`` |
| `docs/architecture/issue-965-secret-bindings.md` | ``Introduction`` |
| `docs/architecture/issue-968-native-network-policy.md` | ``Operator configuration``, ``Verification``, ``Publications on internal-only nodes`` |
| `docs/architecture/managed-opencode.md` | ``Contracts``, ``Data and authority``, ``Evidence and release``, ``References`` |
| `docs/architecture/networking.md` | ``Networks``, ``Container IPs``, ``Multi-Homed Containers``, ``Host Port Mappings``, ``Internal Communication``, ``Network Isolation``, ``Egress Controls (SAF-002)`` |
| `docs/architecture/pack-boundary-design.md` | ``Components and interfaces``, ``Security and failure behavior``, ``Data flow``, ``Policy and executable architecture``, ``Test ownership``, ``Decisions and references``, ``Document review``, ``Retained compatibility ownership`` |
| `docs/architecture/participant-action-enforcement.md` | ``Purpose and ownership``, ``Executable architecture``, ``Installed mappings and controllers``, ``Data flow and transport``, ``Security and failure boundaries``, ``Research and qualification surface``, ``Sources`` |
| `docs/architecture/participant-request-manifests.md` | ``Ownership and interfaces``, ``Admission and content``, ``Identity and limitations``, ``Data flow and trust boundaries``, ``Security and verification``, ``References`` |
| `docs/architecture/participant-tool-admission.md` | ``Result and limits``, ``Evidence cut and method``, ``Fundamental goals already established``, ``Existing work to retain``, ``External patterns and their limits``, ``Drift assessment beyond #1418``, ``Blast radius``, ``Alternatives for discussion``, ``Representative walkthroughs before a decision``, ``Review sequence and current work``, ``References`` |
| `docs/architecture/trial-participant-configuration.md` | ``Boundaries and application``, ``Native observation``, ``Data flow and security``, ``References``, ``Approved local request observer`` |
| `docs/architecture/trial-serving.md` | ``Ownership and flow``, ``Required readiness``, ``Security and executable checks``, ``Trial outcome reporting (issue #1416 preflight)``, ``Outcome handoff design`` |
| `docs/reference/architecture-decisions.md` | ``Template``, ``Existing links`` |
| `docs/reference/compose-topology.md` | ``Networks``, ``Container IPs``, ``Host Port Mappings``, ``Sources`` |
| `docs/reference/design-check-tools.md` | ``Tool contracts``, ``The acceptance adapter`` |
| `docs/reference/participant-trial-integration.md` | ``Bind the admitted configuration`` |
| `docs/reference/trial-readiness-integration.md` | ``Compose the shared gate`` |
| `docs/reference/verify-participant-actions.md` | ``Run the targeted checks`` |
| `docs/reference/web-component-kit.md` | ``Token groups``, ``Primitives``, ``Field context``, ``Focus and motion`` |
| `docs/specs/soc-feature-spec.md` | ``1. Overview``, ``2. Architecture``, ``3. Scenario Schema``, ``4. Session Lifecycle``, ``5. Data Collection``, ``6. Storage``, ``7. Configuration``, ``8. Testing`` |
| `docs/specs/web-component-kit.md` | ``Design tokens``, ``Primitives``, ``Testing`` |
| `docs/specs/web-gui-design.md` | ``Purpose``, ``Product Scope``, ``Design Inputs and Visual Direction``, ``Interaction Affordances``, ``Settings and Persistence``, ``Accessibility``, ``Language and Locale Readiness``, ``Legal and Privacy UX``, ``Information Architecture``, ``Route Contracts``, ``Page Designs``, ``Component Inventory``, ``API and Data Contracts``, ``Authentication and Security UX``, ``UI-008 Acceptance Checklist``, ``Requirement Mapping`` |
