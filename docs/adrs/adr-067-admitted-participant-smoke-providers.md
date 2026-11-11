# ADR-067: Admitted Participant Smoke Providers

## Status

accepted

## Date

2026-11-07

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [smoke-protocol Reference](../components/mcp-smoke-test-protocol.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

The `aptl.participant_mcp_smoke_plans` entry point loads a fixed tuple of MCP operations.
The plan receives no admitted scenario, service inventory, tool grant, or target address.
An adapter cannot omit operations for a service that its trial selects out.
An adapter must also hard-code target addresses.
[Issue #1707](https://github.com/OpenRAE/lilrae/issues/1707) asks for a supported provider interface.
The [design](../architecture/issue-1707-participant-smoke-provider-preflight.md) gives the components, data flows, and threats.

## Decision

1. The entry point can load a provider object or a static tuple.
   A provider declares its checks and resolves operations from a context.
   The provider API version is `1`.
2. Discovery reads declarations only. It never calls `resolve`.
3. The context contains non-secret admitted values only.
   These are profile and scenario identity, admitted nodes, exact tool grants, and expected readiness checks.
4. Lab start records the admitted node inventory in the run MCP admission.
   Node addresses come from static assignments in the admitted realization.
   Resolution does not inspect containers.
5. The managed qualification caller binds the run admission to its run ID.
   A provider cannot resolve without a run admission.
6. The narrative classification decides if a readiness check is required.
   An optional check is omitted only when its MCP server is not admitted.
7. The host validates the complete plan before it starts any MCP process.
8. The public values live in `aptl.core.mcp_smoke_contract`.
   `aptl.validation.participant_mcp_smoke` re-exports them.

## Alternatives considered

| Alternative | Reason for rejection |
| --- | --- |
| Call the provider with an empty context for discovery | Discovery would run executable selection with false inputs. |
| Read addresses from Docker during resolution | Resolution would depend on runtime inspection and could select an ambiguous address. |
| Use the full MCP catalog as provider authority | The catalog is not the admitted selection of the run. |
| Add a required flag to readiness checks | The narrative already classifies each capability. A second flag could disagree. |
| Filter denied operations from a provider result | A silent filter could hide a missing required check. |
| Match readiness `operation_id` to the tool name | Existing profiles use descriptive operation IDs. The tool grant is the authority. |

## Consequences

### Positive

- An adapter can select operations from the admitted inventory and resolve targets from admitted addresses.
- Static plans keep their behavior.
- One validation gate covers static, provider, and caller-supplied plans.

### Negative

- A run admission written by an earlier release has no node inventory. A provider then fails for a missing target.
- A node without a static address gives no target.

### Neutral

- Installed providers are trusted Python code. The context is not a sandbox.
- Release qualification still requires every readiness check in the profile.
