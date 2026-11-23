# Host Requirements

This reference lists host requirements for the released CLI and scenario runtime.
Use [Prepare the lab host](prerequisites.md) for installation tasks.

## Tools And Resources

| Item | Requirement |
| --- | --- |
| Python | `>=3.14,<3.15` for the current CLI |
| Docker Engine | 28.0 or newer, rootful, cgroup v2 |
| User namespaces | No `userns-remap` for scenarios with systemd nodes |
| Compose | 2.0 or newer; emitted `!reset` or `!override` requires 2.24.4 or newer |
| Buildx | Available to the selected Docker client |
| OpenSSH | `ssh-keygen` on `PATH` |
| Node.js | 22.23.4+, 24.22.1+, or 26.12.1+ within those release lines |
| npm | Available for MCP builds |
| Git | Required for source development; released installation needs no clone |
| Full TechVault RAM | More than 20 GB |
| Disk | At least 20 GB; reserve additional space for images, builds, and evidence |

Systemd nodes need a writable cgroup filesystem.
Startup uses Engine's `writable-cgroups=true` option instead of a privileged fallback.
Missing MCP build tools can leave startup degraded.
`lilrae doctor` reports engine memory but does not enforce a scenario memory minimum.

## Qualification Records

The [September 20 candidate QA](../testing/issue-956-candidate-254bc40f-manual-qa.md) tested one Ubuntu 24.04 x86_64 host.
It used Python 3.12.3, Engine 29.5.0, and Compose 5.1.3.
Those historical versions do not replace the current package requirements.
Wheel installation, source installation, full-TechVault startup, and live gates passed for that candidate.
The record did not pair the daemon kernel with the host kernel.
It therefore does not qualify native host containment.

The [one-host KVM acceptance](../reviews/1162-seat-acceptance.md) used eight vCPUs, 32 GiB RAM, and a 128 GiB disk.
It checked a signed V2 image, guest startup, authenticated MCP access, offline restart, and scoped stop.
Exact host OS, kernel, and QEMU versions were not recorded.
Independent-machine qualification was absent.
These results do not qualify every seat version or host.

No exact full-TechVault and containment matrix is recorded here for Docker Desktop, Colima, or Windows.
See [Execution boundaries](execution-boundaries.md) for the meaning of boundary observations.
