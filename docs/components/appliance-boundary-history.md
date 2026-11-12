# Historical V1 appliance boundary

> Source record: This record comes from revision `28fc8f18` (2026-11-06).
> This record describes historical V1 design, separate from current V3 delivery.
> See the [current boundary reference](appliance-boundary.md).

## Historical V1 Materialization

RAES ACLs pass through `AptlRealization`, `DeploymentRealizationSpec`, and the
typed `DeploymentBackend` boundary. The Docker backend binds each RAES
network and ACL owner to an observed bridge and address. It then installs a
project-owned nftables table for the RAES authority. Node and network owners,
authored order, `in`, `out`, `inout`, `allow`, `deny`, TCP, UDP, ICMP, and
protocol-independent rules remain distinct.

The supported ACL subset resolves named endpoints to exact IPv4 networks and
preserves an authored omitted endpoint as RAES `any`, still scoped by the ACL
owner. Unresolved networks, IPv6 endpoints, invalid port combinations,
ambiguous owners, and malformed direct plans fail before native mutation.
IPv6 remains default denied at the platform floor until dual-stack crossing
realization is supported.

The signed platform policy uses exact Docker label selectors for three
distinct platform networks and three exact workload anchors. Scenario
networks that do not carry those signed selectors are excluded from the
platform table. This prevents the platform implementation from becoming a
second authority for red, blue, or target topology.

A participant or egress gateway may be multi-homed only across those three
selected platform networks. A fixed crossing is emitted only when its exact
source and destination anchors share an observed platform path. External
egress is still authorized solely from the egress anchor's separately signed
egress-side network.

Both authorities use separate nftables tables. Replacement is one native
transaction. Readback checks table ownership, policy digest, chain hooks,
priority, default policy, and every expected rule identity. A missing,
changed, or extra owned rule is fatal.

[Base-container-materialized nodes](node-realization.md) are created on their first declared RAES network and attached
to all remaining declared networks before they start. There is no temporary
Docker default-bridge or package-install egress window.

## Historical V1 Participant Workbench

The [participant workbench](participant-workbench.md) remains the source of
the closed workbench launch contracts. The boundary does not copy that
profile model or infer a profile from a scenario name. The canonical full-TechVault participant profile composes `red` and `blue`.
The historical guided fixture remains separate.

The appliance payload places the participant browser gateway on the signed
participant anchor and the installed agent and selected MCP processes on the
signed management anchor. Fixed platform crossings authorize only the
required participant-to-management and management-to-egress services.
Profile-specific MCP destinations remain the typed, released server
inventories from `aptl.workbench`; RAES remains authoritative for the
scenario-side endpoints those servers use.

The participant-profile manifest, asset lock, and qualification report are
independent signed-payload inputs. Issue #823 binds those #820 outputs together
with this boundary policy and its helper/proxy image identities. The boundary
therefore validates the shared workbench policy version and observed placement,
but it does not duplicate the participant profile's capability inventory,
resource budgets, or readiness suite.

## Historical V1 Controlled Egress

External access uses the dedicated egress anchor. Management can reach the
egress service only through a declared fixed crossing. The egress firewall
drops private, loopback, link-local, carrier-grade NAT, benchmark, multicast,
reserved, and metadata destinations before allowing the declared upstream
TCP ports.

The CONNECT broker receives a narrow projection of the signed exact DNS
authorities and ports. It rejects IP literals, wildcard names, URLs,
unapproved ports, redirects that do not create a new CONNECT request, empty
DNS results, and any DNS result set containing a non-global address. IPv4
addresses embedded through IPv4-mapped IPv6 or well-known NAT64 are checked
the same way. Signed bounds cap concurrent connections, header size, header
wait, upstream connect time, and tunnel idle time.

An unavailable proxy, failed DNS lookup, unsafe DNS answer, timeout, refused
upstream, policy mismatch, or missing firewall readback denies the request.
There is no direct DNS, DoH, QUIC, UDP, or arbitrary Internet fallback.
Version 1 admits TCP CONNECT authorities only. Browser, update, and
model-provider exceptions must be exact signed authorities and must pass
qualification probes. Participant processes do not receive direct NTP
egress; appliance time comes from the sealed guest and outer lifecycle. A
future external time service requires a new typed policy and enforcement
version rather than a port-only exception.
