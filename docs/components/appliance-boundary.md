# Appliance Network Boundary

> Current delivery scope: protected seats use
> `aptl.appliance-boundary/v3`. They keep the outer VM boundary from
> [ADR-060](../adrs/adr-060-vm-only-seat-containment.md) and add default-deny
> protection for guest-host seat components. V2 still means VM-only. The V1
> three-zone and controlled-egress sections remain historical design,
> not as a claim made by V3.

The appliance boundary is the reusable materialization surface for
[ADR-049](../adrs/adr-049-sealed-disposable-lab-appliance.md). It is not a
TechVault topology and it does not assign scenario roles. It consumes two
authorities. It does not merge them:

- The admitted RAES provisioning plan owns scenario networks, node
  attachments, ACL owners, rule order, direction, endpoints, protocol, ports,
  and action.
- The signed V3 appliance policy owns protected component classes, reviewed
  range-to-guest-host exceptions, guest publications, and Docker-authority
  constraints. It does not own range networks or workloads.

The effective result is the intersection of these authorities. A policy
conflict or an observation gap fails the boundary gate. Neither authority
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
for those exact bridges. The helper permits established replies to host-initiated management and signed exceptions.
It drops all other bridge-to-guest-host traffic. The helper adds no forward, output, NAT, or egress rules, so the
admitted range topology and range-to-range traffic are unchanged.

Fresh Docker inspection is also required. Every receipt-owned range workload must be inspectable. It must not use privileged mode, host networking, or the host PID namespace. It must not use unadmitted Docker endpoints, protected capture/run storage, or platform launch credentials. The inventory records device counts.

Exact devices,
capabilities, namespaces, and general mounts remain governed by the admitted
RAES runtime contract and its effective-model check. Exact RAES
Docker-authority admission remains necessary for an authority holder. Labels
alone never authorize it.

The gate requires both independent kernel read-back and active coverage. For each owned network and observed address family, the gate proves a host-initiated connection and established reply. It then proves each component probe target ready and unreachable from a receipt-owned range namespace.
Missing, duplicate, unexpected, stale, or failed coverage fails the gate.

V3 does not isolate range workloads from each other, restrict range egress,
prevent denial of service, or survive guest-root/kernel compromise. The
capture sidecar and an admitted Docker authority holder keep the authority
their explicit contracts require. The outer host, hypervisor, and other seats
remain ADR-060 concerns.

## Historical V1 Materialization

See the [V1 source record](appliance-boundary-history.md#historical-v1-materialization).

## Historical V1 Participant Workbench

See the [V1 source record](appliance-boundary-history.md#historical-v1-participant-workbench).

## Historical V1 Controlled Egress

See the [V1 source record](appliance-boundary-history.md#historical-v1-controlled-egress).

## Qualification And Start Gate

Image qualification and every appliance start call the same boundary gate.
For V3 the gate requires:

- the exact signed policy, payload, and RAES plan digests.
- the current boot identity and selected guest Docker daemon identity.
- a fresh authenticated outer-host observation given by the launcher.
- the separate RAES and seat-protection enforcement observations that the
  admitted realization requires.
- exact per-network, per-family positive and negative probe coverage.
- an exact Docker authority-holder inventory without privileged mode, host PID/network use, devices, or unapproved daemon access.
- only the signed participant and recovery publications on the physical host.

Ordinary range workloads have a separate inspection contract.
Their device and capability use must match the admitted RAES runtime contract.
The result is a bounded, redacted, machine-readable inventory.
Missing or stale host evidence, an incomplete scan, or an unapproved listener fails the gate.
Rule drift, a failed probe, or an unknown Docker authority holder also fails the gate.
The participant surface receives only coarse readiness.

Appliance mode also binds the helper image by full `name@sha256` reference. A
missing signed helper fails readiness. The backend does not build or substitute
a mutable local tag. Developer-local RAES runs may build the checked-in helper,
but that path is not appliance evidence.

The signed image uses `aptl.seat-image/v3`, boundary policy generation 4, and
network-helper wire tag 6. An older V2 image or observation cannot satisfy this
gate. Qualification accepts only an immutable signed image digest. It exercises the normal launcher, first-boot service, readiness channel, clean start, warm restart, reset, and second clean start. The retired smoke service that disabled
first boot is not qualification evidence.

See [qualify an appliance boundary](appliance-qualification.md) for the procedure.

## Host MCP policy extension

[ADR-059](../adrs/adr-059-canonical-techvault-delivery-and-host-mcp-access.md)
adds `host_mcp_contract: aptl.restricted-ssh-mcp/v1` and the `host-mcp`
publication audience. Opt-in requires exactly one TCP guest publication.
A host observation must record both its outer loopback address/port and its
guest loopback address/port. Observation identities cover that mapping.
Equal port numbers or a stale access file are insufficient authorization.

The restricted dispatcher verifies its signed launch, current guest boot, Docker daemon, project, complete container IDs, and active run/capture. It also requires a management-owned boundary observation no more than five seconds old. A missing
or failed check prevents operations and closes existing connections. This does
not expose a Docker API, SFTP, SSH forwarding or an unrestricted guest shell.
