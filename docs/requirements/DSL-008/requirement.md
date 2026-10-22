---
id: DSL-008
title: "APTL Realization of ACES Infrastructure Topology"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-03-24T02:44:23.438740Z
updated_at: 2026-10-22T00:00:00.000000Z
---

# DSL-008: APTL Realization of ACES Infrastructure Topology

## Statement

The APTL backend shall consume ACES parser/compiler output and declared topology/runtime-model content for containers, Compose profiles, networks, services, addresses, volumes, health checks, and supported topology transitions. Before scenario execution, it shall validate that the running lab satisfies those declarations, realize supported changes through model/plan-driven Docker Compose operations, and fail with explicit diagnostics for unsupported or missing declarations instead of dispatching on scenario name or maintaining an APTL-local scenario DSL.

## Rationale

After ADR-035 and SCN-010, ACES SDL owns scenario authoring and topology declaration. APTL's Wave 1 responsibility is the backend realization contract: map ACES runtime/provisioning content to the local Docker lab without reviving aptl.core.sdl or a TechVault preset shortcut.

NOT DEPRECATED 2026-10-09: ADR-035 deprecates DSL-002 to DSL-009 as requirements on the retired in-tree DSL. This record stays ACTIVE because its statement now covers how the backend realizes RAES-declared topology, not a LilRAE scenario DSL. #422 (PR #549) closed its last clause, declared node health, and made it ACTIVE on 2026-06-25. See GitHub issue #422.

## Traceability

- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_network_realization.py` (Shared declared-network reconciliation and fresh endpoint readback across startup routes)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_realization_networks.py` (Typed attachment resolution and required address/alias observation)
- TESTS → TEST `tests/test_compose_network_readback.py` (Endpoint drift, both startup routes and real default/bounded/curated SDL lowering)
- TESTS → TEST `scripts/ci/assert_boot_realization.py` (Independent installed-wheel declared-network endpoint observation)
- TESTS → TEST `tests/test_boot_realization_gate.py` (Missing endpoint, IPv4 and alias rejection in the installed-wheel gate)
- DOCUMENTS → GITHUB_ISSUE `#422` (DSL-008: Infrastructure Topology Declaration in Scenario DSL)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/techvault_live_gate.py` (Live conformance gate: validate the running lab satisfies ACES declarations)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/_live_gate_readiness.py` (Node-readiness / declared-health conformance comparison against the running range)
- TESTS → TEST `tests/test_techvault_live_gate.py` (Tests for live conformance gate incl. declared-health readiness enforcement)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_realization.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_realization_values.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_profiles.py`
- TESTS → TEST `tests/test_raes_backend.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_realization_model.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_diagnostics.py`
- IMPLEMENTS → CODE_FILE `src/aptl/backends/_raes_scenario_queries.py` (Admit one scenario execution; project the pre-start facts lab start reads)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_runtime_observation.py` (Trusted observation of declared runtime concerns on the realized range)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/_runtime_concern_excess.py` (Excess/scope detection and the runtime baselines subtracted before rejection)
- TESTS → TEST `tests/test_raes_runtime_observation.py` (Realization-observation gate tests, including the runtime-baseline carve-outs)
- IMPLEMENTS → GITHUB_ISSUE `956` (Faithfully realize SDL privilege and runtime security requirements)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/runtime_materialization.py` (Graph-wide pre-mutation qualification of image-backed, generic, mixed, mount, and orchestration-authority contracts)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_node_generation.py` (Faithful Compose lowering for supported runtime container, capability, and mount fields)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_realization.py` (Qualification and effective-model gates before ownership or deployment mutation)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes.py` (Read-only planned-graph qualification before deferred component-image materialization)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_artifact_availability.py` (Read-only specification inspection separated from post-qualification Docker builds)
- IMPLEMENTS → DOCUMENTATION `docs/architecture/issue-956-sdl-runtime-authority-materialization-preflight.md` (Faithful runtime-authority materialization boundary and supported backend fields)
- TESTS → TEST `tests/test_runtime_materialization.py` (Supported and unsupported materialization, lowering, ordering, and effective-model coverage)
- TESTS → TEST `tests/test_raes_artifact_availability.py` (Read-only inspection and deferred component-build ordering coverage)
- TESTS → TEST `tests/test_raes_runtime_orchestration.py` (Exact raw-socket joins and unrestricted authored holder topology coverage)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/scenario_startup_policy.py` (Pack-qualified, declared-edge-only startup health policy)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_model_realization.py` (Validated startup overlay in the generated Compose file set)
- IMPLEMENTS → CODE_FILE `src/aptl_techvault/startup.py` (TechVault-specific health probes through the adapter seam)
- TESTS → TEST `tests/test_techvault_startup_adapter.py` (Content-qualified startup policy and undeclared-edge rejection)
- TESTS → TEST `tests/test_base_container_admission_integration.py` (Product-neutral real-Docker materialization envelope)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/_raes_backend_implementation_catalog.py` (Redis runtime config staged outside a publicly writable directory)
- IMPLEMENTS → CODE_FILE `src/aptl_techvault/log_sources.py` (Native log configuration staged under a root-owned guest path)
- TESTS → TEST `tests/test_misp_redis_realization_contract.py` (Credential-free argv and protected Redis staging path)
- TESTS → TEST `tests/test_techvault_log_sources.py` (Protected rsyslog staging and native producer behavior)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_misp_cache_credential.py` (Shared protected Redis runtime config path contract)
- IMPLEMENTS → CODE_FILE `src/aptl_techvault/redis_acl_observation.py` (Live authorization readback from the selected config path)
- IMPLEMENTS → CODE_FILE `src/aptl/validation/_gate_raes_cli.py` (Resolve the installed RAES CLI from the active Python environment for source and wheel validation)
- TESTS → TEST `tests/test_techvault_static_gate.py` (RAES CLI resolution with and without virtual-environment PATH activation)
- IMPLEMENTS → DOCUMENTATION `docs/testing/smoke-test-plan.md` (Capture the user-facing startup inventory and validate both installation paths)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_account_provider.py` (Account providers bound to the realizing implementation, not to a scenario node name)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_account_realization.py` (Authored secret_fixture credential bindings lowered or refused)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_application_accounts.py` (Declared SOC console accounts realized and proven by authentication)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/raes_declared_credentials.py` (Account credential references resolved from the admitted SDL only)
- IMPLEMENTS → CODE_FILE `src/aptl/core/participant_desktop.py` (Participant desktop resolved from the admitted SDL and the realized lab)
- IMPLEMENTS → CODE_FILE `tools/check_pack_boundary.py` (Pack-owned facts refused in generic files, derived from the owning pack's SDL)
- TESTS → TEST `tests/test_declared_account_credentials.py` (Credential binding lowering and refusal)
- TESTS → TEST `tests/test_account_provider.py` (Conflicting duplicate identities or credentials refuse the entire batch before mutation)
- TESTS → TEST `tests/test_seat_desktop.py` (Desktop delivery waits for both private files and successful management-owned hostname publication)
- TESTS → TEST `tests/test_application_accounts.py` (Application account providers, stdin-only secrets, and fail-closed proofs)
- TESTS → TEST `tests/test_participant_desktop.py` (Desktop resolution from the owned fixture pack and private publication)
- TESTS → TEST `tests/test_pack_boundary_policy.py` (Boundary check over the repository and planted facts)
- IMPLEMENTS → CODE_FILE `src/aptl/backends/participant_desktop.py` (Exact pack-qualified desktop reference admission)
- IMPLEMENTS → CODE_FILE `src/aptl/core/participant_hosts.py` (Validated hostname projection applied through management-owned publication)
- IMPLEMENTS → CODE_FILE `src/aptl/core/_participant_desktop_files.py` (Participant-only inactive credential and guide files)
- IMPLEMENTS → CODE_FILE `src/aptl/core/_participant_desktop_endpoints.py` (Declared endpoint resolution and bounded hostname mappings)
- IMPLEMENTS → CODE_FILE `src/aptl/core/_participant_desktop_tls.py` (Verify the served chain, hostname and exact backend-issued leaf)
- TESTS → TEST `tests/test_participant_desktop_tls.py` (Live TLS refusal, private-material isolation and released certificate bindings)
- TESTS → TEST `tests/test_participant_desktop_lifecycle.py` (Start, failed-start, stop and reset withdraw stale desktop state)
- TESTS → TEST `tests/test_participant_hosts.py` (Hostname conflicts, unsafe paths and metadata-preserving removal)
- TESTS → TEST `tests/test_owned_content_install.py` (Declared content ownership reaches the realized node)
- IMPLEMENTS → GITHUB_ISSUE `1273` (Move participant desktop and rule-file scenario facts behind the TechVault adapter)
