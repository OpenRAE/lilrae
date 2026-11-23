# Execution Boundaries

LilRAE runs intentionally vulnerable workloads and agent tools.
The selected Docker transport determines where containers run.
It does not, by itself, establish containment.
Use an approved isolated VM or a dedicated lab machine for exercises.
The developer workstation is limited to source edits, static checks, and Git work.

## Docker Observations

`lilrae lab start` and `lilrae lab info` report the selected transport and observed host boundary.
`native-docker` means the local daemon kernel matched the CLI host during observation.
`docker-vm-unverified` describes a VM runtime without containment qualification.
Unreadable, changed, conflicting, or remote endpoints can produce limited or unknown observations.
These labels do not prove isolation of ports, devices, egress, credentials, or other resources.

Native Docker workloads can affect the selected daemon host.
A Docker socket mount gives root-equivalent authority over that daemon.
Project files can be mounted into workloads, and services can publish host ports.

Docker Desktop and Colima place the daemon in a VM.
The physical host still runs the CLI and holds project credentials.
Published ports and shared files can cross the VM boundary.
A remote daemon publishes ports on its own host; those ports need separate reachability checks.

## Disposable Seats

A [disposable KVM seat](../reference/appliance-seat-launcher.md) places Docker and the lab inside an outer VM.
The host needs `/dev/kvm` and reserved CPU, memory, and disk.
Desktop seats also need `bwrap`, `nsenter`, `slirp4netns`, and `/dev/net/tun`.
Declared host-to-guest mappings bind to loopback.
Neither containers nor a VM provide an absolute sandbox.

V3 seats deny ordinary range workloads access to named management, evidence, Docker-authority, and platform-credential components by default.
That claim requires the exact signed policy and fresh kernel, daemon, workload, and probe evidence on every start.
It excludes guest root or kernel compromise, shared-guest denial of service, and compromise of an admitted Docker-authority holder.
It adds neither internal range segmentation nor default-deny guest egress.
See the [appliance boundary](../components/appliance-boundary.md).

A required containment profile fails when its evidence or required outer boundary is unavailable.
An unreadable endpoint, unverified signed launch, unavailable KVM, or missing host observation cannot satisfy that requirement.
Direct `lilrae lab start` does not create a seat.
A scenario's own VM node is also separate from the outer seat VM.

## Evidence Limits

The [qualification records](host-requirements.md#qualification-records) describe exact historical trials.
A signed image establishes identity; a successful boot establishes operation.
Neither proves freedom from VM escape.
Keep the host kernel and hypervisor current, and control the surrounding network.
