---
design: 1
issue: 1758
packages:
  - path: internal/config
    component: configuration
    imports:
      - github.com/OpenRAE/lilrae/internal/canonical
      - github.com/OpenRAE/lilrae/internal/securefile
    test_imports:
      - github.com/google/go-cmp
model_changes: []
---

# Issue #1758: Merge of dev into go-cutover design

This design records the Go changes that the merge of `dev` into `go-cutover`
needs. The front matter of this note is its design record. The
[#1747 configuration design](issue-1747-go-config-design.md) applies.

## Decisions

1. **Configuration members from dev.** `dev` adds `mcp`,
   `deployment.range_egress_allowances`, the OpenCode and Vertex participant
   selections, `participant_serving_providers`, and `opencode_executable` to
   `aptl.json`. `internal/config` decodes and checks them as the Python release
   does. Decision 10 of the #1747 design gives the details.
2. **No model change.** The change stays in the `configuration` component and
   uses only its existing dependencies.
3. **Toolchain.** Go 1.27.4 fixes GO-2026-6859 in `net/http`. Each
   first-party `go.mod` names it.

## Threats

| Threat | Mitigation |
| --- | --- |
| The Go port accepts a configuration that Python rejects, or the reverse. | The decode tests cover each new member with accepted and rejected cases. |
| The default MCP ceiling drifts from the catalog. | A test compares `MCPServerIDs` with the catalog of the Python release. |
| A range egress allowance names a loopback, multicast, or unspecified address. | The check unmaps an IPv4-mapped address and rejects those classes. |
