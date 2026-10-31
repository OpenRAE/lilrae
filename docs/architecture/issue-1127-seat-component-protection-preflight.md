# Issue #1127 Seat Component Protection Preflight

This note fixes the architecture boundary for issue #1127. It is design
guidance, not an implementation plan. The issue remains the delivery contract.
No new ADR is needed: [ADR-060](../adrs/adr-060-vm-only-seat-containment.md)
already assigns inner-seat protection to #1127, and the existing signed
appliance-boundary contract is the correct owner.

## Decision

Add a new, signed appliance-boundary policy version for **seat-component
protection**. It is distinct from both existing meanings:

- `aptl.appliance-boundary/v1` is the withdrawn three-zone design. It must not
  be revived: it confused scenario networks with platform zones and changed
  valid TechVault traffic.
- `aptl.appliance-boundary/v2` proves VM-only seat containment. It must continue
  to mean exactly that and must never imply protection inside the guest.
- The new version must mean that ordinary range workloads are default-denied
  from LilRAE's guest-host control surface, Docker authority, credentials, and
  evidence custody, subject only to explicit, typed flows in the signed policy.

The protection is a platform guard around the range, not segmentation within
the range. It must not classify red, blue, target, Shuffle, TheHive, or any
other scenario node as a LilRAE management zone. RAES and the admitted SDL
remain the sole owners of range topology and range-to-range policy.

The new policy version and an increased policy generation are sufficient to
separate protected seats from VM-only seats. The existing signed seat image
configuration, launch-descriptor digest, guest readiness challenge, and
per-start boundary gate already bind that policy to the immutable image and
the running seat. Do not bump the seat-image or launch-descriptor schema merely
as a label; bump either only if its own wire shape changes. A v2 observation
must not be accepted as evidence for the new protection.

`PlatformBoundarySpec` and `PlatformBoundaryBootstrapSpec` are legacy v1
three-zone enforcement records. Do not change their meaning or stretch their
`platform` payload into a host-input guard. Compile the new policy into a
distinct, tagged variant inside the existing `BoundaryEnforcementSpec` and
network-helper wire contract. This preserves one compiler/apply/receipt
pipeline without making old signed payloads acquire a new meaning.

## Threat Model And Components

Assume an attacker has arbitrary code execution, including container root, in
an ordinary range workload. It can originate arbitrary traffic, alter its own
network namespace within its admitted capabilities, inspect its own files and
environment, and try to reach guest-host listeners, Docker control endpoints,
mounted credentials, and evidence. Missing or unreadable enforcement state is
a failure, not evidence of safety.

| Protected component | Canonical owner | Required boundary |
| --- | --- | --- |
| Seat management and control | Guest first-boot service, seat launcher, signed launch/readiness channel, Compose backend | Range workloads cannot reach guest-host control listeners or mutate control state. Host-initiated management and its established replies remain possible. |
| Evidence capture | Admitted capture apparatus and capture coordinator | Only the admitted capture path receives participant sessions or telemetry. Its authority, credentials, and capture volume are not exposed to ordinary workloads. |
| Evidence storage | `LocalRunStore`, evidence coordinator/content store, and backend export path | No run-store path or capture volume is mounted into an ordinary workload; exports retain existing custody, sealing, path-safety, and redaction checks. |
| Guest Docker authority | Selected guest daemon plus exact admitted authority holder | No ordinary workload receives a socket, remote daemon route, equivalent host bind, or implicit proxy. Each exception is exact, graph-derived, daemon-bound, observed, and signed. |
| Credentials | Generated artifacts, owner-only environment files, capture key material, and desktop credential store | Secrets reach only their declared consumer by the existing generated-artifact or environment binding. They never become firewall-policy values, labels, process arguments, logs, or inventory evidence. |

Platform/control/capture credentials are protected components. An SDL
`secret_fixture` is scenario content and remains under scenario admission; it
must not be silently reclassified as a platform credential or copied into the
platform policy.

The current capture sidecar deliberately shares Kali's network namespace and
owns the participant SSH broker. That permitted ingress is protected by the
existing capture admission, broker authority, private keys, isolated capture
volume, and export reconciliation. It is not a reason to open a generic
range-to-guest-host port. Likewise, the guest loopback desktop proxy is a
participant publication, not a range management endpoint.

The admitted Shuffle Orborus Docker socket is the current exceptional Docker
authority. A raw Docker daemon endpoint is guest-root-equivalent; read-only
mount syntax does not attenuate it. The design can prove that only the exact
admitted holder has it, but cannot claim containment after that holder is
compromised. Other optional profiles, including a web API with Docker access,
must not be admitted silently.

This protection does not claim resistance to a guest-kernel or guest-root
compromise, an administrative desktop user with `sudo`, the hypervisor or
physical host, another seat, or resource exhaustion in the shared guest.
ADR-060 owns host/seat containment. Participant privilege is a separate
contract. Availability isolation needs a separate resource-control design.

## Enforcement Boundary

The platform policy has three cooperating enforcement surfaces. Passing only
one of them is not sufficient.

### Range-to-guest network guard

Install a default-deny guard for traffic entering the guest host from every
bridge owned by the admitted range realization. It must be active before any
range workload starts. The guard may allow only typed, reviewed guest-host
flows and stateful replies required by host-initiated management.

The guard must act on the guest-host input path. It must not filter forwarding
between range workloads, rewrite the admitted networks, or restrict range
egress; doing so would change the SDL. It must not select all Docker bridges,
because the separate seat-desktop Compose project is platform support rather
than range content. Interface ownership must come from the admitted
project/attempt realization and live native runtime observations. Reuse
`WorkspaceOwnership` and its append-only `ResourceReceipt` records, then match
their native network IDs to the selected daemon. Names and labels remain
discovery hints only; source IP addresses and hard-coded TechVault subnets are
not authority.

The existing network-boundary helper remains the only rule installer. Its
atomic apply, independently parsed closed wire shape, owner/authority table,
bounded invocation, and fresh `nft -j` read-back must be extended for the new
policy. The helper image tag is a wire-contract version and must change when
that payload changes. Core validation and helper validation are intentional
defence in depth across a process/container trust boundary; update both, but
do not introduce a third firewall schema or accept generic rule text.

Both address families and the exact supported Docker/nftables versions must be
qualified. Do not assume that a rendered rule or a successful command proves
the effective hook, priority, interface set, or packet path.

### Authority, mounts, and credentials

Retain exact Docker authority admission through the existing RAES graph,
selected endpoint binding, daemon identity, native container ownership, and
holder observation. Extend the same fatal observation boundary to every range
workload for privileged mode, host networking, host PID namespace, devices,
Docker sockets or remote daemon endpoints, sensitive or broad host binds, and
protected named volumes. An unknown or uninspectable effective value is fatal.

RAES runtime admission and seat protection are independent authorities. A
graph-authored Docker or mount requirement is necessary for realization, but
does not by itself grant access to a protected seat component. Effective state
must satisfy both the admitted realization and the signed seat policy. The
generic base substrate's exact cgroup namespace, cgroup bind, capability, and
seccomp requirements therefore need typed, observed exceptions; neither a
blanket ban nor “inside a VM” is a valid shortcut.

This is effective-runtime verification, not a second Compose policy language.
Desired Compose is an input; daemon inspection, endpoint identity, mount and
namespace read-back are the evidence. Labels are not authority. Credentials
remain in the existing generated-artifact and environment machinery, with
owner-only files and placeholder rejection. The signed boundary policy carries
non-secret component classes, selectors, protocols, ports, and purposes only.

### Evidence custody

Reuse the capture registry/specification, capture admission and apparatus,
broker, coordinator, content store, and `LocalRunStore`. The range boundary
observation may consume their normalized ownership facts; it must not copy
their schemas or invent a parallel evidence repository. In particular, a
run-store directory must never be mounted into the range, and the capture
volume and private keys must remain exclusive to the admitted apparatus.

Network policy alone cannot isolate components that share a network namespace.
The Kali/capture relationship therefore needs mount, credential, authority,
and export evidence as well as network evidence.

## Signed Evidence And Qualification

The existing fatal appliance-boundary gate remains the single decision point
for image qualification and every seat start. The boundary policy, realized
payload, plan, helper image digest, selected daemon, boot identity, host
observation, and guest observation remain one `ApplianceBoundaryBinding`.
Extend that contract for the new containment meaning; do not add a second gate
or an optional `protected=true` flag that an old observation can satisfy.

Keep artifact identities exact through that binding. The current launch path
projects `SeatImageBinding.raes_plan_digest` through a field named
`participant_routes_digest`, then reads it back as a RAES plan digest. A route
projection and the admitted RAES infrastructure plan are different artifacts.
Carry the actual admitted plan digest under its own versioned field, with one
producer and no relabelling or second compilation. Likewise,
`raes_boundary_required` must derive from the admitted realization/plan, not
from the appliance policy's legacy `internal_zone_isolation` property. Host
boot, guest boot, seat instance/generation, selected daemon, and process start
identity remain separate facts whose association is authenticated by the
existing launch/readiness chain.

Each start needs fresh kernel and daemon read-back tied to the current signed
policy, launch descriptor, boot identity, selected daemon, and readiness
challenge. Cached image qualification can establish image provenance, but it
cannot replace per-boot evidence.

The probe contract must be coverage-based rather than “at least one positive
and one negative probe”:

- every allowed flow class has a positive probe from its real source context;
- every admitted range bridge or signed rule-equivalent source class has a
  negative probe to every applicable protected component/listener class from
  an ordinary range workload namespace;
- the target listener or instrument is independently proved ready immediately
  before a negative probe, so connection failure cannot mean “nothing was
  listening”;
- probe identities and expected coverage derive from the signed policy, and
  duplicate or missing coverage is fatal; and
- rule read-back and active probes are both required.

The inventory must authenticate every field used in its verdict, including
completeness and expected coverage. Planned endpoints, a stage-time record, or
a manufactured successful reachability result are intent, not observation.
Host exposure remains under the existing fresh host observation; this issue
does not redesign that outer boundary. Issue #1127 also adds no egress
filtering and must make no egress-protection claim. If a signed policy selects
egress control now or later, unsupported or unreadable egress enforcement
still fails the same APP-1 gate closed.

Qualification must use the real signed launcher, first-boot service, readiness
channel, and immutable candidate image. A smoke image that disables first boot
or substitutes a test service cannot prove this property. The existing
installed TechVault verification and journey owners must supply the clean-seat
attack, detection, Shuffle, TheHive, repair, and retest evidence; do not create
a second journey schema or hard-code those product names into boundary policy.

[ADR-063](../adrs/adr-063-remove-thehive-and-cortex.md) now directs removal of
TheHive and Cortex, while #1127's supplied acceptance contract still names
TheHive. No protected-seat implementation can truthfully produce current
TheHive evidence after that removal is adopted. Qualification records must name
the exact admitted TechVault pack and disclose the omitted case-management step
rather than substituting another product or claiming that step passed. The
protection model remains product-neutral so pack changes affect qualification
content, not the security architecture.

## Existing Contracts To Reuse

| Concern | Canonical incumbent and required use |
| --- | --- |
| Signed policy and strict shape | `src/aptl/core/appliance_boundary.py` and `src/aptl/appliance/policy.py`; strict, extra-forbidden versioned models and canonical digest, with no permissive legacy default. |
| Realization authorities | `BoundaryEnforcementSpec`, `AcesBoundarySpec`, `DeploymentRealizationSpec`, and `boundary_compiler.py`; add one distinct tagged seat-protection variant, keep legacy `PlatformBoundarySpec` v1-only, and preserve separate platform and RAES meanings. |
| Apply and read-back | `_compose_boundary_realization.py`, `_compose_boundary.py`, and `containers/network-boundary-helper`; signed payload over stdin, bounded helper, atomic rules, independent closed parser, normalized receipt, fresh kernel read-back. |
| Runtime inventory and fatal decision | `appliance_boundary_inventory.py`, `guest_observation.py`, and `appliance_boundary_gate.py`; extend the one observation and gate vocabulary. |
| Native resource ownership | `_compose_resource_ownership.py`, `WorkspaceOwnership`, `ResourceReceipt`, receipt capture, and native evidence; bind network/container/volume native IDs to the exact workspace, project, daemon, and attempt. |
| Docker and effective runtime authority | `runtime_authority.py`, `_compose_runtime_orchestration.py`, `_compose_runtime_observation.py`, `_runtime_materialization_effective.py`, `_compose_substrate_attestation.py`, and RAES runtime observations; intersect typed admission with daemon-observed mounts, namespaces, devices, capabilities, and holder identity. |
| Capture and evidence | `_compose_capture_apparatus.py`, capture admission/coordinator, evidence coordinator/content store, and `LocalRunStore`; preserve authority, sealing, path safety, custody, and export reconciliation. |
| Configuration and secrets | Strict `AptlConfig`, `core/env.py`, `_environment_bindings.py`, generated artifacts, `strict_json.py`, and ADR-029; reject extras/placeholders/duplicate keys and keep secrets out of the signed policy. |
| Seat identity and freshness | `image_config.py`, `image_trust.py`, `launch_descriptor.py`, `readiness.py`, and seat `lifecycle.py`; retain Cosign/digest binding, canonical bytes, nonce/boot/instance/generation binding, and per-start observation. |
| Guest/runtime separation | `aptl-appliance-first-boot`, its hardened systemd service, and `desktop-compose.yml`; protect guest services without sweeping the platform desktop bridge into the range. |
| Errors and diagnostics | Existing `BackendTimeoutError`/`BackendObservationError`, `LabResult`, `StartupOutcome`/`StartupDiagnostic`, and `SeatLauncherError`; use stable, coarse codes and the existing error envelopes. |
| Logging and redaction | `utils/redaction.py` at persistence and response boundaries and `get_logger()` for logging; never assume the logger redacts arbitrary values, so do not log raw inspect, nftables, environment, credential, or probe payloads. |
| Qualification workflow | Appliance build/scan/config/qualification scripts plus the installed-lab TechVault verifier and live gates; one immutable candidate, real start path, fresh-seat journey, existing CI workflow. `qualify-seat-image.sh` accepts only an immutable signed digest and exercises real first boot, warm restart, reset, and a second clean start. |
| Repository workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/run-targeted-tests.sh`, staged-file pre-commit, strict docs, and CI clean-lab/image gates remain the only quality workflow; do not add an issue-local runner or weaken path selection. |

`AptlConfig` remains the user configuration surface. This protection is a
signed seat property, not a new `aptl.json` or environment toggle. Strict JSON
duplicate-key rejection applies to signed documents. Paths and persisted
evidence retain the existing safe-path, no-follow, locking, private-mode,
sealing, and redaction boundaries.

Commands must remain argument arrays, with policy documents delivered on
standard input. Secrets must not appear in `argv`, systemd environment,
health-check commands, exceptions, readiness envelopes, or probe records. The
participant API receives no new endpoint and should see only the existing
coarse readiness/diagnostic state. If any management projection is later
required, it must pass `src/aptl/api/deps.py`, `api/middleware/bff.py`, and
`api/session.py`: bearer authentication, Host/Origin, CSRF, two-factor session,
WebSocket-origin, and response-redaction boundaries.

`LocalRunStore.write_json()` and `write_jsonl()` apply the shared structured
redaction boundary; opaque `write_file()` content does not. Persist only the
bounded, normalized inventory and receipts through the structured path. Never
store raw Docker inspect, environment, nftables, journal, or probe output and
assume the repository will redact it later.

## Whole-Repository Surface

- Policy and trust: appliance policy/binding, seat image configuration,
  signature verification, launch descriptor, readiness challenge, host
  exposure observation, and the one boundary gate.
- Realization and runtime: admitted RAES realization, boundary compiler and
  tagged enforcement union, selected Docker transport, native ownership
  receipts, effective-runtime validators, helper container, nftables kernel
  state, and active probe namespaces.
- Guest and evidence: first-boot/systemd ordering, the QEMU launch channel,
  desktop support project, capture apparatus, generated environment/artifacts,
  evidence coordinator/content store, and structured run-store inventory.
- Delivery and operations: appliance build, scan, configuration and
  qualification scripts; installed TechVault journey/live gates; launcher and
  limitation documentation; `.ground-control.yaml`, `.gc/plan-rules.md`,
  pre-commit, strict MkDocs, CI, and clean-seat qualification. Ground Control
  routes `containers/network-boundary-helper/**` to the host boundary and
  `containers/appliance-egress-proxy/**` to the range perimeter.

## Extensibility Seam

The seam is a signed set of **protected component classes and typed permitted
flows**, applied to the runtime set of range bridges and resources owned by the
admitted project/attempt. A flow needs source class, destination component
class, protocol/port, purpose, and probe identity; realization supplies native
interfaces and resource identities. Observation adapters report the same
classes for the current backend.

A future LilRAE collector should require one new typed component/flow and probe
adapter. A future scenario should change only the admitted realization and its
owned bridge/resource set. Neither change should require a TechVault-specific
firewall fork, a Compose-service allow-list, or a rewrite of the fatal gate.
The same observation seam can later support another backend without pretending
that Docker-specific interface or mount facts are portable policy.

## Guardrails And Anti-Patterns

- Do not restore participant/management/egress zones or rename scenario SOC
  networks as platform management networks.
- Do not make platform rules part of RAES ACLs, or parse the SDL a second time.
- Do not filter the forwarding path, alter range subnets, or add broad port
  exceptions to make TechVault pass.
- Do not target every Docker bridge; the desktop project and future platform
  support networks are outside the range ownership set.
- Do not use Docker labels, container names, mutable IP addresses, or socket
  path strings alone as identity or authority.
- Do not relabel `participant_routes_digest` as a RAES plan digest, infer RAES
  enforcement from a platform policy version, or let a RAES runtime admission
  double as a seat-component access grant.
- Do not treat `internal: true`, loopback publication, NAT, TLS, CORS, a
  read-only socket mount, desired Compose, a successful helper exit, or rule
  text alone as enforcement evidence.
- Do not duplicate boundary, capture, mount, environment, error, logging,
  startup, or qualification schemas and workflows.
- Do not accept generic nftables commands or an unrestricted policy escape
  hatch. Unknown policy values and unsupported runtime capabilities fail
  closed.
- Do not include secrets or unbounded raw runtime output in policies,
  observations, logs, diagnostics, evidence bundles, or API responses.
- Do not reuse qualification from another image or boot. Do not let a v1/v2
  policy, missing field, or defaulted boolean claim the new protection.

## Non-Goals And Boundaries

- No red/blue/target, Shuffle/TheHive, or other range segmentation.
- No host-to-seat, seat-to-seat, hypervisor, physical-host, or recovery design;
  ADR-060 and the existing seat trust chain own those boundaries.
- No new seat egress control or egress-protection claim; issue #1182 owns
  optional egress policy, while selected but unverifiable egress policy remains
  a fatal APP-1 condition.
- No new participant API, secret store, evidence store, capture schema,
  firewall engine, Docker proxy, or general-purpose policy language.
- No claim against guest root, the administrative participant mode, compromise
  of an admitted raw-Docker authority holder, kernel escape, or shared-guest
  denial of service.
- No product-specific service list in the signed protection contract. Product
  journey names belong to qualification evidence, not platform policy.
