# MCP Smoke-Test Protocol

The canonical hands-on MCP procedure is the
[Release Candidate Manual QA](../testing/smoke-test-plan.md). It contains the
release-blocking checks for `mcp-red`, `mcp-wazuh`, `mcp-indexer`, `mcp-soar`,
`mcp-threatintel`, `mcp-network`, and `mcp-reverse`, with a
separate result and evidence reference for both supported install paths.

The former protocol on this page predated the SDL-only runtime and had different pass criteria.
The canonical QA record replaces it. Automated smoke and integration tests give regression evidence. Process startup, `tools/list`, and container health do not replace the release record's manual target-backed operations.
