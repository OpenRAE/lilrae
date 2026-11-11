# Network Architecture

LilRAE separates scenario topology from deployment transport.
The compiled SDL infrastructure plan determines the scenario's networks, addresses, and node attachments.
Typed backend operations realize those declarations.
A fixed root Compose network block cannot replace an admitted plan.
[ADR-046](../adrs/adr-046-dynamic-raes-scenario-realization.md) records this ownership decision.

## Networks

The [root Compose topology reference](../reference/compose-topology.md#networks) lists the four compatibility network declarations.
They separate security services, DMZ targets, internal targets, and the red-team workstation.
Those names and subnets do not impose a topology on another Scenario Pack.

## Container IPs

The [address tables](../reference/compose-topology.md#container-ips) describe root declarations, including compatibility stubs.
The admitted scenario and runtime observations determine actual addresses.
A stub's image field does not identify the substrate used for generic realization.

### Security Network (172.20.0.0/24)

The [security address table](../reference/compose-topology.md#security-network-172200024) owns these compatibility declarations.

### DMZ Network (172.20.1.0/24)

The [DMZ address table](../reference/compose-topology.md#dmz-network-172201024) owns these compatibility declarations.

### Internal Network (172.20.2.0/24)

The [internal address table](../reference/compose-topology.md#internal-network-172202024) owns these compatibility declarations.

### Red Team Network (172.20.4.0/24)

The [red-team address table](../reference/compose-topology.md#red-team-network-172204024) owns these compatibility declarations.

## Multi-Homed Containers

Several declared services attach to more than one network.
Wazuh Manager collects logs across zones.
Suricata observes traffic through its attached interfaces.
DNS serves multiple zones, and the web application connects its DMZ and internal interfaces.
Kali's compatibility attachments include both DMZ and internal networks.
This topology does not require a DMZ compromise before Kali reaches internal targets.

## Host Port Mappings

The [publication reference](../reference/compose-topology.md#host-port-mappings) lists default host ports and override variables.
SOC management publications bind to loopback.
Loopback binding limits network exposure; it does not authenticate a local caller.
The [web reference](../reference/web.md) describes the web control plane's separate authentication checks.

The victim and Kali stubs publish no host ports.
Supported access uses admitted operator relays, MCP, or the existing container-shell interface.
[Kali operations](../components/kali-operations.md) describes the capture boundary and shell restrictions.

## Internal Communication

Wazuh collects agent and syslog traffic and sends indexed events to its Indexer.
The Dashboard queries the Indexer.
Suricata produces Eve JSON for the configured collection path.
The source configuration determines each transport's authentication and TLS behavior.
[ADR-034](../adrs/adr-034-lab-managed-soc-tls-ca.md) explains the lab CA and its Wazuh exception.
Network segmentation does not mean that all internal traffic is unencrypted.

## Network Isolation

Docker bridge networks separate attachments and provide the declared network transport.
They do not provide the VM containment required for a disposable seat.
[ADR-060](../adrs/adr-060-vm-only-seat-containment.md) explains that separate host boundary.
A published port, shared daemon, or multi-homed node has its own security implications.

## Egress Controls (SAF-002)

The root DMZ, internal, and red-team networks declare `internal: true`.
The security network does not.
The internal flag restricts external connectivity through that network.
It is not a complete policy for a node with another external attachment.

An authored RAES network carries its own `internal` property.
Backend realization must preserve that property.
Correct root Compose declarations cannot compensate for an incorrectly realized dynamic network.

### Multi-homed container egress

A node attached to an external security network can retain an external path.
DNS, Wazuh Manager, and Suricata have such compatibility attachments.
An internal attachment alone cannot prove that the whole node has no egress.

### Host port mappings

Internal-network policy and host port publication are separate controls.
The realized backend and host determine the effective reachability.
A successful configuration check does not replace installed network qualification.

### Package pre-installation

Internal-only nodes cannot depend on runtime internet downloads.
The selected substrate and authored software must satisfy their installation requirements.
Older Wazuh and Falco install scripts can attempt downloads when packages are absent.
Their fallback cannot establish readiness on a network without external access.

### Upgrading from pre-SAF-002 deployments

Docker cannot change a network's internal flag in place.
Network replacement requires the supported lab lifecycle and its ownership checks.
The [deployment guide](../deployment.md) describes stop, reset, and startup operations.
Direct Compose teardown is not the generic scenario recovery procedure.
