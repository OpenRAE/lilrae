# Why seats use a VM boundary

This Explanation describes the containment decision and its limits.
See the [seat reference](appliance-seat-launcher.md) and [operating guide](appliance-seat-operations.md).

## Security boundary

A seat places the rootful Docker daemon, vulnerable workloads, and Docker-authorized control components inside one disposable VM.
KVM/QEMU adds a boundary before an ordinary container compromise reaches the physical host or another seat.
Direct `lilrae lab start` instead uses the selected host Docker engine.

QEMU runs in a rootless network namespace. The Unix account that starts QEMU owns that namespace.
`slirp4netns` gives outbound connectivity.
The declared Guacamole listener is reachable through that private namespace.
Other local accounts cannot enter it through ordinary account access.
Processes under the same account share that account's seat access.

`lilrae seat open-kiosk` launches a browser inside the namespace.
It adds no LilRAE participant login.
Guacamole, guacd, PostgreSQL, and xrdp have no separate host port mappings.
The overlay contains generated gateway and xrdp credentials.

## Limits of the outer boundary

A VM boundary reduces risk. It does not prove that escape is impossible.
An exploit chain can target the guest kernel, emulated devices, QEMU, KVM, or host kernel.
A flaw in those layers can permit escape.

Operators should keep the virtualization stack patched and use a dedicated, rebuildable host.
They should avoid unnecessary devices and host mappings, keep unrelated secrets elsewhere, restrict the network around the host, and monitor sessions.
These measures support the boundary. They do not prove absence of escape paths.

## Limits inside the guest

All TechVault workloads share the guest kernel.
V3 blocks ordinary workloads from protected guest-host components and rejects unadmitted authority, mounts, and platform credentials.
It does not contain guest-root/kernel compromise or an admitted Docker-authority holder.
A compromise can still affect other range containers and scenario content.

Reset destroys the overlay and revokes the previous generation.
It cannot restore trust in a compromised physical host.
V3 does not add range-to-range segmentation or controlled egress.

## Qualification evidence

The [one-host acceptance record](../reviews/1162-seat-acceptance.md) covers its exact signed image and observed operations.
It does not establish every supported host profile or independent-machine qualification.
Only the outer launcher can observe and qualify the physical host for a generation.
An in-guest Docker observation does not give that evidence.
See [tested profiles and limits](../getting-started/prerequisites.md#tested-execution-profiles-and-limits).
