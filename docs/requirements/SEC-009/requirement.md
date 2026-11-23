---
id: SEC-009
title: "Verified TLS for Wazuh Components and Clients"
status: ACTIVE
type: NON_FUNCTIONAL
priority: SHOULD
wave: 1
created_at: 2026-11-12T07:31:45.000000Z
updated_at: 2026-11-12T07:31:45.000000Z
---

# SEC-009: Verified TLS for Wazuh Components and Clients

## Statement

Wazuh components shall communicate over TLS. The lab Wazuh CA shall sign their certificates. This applies to manager to indexer, dashboard to indexer, and dashboard to manager API traffic. The indexer and manager API certificates shall also name `localhost` and `127.0.0.1`.

The MCP servers shall verify the TLS certificates of the indexer and manager API with the lab Wazuh CA certificate. Host-side LilRAE clients of these services shall verify TLS in the same way. No client shall disable certificate verification.

## Rationale

SEC-004 let the MCP HTTPClient accept self-signed lab certificates with `rejectUnauthorized: false`. This requirement replaces SEC-004. Each client can verify the indexer and manager API certificates, because the lab Wazuh CA signs them.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `1767` (Issue #1767: The Wazuh MCP clients do not verify TLS)
- IMPLEMENTS → ADR `docs/adrs/adr-034-lab-managed-soc-tls-ca.md` (ADR-034 Lab-Managed CA for Verified SOC Stack TLS)
- IMPLEMENTS → CONFIG `generate-indexer-certs.yml` (The indexer and manager certificates name the loopback hosts)
- IMPLEMENTS → CONFIG `docker-compose.yml` (The manager API serves the generated manager certificate)
- IMPLEMENTS → CODE_FILE `src/aptl/core/certs.py` (Regeneration of certificates without the loopback names)
- IMPLEMENTS → CODE_FILE `src/aptl/core/services.py` (Verified indexer and manager API probes)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_wazuh_attestation.py` (Verified indexer readback)
- IMPLEMENTS → CODE_FILE `src/aptl/core/deployment/_compose_stateful_readiness.py` (The probes read the lab Wazuh CA)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/http.ts` (No agent disables certificate verification)
- IMPLEMENTS → CODE_FILE `mcp/aptl-mcp-common/src/config.ts` (Configurations with `verify_ssl: false` are refused)
- IMPLEMENTS → CONFIG `mcp/mcp-wazuh/docker-lab-config.json` (Verification against the lab Wazuh CA)
- IMPLEMENTS → CONFIG `mcp/mcp-indexer/docker-lab-config.json` (Verification against the lab Wazuh CA)
- IMPLEMENTS → CONFIG `mcp/mcp-network/docker-lab-config.json` (Verification against the lab Wazuh CA)
- TESTS → TEST `tests/test_certs.py`
- TESTS → TEST `tests/test_services.py`
- TESTS → TEST `mcp/aptl-mcp-common/tests/http-agent.test.ts`
- TESTS → TEST `mcp/aptl-mcp-common/tests/http-ca.test.ts`
- TESTS → TEST `mcp/aptl-mcp-common/tests/http-failures.test.ts`
- TESTS → TEST `mcp/aptl-mcp-common/tests/config-logic.test.ts`
