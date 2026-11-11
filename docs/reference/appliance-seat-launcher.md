# Appliance seat launcher

A seat is one disposable VM per user running the ordinary full TechVault lab,
with [VM-only containment](../adrs/adr-060-vm-only-seat-containment.md).
New images open an XFCE desktop in the browser through Guacamole. The desktop
has a browser and red/blue Claude terminals. APTL adds no participant login or
host MCP grant. Scenario services keep their own authentication.

On new images, the operator selects the guest `aptl` account's privilege mode
at seat load time. This does not change the host Unix account that launched
the seat.
Protected V3 images also default-deny ordinary range workloads from LilRAE's
guest-host management/control, evidence custody, Docker authority, and platform
credentials. This guard does not segment workloads from each other or add
controlled egress. The signed boundary policy identifies V2 VM-only seats and
V3 protected seats explicitly.

**Seats have no default outbound network controls.** The guest uses user-mode
NAT and can start ordinary internet and LAN connections, such as HTTP,
HTTPS, SSH, and other TCP/UDP traffic. The launcher adds no destination or port
allow-list and no outbound proxy. The host network, selected scenario, or an
operator's event-specific network controls may still affect connectivity.
Optional controls for future events are tracked in
[issue #1182](https://github.com/OpenRAE/lilrae/issues/1182).

Only the declared host-to-guest Guacamole port is published, inside the seat
user's private network namespace. The VM does not share the host filesystem or
Docker socket. Network services exposed by the physical host may be reachable
from the guest. This does not separate workloads inside the VM.

## Security boundary

See [why seats use a VM boundary](seat-containment.md).

## Prerequisites

See [Operate an appliance seat](appliance-seat-operations.md#prerequisites).

## Choose desktop privileges and start a seat

See [Operate an appliance seat](appliance-seat-operations.md#choose-desktop-privileges-and-start-a-seat).

## Updates are never forced

See [Operate an appliance seat](appliance-seat-operations.md#updates-are-never-forced).

## Reserving operator-selected ports

See [Operate an appliance seat](appliance-seat-operations.md#reserving-operator-selected-ports).

## Reset and recovery

See [Operate an appliance seat](appliance-seat-operations.md#reset-and-recovery).

## Participant desktop

The admitted scenario pack decides what the desktop shows. Its adapter names
the consoles, the logins, the guide and the hostnames the browser must resolve,
as references to the pack's SDL (`aptl.participant_desktop`). Lab start resolves
each reference against the admitted SDL and the running lab:

- A console URL is the authored canonical URL, or the realized published port
  under the name that the console's certificate covers.
- A login is only an authored `secret_fixture` credential from the SDL.
- A hostname maps to the address of the node's own container.

The guest sets `LILRAE_PARTICIPANT_DESKTOP_ACCOUNT=aptl`. Lab start writes the
logins, the guide and the console list into that account's
`~/.config/aptl/desktop` directory. The directory is `0700` and each file is
`0600`. Lab start keeps only the hostname list, which has no secret, in
`.aptl/participant-desktop/hosts.json`.

The shared publisher applies the hostname list to `/etc/hosts`. After readiness, the session browser opens the logins, guide, and consoles. A lab without that
variable publishes no desktop.

State defaults to the current user's private roots: `$XDG_STATE_HOME/aptl/seat`
for the seat and `$XDG_CACHE_HOME/aptl/appliance` for the image cache, or the
`~/.local/state` and `~/.cache` equivalents. `--seat-root` and `--image-cache`
remain available for managed deployments.

See [operate a seat](appliance-seat-operations.md) for launch and recovery steps.

## Directory layout

```text
~/.local/state/aptl/seat/
  seat-state.json
  vm.pid                     # PID + procfs start/executable identity
  launch/
    appliance-launch.json    # create-once launch projection
    boundary-policy.json     # the exact policy bytes the gate is bound to
  image/                     # this generation's retained disk/config/trust
  instances/
    seat-01.qcow2            # disposable overlay
    seat-01.base.qcow2       # retained immutable backing file
    seat-01.state/           # guest-only overlay identity

~/.cache/aptl/appliance/
  <digest>/seat-disk.qcow2   # shared, read-only, content-addressed
  refs/<reference>.json      # which digest each reference selects
```

## Building the image

See [Operate an appliance seat](appliance-seat-operations.md#building-the-image).

## Diagnostics

CLI failures emit bounded JSON with stable codes such as `no-kvm`, `low-disk`,
`corrupt-overlay`, `image-unavailable`, `failed-readiness`, and boundary
inventory codes. Raw QEMU/libvirt stderr, guest logs, and credentials are
never returned.

## Related documents

- [VM-only seat containment](../adrs/adr-060-vm-only-seat-containment.md)
- [Appliance network boundary](../components/appliance-boundary.md)
- [Desktop seat decision](../adrs/adr-061-gateless-vm-seat-access.md)


## Host prerequisites

The selected image declares minimum CPU, RAM, disk, and runtime reservations.
The physical host requires Linux, `/dev/kvm`, `qemu-img`, `qemu-system-x86_64`, and read-only OVMF firmware.
Desktop networking requires Bubblewrap (`bwrap`), `nsenter`, `slirp4netns`, and `/dev/net/tun`.
Acquisition and updates require Cosign.
Seat operations do not require host Docker.

The account used to start the seat must have read/write KVM access.
A `kvm` group change normally requires another login session.
Prerequisite failures are reported together in one bounded error.
State belongs to the private roots of the user who starts the seat. No shared `seat-state` directory is required.

## Desktop privilege modes

| Mode or input | Contract |
| --- | --- |
| `event` | Guest `aptl` has no sudo authorization or Docker-group membership. Root-owned first boot starts the lab and desktop. |
| `administrative`, nonempty password | The given password becomes the guest sudo and xrdp password. Docker administration uses sudo, without Docker-group membership. |
| `administrative`, empty password | Sudo is passwordless. The browser desktop keeps a nonempty generated xrdp password. |
| `--sudo-password-file` | Accepted only for administrative first start. The file must be private and owned by the user who starts the seat. Zero bytes select passwordless sudo. |
| Warm restart | A warm restart keeps the generation's mode and password without another prompt. |
| Older image digest | An older image keeps its signed privilege behavior and does not accept a new desktop mode. Update and reset are explicit. |

The mode changes the guest account, not the physical host account.
First boot receives the password over a private VM channel before xrdp starts.
It is absent from the image, command arguments, environment variables, launch descriptor, and host seat record.
Reset is required to change the generation's mode or password.

`seat rescue` requires a stopped VM and a host administrator with `virt-rescue`.
It holds the lifecycle lock and opens the overlay as its host owner.
It gives the participant account no administrative grant.

## Image selection and verification

Selection order is `--image` or `APTL_SEAT_IMAGE`, `seat.image`, the existing seat source, then the default GHCR channel.
`seat.public_key` selects an alternate trust key.
An alternate source does not use the default as a fallback.
Trust keys are scoped to the selected repository.
Keys or credentials inside a downloaded image do not establish publisher trust.

The first acquisition asks before registry lookup or download.
If the operator declines, presses Enter, or gives no stdin, the launcher leaves the image and seat unchanged.
`--yes` or `-y` explicitly approves acquisition for automation.
Registry login and host Docker are unnecessary.

Cosign verifies the immutable OCI manifest against the bundled publisher key.
The launcher compares configuration and disk bytes with their signed digests.
Missing Cosign, missing trust keys, invalid signatures, or corrupt images prevent startup.
Transparency-log checks remain enabled.

An image reference keeps its selected digest until explicit replacement.
Warm startup uses verified local bytes without registry access.
A missing or corrupt selection reports an error. The launcher does not download another image.
A new tag does not change an existing seat.

A running VM refuses replacement.
Download, signature, or host-admission failure keeps the old selection and overlay.
Successful replacement resets the stopped seat to a new generation and removes the superseded cache entry.
Other seats keep their immutable disks, configurations, and verification records for offline restart.

`seat update --to sha256:<disk-digest>` requires a retained verified disk under the same repository and trust key.
Otherwise the launcher must acquire the intended immutable reference again for rollback.
A pinned reference remains pinned until explicitly changed.

## Port mappings and capacity

Each `--mapping` has six fields in this order:

| Field | Meaning |
| --- | --- |
| Audience | Publication audience, such as `participant`. |
| Protocol | Declared transport, such as `tcp`. |
| Outer address | Host-side publication address. |
| Outer port | Host-side publication port. |
| Guest address | Destination address inside the guest. |
| Guest port | Fixed port declared by the image. |

Duplicate outer endpoints, missing mappings, and undeclared destinations prevent staging.
Startup cannot change a staged mapping. Reset creates a new generation.
Automatic port selection and capacity admission are serialized across launchers.

Each QEMU seat records CPU, RAM, and disk reservations in a fixed `fw_cfg` argument.
The allocator sums visible reservations before it starts another seat.
It also keeps memory headroom of at least 8 GiB or 10% of physical RAM, whichever is greater.
Insufficient capacity prevents launch.

Readiness requires matching QEMU identity, forbidden-reachability probes, guest boot/daemon observations, and the complete boundary gate for that generation.
A live PID or listener is insufficient.
`seat status` exposes coarse health without credentials.

## Desktop endpoints

`seat open-kiosk` opens `http://127.0.0.1:<selected-port>/` inside the user's private network namespace.
An ordinary host browser cannot reach that listener directly.
Guacamole establishes its internal identity and opens the overlay's single xrdp connection.
There is no more LilRAE participant login or bootstrap file.

New desktop images grant no host MCP key, expiring transport grant, or host client configuration.
Provider authentication stays with the guest user.
Scenario applications keep their own authentication.
`lilrae lab info` reports their observed endpoints and credential-file locations.

The portal's authored login is `http://172.20.1.20:8080/login`.
MISP uses `https://misp.techvault.local/`.
The desktop resolves authored names to the admitted containers and trusts the generated scenario CAs.
Wazuh uses `https://wazuh.dashboard:<port-from-lab-info>` for certificate hostname agreement.

## Image build and publication contracts

The build requires KVM, `libguestfs-tools`, QEMU, Docker, Node 22, Python 3.14, `uv`, and an installed environment at `.venv/bin/python`.
Disk capacity must hold source, image archive, expanded guest, and compressed output together.
`APTL_SEAT_LIBGUESTFS_SUDO=1` permits sudo for libguestfs operations when host kernel files require it.
The disk defaults to 128 GiB. `APTL_SEAT_DISK_GIB` selects another virtual capacity.
Admission uses virtual capacity, not compressed size.

The build uses the Ubuntu digest in `scripts/appliance/seat-base-image.env`.
It builds project, Guacamole, and MCP assets and stages the complete admitted TechVault image closure.
The desktop and provider runtime use hash-locked offline installation.
Guest sanitization and scanning precede launch-configuration output.
Participant boot loads local images and starts the ordinary admitted lab without image pulls.

`seat-build.json` binds source revision, disk, and configuration bytes.
Dirty builds are diagnostic artifacts and cannot be published.
Changed output bytes also fail publication.
This record is not a SLSA provenance attestation.

Publication requires ORAS, Cosign, an authorized GHCR write token, and the private key matching the CLI's publisher anchor.
Signing material must stay outside tracked source and the guest payload.
Encrypted file keys use `COSIGN_PASSWORD`.
The publisher isolates registry login from the operator's Docker configuration.
No registry token or signing key enters the image.

Publication writes disk/configuration by content identity and verifies anonymous access, the manifest signature, and immutable reference.
`APTL_SEAT_IMAGE_TAG` can add an immutable readable tag.
`APTL_SEAT_PUBLISH_LATEST=1` selects public-channel publication after qualification.
Anonymous checks try at most three times and stop immediately on HTTP 401 or 403.
A new image build does not repair registry permissions or a broken tag.

The historical issue #1127 checklist names TheHive.
ADR-063 removes TheHive and Cortex, so current qualification must record the admitted pack and disclose that difference.
A publisher signature proves authorization. The separate live record proves only the operations actually observed.
