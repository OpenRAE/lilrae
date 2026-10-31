# Appliance Network Boundary

> Current delivery scope: protected seats use
> `aptl.appliance-boundary/v3`. They retain the outer VM boundary from
> [ADR-060](../adrs/adr-060-vm-only-seat-containment.md) and add default-deny
> protection for guest-host seat components. V2 still means VM-only. The V1
> three-zone and controlled-egress sections are retained as historical design,
> not as a claim made by V3.

The appliance boundary is the reusable materialization surface for
[ADR-049](../adrs/adr-049-sealed-disposable-lab-appliance.md). It is not a
TechVault topology and it does not assign scenario roles. It consumes two
authorities without merging them:

- The admitted RAES provisioning plan owns scenario networks, node
  attachments, ACL owners, rule order, direction, endpoints, protocol, ports,
  and action.
- The signed V3 appliance policy owns protected component classes, reviewed
  range-to-guest-host exceptions, guest publications, and Docker-authority
  constraints. It does not own range networks or workloads.

The effective result is the intersection of these authorities. A policy
conflict or an observation gap fails the boundary gate; neither authority
wins through implicit precedence.

## Protected Seat Materialization

V3 protects five closed component classes: management and control, evidence
capture, evidence storage, guest Docker authority, and platform credentials.
The canonical TechVault policy grants no range-to-guest-host flow. A later
exception must name its source class, destination component, transport, ports,
purpose, and unique probe identity in the signed policy.

After the admitted range networks exist, but before any range workload starts,
the compiler resolves every network through its append-only native resource
receipt. The network helper installs separate IPv4 and IPv6 input-hook rules
for those exact bridges. Established replies to host-initiated management are
allowed; signed exceptions are allowed; all other bridge-to-guest-host traffic
is dropped. The helper adds no forward, output, NAT, or egress rules, so the
admitted range topology and range-to-range traffic are unchanged.

Fresh Docker inspection is also required. Every receipt-owned range workload
must be inspectable and must not use privileged mode, host networking, the host
PID namespace, an unadmitted Docker endpoint, protected capture/run storage, or
platform launch credentials. Device counts are recorded; exact devices,
capabilities, namespaces, and general mounts remain governed by the admitted
RAES runtime contract and its effective-model check. Exact RAES
Docker-authority admission remains necessary for an authority holder; labels
alone never authorize it.

The gate requires both independent kernel read-back and active coverage. For
every owned range network and observed address family it proves a
host-initiated connection and established reply, then proves each component
probe target ready and unreachable from a receipt-owned range namespace.
Missing, duplicate, unexpected, stale, or failed coverage is fatal.

V3 does not isolate range workloads from each other, restrict range egress,
prevent denial of service, or survive guest-root/kernel compromise. The
capture sidecar and an admitted Docker authority holder retain the authority
their explicit contracts require. The outer host, hypervisor, and other seats
remain ADR-060 concerns.

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

## Qualification And Start Gate

Image qualification and every appliance start call the same boundary gate.
For V3 the gate requires:

- the exact signed policy, payload, and RAES plan digests;
- the current boot identity and selected guest Docker daemon identity;
- a fresh authenticated outer-host observation supplied by the launcher;
- the separate RAES and seat-protection enforcement observations that the
  admitted realization requires;
- exact per-network, per-family positive and negative probe coverage;
- an exact Docker authority-holder inventory with no privileged, host PID,
  host network, device, or unapproved daemon access; and
- only the signed participant and recovery publications on the physical host.

The result is a bounded, redacted, machine-readable inventory. Missing host
evidence, stale boot identity, an incomplete scan, an unapproved listener,
rule drift, a failed probe, or an unknown Docker authority holder is fatal.
The participant surface receives only coarse readiness.

Appliance mode also binds the helper image by full `name@sha256` reference. A
missing signed helper fails readiness; the backend does not build or substitute
a mutable local tag. Developer-local RAES runs may build the checked-in helper,
but that path is not appliance evidence.

The signed image uses `aptl.seat-image/v3`, boundary policy generation 4, and
network-helper wire tag 6. An older V2 image or observation cannot satisfy this
gate. Qualification accepts only an immutable signed image digest and runs the
normal launcher, first-boot service, readiness channel, clean start, warm
restart, reset, and second clean start. The retired smoke service that disabled
first boot is not qualification evidence.

## Host MCP policy extension

[ADR-059](../adrs/adr-059-canonical-techvault-delivery-and-host-mcp-access.md)
adds `host_mcp_contract: aptl.restricted-ssh-mcp/v1` and the `host-mcp`
publication audience. Opt-in requires exactly one TCP guest publication.
A host observation must record both its outer loopback address/port and its
guest loopback address/port. Observation identities cover that mapping;
matching port numbers or a stale access file are insufficient authorization.

The restricted dispatcher verifies its signed launch, current guest boot,
Docker daemon, project and complete container IDs, active run/capture and a
management-owned boundary observation no more than five seconds old. A missing
or failed check prevents operations and closes existing connections. This does
not expose a Docker API, SFTP, SSH forwarding or an unrestricted guest shell.
