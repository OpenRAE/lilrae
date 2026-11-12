# Issue #1566: Container helpers architecture preflight

The Go port must preserve enforcement and capture contracts across container,
host, and evidence boundaries. Replacing interpreters alone is insufficient.
This preflight uses repository revision `f573683d1` and the supplied issue and
APP-1 and NET-005 payloads. It changes no implementation and is not an implementation
plan, a package design record, or evidence that the design check passed.

## Decisions and unresolved boundaries

- Follow [ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md):
  one static Linux `cmd/lilrae-helper` binary serves the helper roles.
  Keep role dispatch at entry and policy values in core. Native effects stay
  outside the shared policy package. Sharing a binary grants no additional
  capabilities, mounts, commands, or remotely selectable roles.
- Share one boundary enforcement contract between Go host and helper consumers.
  `src/aptl/core/deployment/boundary.py`, `_boundary_validation.py`, and
  `boundary_compiler.py` identify its existing ownership boundaries.
  Model authority-specific variants with closed shapes; do not create one
  structure whose optional fields admit combinations from different authorities.
  Keep compilation from observed resources separate from wire validation and
  nftables rendering. Do not copy RAES SDL, ACL, planning, or env-packs schemas.
- **Host integration needs an explicit handoff.**
  `_compose_capture_apparatus.py` invokes `python3 /usr/local/bin/broker.py`;
  MCP common `captures.ts` also uses that interpreter for session finalization.
  `src/aptl/appliance/guest_observation.py` overrides the image entrypoint with
  `python3` for probes. Neither works with a Python-free image.
  Host realization belongs to Go port 20. The delivery design must name the
  later consumer contract and isolate unreleased Go assets from Python assets.
  Do not replace Python release images, retain an interpreter, or disguise a
  Go executable as `python3` to bridge this gap. Image-local SSH configuration
  must invoke the Go broker while retaining the forced-command contract.
- **Prerequisites are incomplete in this checkout.**
  `internal/canonical`, `digest`, `clock`, `wait`, `securefile`, `filelock`,
  and `httpclient` exist. The foundation design assigns `internal/process`
  to #1607; that package and the shared Go redactor are absent here.
  Dependent work requires the relevant delivered packages, not a helper-local
  replacement. Required upstream Go contracts must also exist before use.
  `securefile` has no general append writer, and `ReadFile` is unbounded.
  Resolve required contained append support with its owner; bound reads from
  retained handles. Do not assume replacement APIs satisfy ledger semantics.
- **Validation parity needs a decision.** Host and helper checks differ.
  For example, host owners use an 80-character grammar; helper tokens admit
  more punctuation and length. Network/family checks also differ.
  Record accepted and rejected cases before choosing the shared validator.
  Do not silently widen authorization or reject a valid producer output.
  ADR-065 requires strict decoding; document Python leniencies using the
  compatibility disposition in the [serialization inventory](../reference/serialization-schemes.md).

## Authorities must remain distinct

| Concern | Boundary to preserve |
| --- | --- |
| NET-005 and [ADR-006](../adrs/adr-006-four-network-segmentation.md) | Workloads without a shared admitted network have no direct path. An inter-zone path requires a multi-homed intermediary. Membership does not itself enable forwarding or authorize every flow. The historical four-network example is not a fixed topology for new scenarios. |
| RAES range policy | Admitted networks, attachments, ACL owners, authored order, direction, endpoints, protocols, ports, and actions remain RAES authority. Multiple applicable ACL owners remain independent restrictions. An allow rule cannot manufacture network membership or a route. |
| Appliance V1 platform policy | Exact signed selectors bind participant, management, and egress anchors and their crossings. Preserve deny-only bootstrap before anchors exist. These three zones are distinct from ADR-006's four scenario zones. |
| Appliance V2 and V3 | V2 declares VM-only containment. V3 adds range-to-guest-host input protection; it does not introduce range-to-range isolation or default outbound restrictions. Retain the outer VM boundary of [ADR-060](../adrs/adr-060-vm-only-seat-containment.md) and the current access contract of [ADR-061](../adrs/adr-061-gateless-vm-seat-access.md). |
| Integrity identities and projections | The signed appliance-policy digest, compiled enforcement digest, and exact-authority egress projection have separate owners. Keep `render_egress_proxy_policy()` separate from the shared firewall contract. A digest proves byte identity, not producer authentication or observed enforcement. |
| Capture custody | [ADR-041](../adrs/adr-041-kali-capture-sidecar-ownership-boundary.md) and [ADR-042](../adrs/adr-042-sidecar-owned-pty-master.md) govern sidecar-owned PTY capture. Sharing Kali's network namespace does not authorize sharing its PID namespace or evidence mounts. |

[Appliance boundary](../components/appliance-boundary.md) defines the
intersection of admitted range authority and signed seat policy. A helper
receipt, a default-deny flag, or successful host-protection probes cannot
independently prove NET-005 or SAF-002. Preserve the applicable policy generation;
do not restore historical V1 egress controls to V2/V3 seats during this port.
[ADR-057](../adrs/adr-057-agent-execution-compartments.md) is proposed;
it does not authorize a new sandbox or execution service here.

## Cross-cutting layers and canonical owners

Paths starting with `core/`, `backends/`, `api/`, or `utils/` below are relative
to `src/aptl/`. Existing Python owners define parity contracts; Go consumers
reuse their delivered Go counterparts without importing Python or tool packages.

```text
authenticated caller -> admitted plan / signed policy -> observed resource binding
  -> shared enforcement values -> bounded helper -> Linux kernel / SSH / private files
  -> independent readback / capture export -> existing qualification / archive / result
```

| Layer and incumbent | Required passage |
| --- | --- |
| Authentication and ingress: `api/deps.py`, `api/session.py`, `api/middleware/bff.py`; MCP common `server.ts`, `config.ts`; capture `sshd_config` | Preserve bearer/session, Host/Origin, capability, and advertised argument-schema gates. No new HTTP/MCP endpoint or arbitrary helper-command surface. OpenSSH authenticates the broker session; authority binds run, plan, and capture binding. The operator relay transports bytes and leaves target authentication intact. |
| Signed policy and resource binding: `core/appliance_boundary.py`, `boundary_compiler.py`, `_compose_boundary_realization.py`, `_compose_resource_ownership.py`, `_compose_resource_resolution.py`, `_docker_endpoint_binding.py` | Validate signed policy shape and digest before compilation. Bind exact receipt-owned networks, bridges, workloads, workspace, and selected daemon. Reject missing, ambiguous, foreign, or stale bindings before mutation. Names, labels, and hashes alone grant no authority. Host-side discovery and compilation remain outside #1566. |
| Shared wire parsing: `boundary.py`, `_boundary_validation.py`, helper `validate_policy`; `internal/canonical` | Bound input, reject duplicate/unknown/case-mismatched keys, invalid UTF-8, trailing data, invalid variants, and cross-authority fields. Preserve required nulls, empty collections, integer checks, label-pair arrays, ordering, and field spellings. Decode and validate at both process boundaries with the same contract. Resource ownership and kernel readback are separate checks and must remain. |
| Configuration and environment: `core/config.py:AptlConfig`, `core/env.py`, `core/_credential_sources.py`, `_environment_bindings.py`, `_realization_primitives.py`, `_compose_capture_config.py` | Retain strict first-party shapes, placeholders, exact pack/consumer/variable grants, generated-artifact references, and env-file representability checks before mutation. Preserve existing `APTL_*` roots, proxy target/listen fields, and session correlation names. Read explicit inputs; do not inherit ambient credentials or introduce a durable feature flag or naming alias. |
| OS exposure: `_compose_boundary.py`, `guest_observation.py`, `core/ephemeral_containers.py`, `core/lifecycle_guard.py`, capture entrypoint and Compose | Enforcement runs on the selected Linux daemon with host networking and only its existing `NET_ADMIN` grant. Probes retain no added capabilities and their exact observed namespace. Preserve read-only roots, tmpfs bounds, no-new-privileges, owned cleanup, context cancellation, and bounded subprocess I/O. Pass policy on stdin and private keys through protected files. No shell interpolation, Docker socket, privileged mode, or physical-host substitution. |
| Integrity and persistence: `internal/canonical`, `internal/digest`, `internal/securefile`, `internal/filelock`, `core/runstore.py`, `core/archival/`, `backends/_raes_transcript_export.py` | Compose the existing scheme functions; retain private contained access, no-follow rules, create-once authority/metadata, append-only ledgers, shared quota/admission locks, and seal exclusion. Keep directories 0700 and files 0600 unless an existing key/config contract requires stricter modes. Match each lock's scope and primitive. Atomic replacement is not a substitute for create-once or append semantics. Raw custody bytes remain protected evidence; redaction must not rewrite their hash chain. |
| Errors and observability: `core/deployment/errors.py`, `LabResult`, capture diagnostics, API schemas, MCP handlers, `utils/{logging,redaction}.py` | Preserve helper exit/receipt contracts, broker outcomes, coarse readiness, and existing error envelopes. Wrap safe Go causes; add a category only when a caller branches on it. Never expose raw parser values, nft/Docker/SSH stderr, command contents, environments, or transcript bytes. Inject `slog` when logging is needed, use stderr, and apply the shared redactor at every outward sink. Logs do not substitute for evidence. |

The broker currently passes `SSH_ORIGINAL_COMMAND` as one inner-SSH argument.
Keep its `--` delimiter and single-argument semantics; do not execute it through
a new local shell. That existing argv exposure is not command secrecy.
A different transport for sensitive command text requires a separate contract
decision. Platform keys and tokens must never be placed in argv or diagnostics.

## Helper-specific invariants and hazards

**Boundary enforcement.** Keep separate owner/authority-derived tables in
both `bridge` and `inet`, atomic native replacement, foreign-table refusal,
and exact receipts. Empty RAES policy means owned cleanup, not global deny.
Retain owner scoping, authored wildcard meaning, ordered rules, bootstrap
denials, and the current IPv4-only RAES/platform subset.
V3 host protection covers each observed IPv4/IPv6 range bridge with input
rules only. Do not add NAT, routing, forwarding, or broad firewall flushes.

Readback has a concrete baseline limitation. Helper
`_verify_observed_family` checks chain metadata and sorted rule comments for
RAES/platform; only seat protection compares ordered expressions.
Changed RAES/platform expressions retaining their markers can therefore evade
that comparison. A port must not claim complete semantic drift detection from
these checks. Record a separate security bug for stronger readback; do not
silently change the accepted enforcement behavior in a parity port.
Do not remove independent observations because the renderer already validates.
Observation failures must remain fatal. Distinguish confirmed absence from
unavailable readback; never describe unknown state as verified absence.
Any required change to current behavior needs separately scoped bug work.
Follow `SECURITY.md` for security-defect reporting.

**APP-1 inventory and gate.** Reuse
`core/appliance_boundary_inventory.py`, `core/appliance_boundary_gate.py`,
and `appliance/guest_observation.py`; keep their orchestration outside
the helper. Qualification and every start require current policy/payload/plan,
boot, selected daemon, workload, Docker-authority, publication, and probe evidence.
Keep guest boot, outer-host boot, and instance generation distinct and bound
through the authenticated launch contract.
A signed image, cached inventory, successful helper receipt, or refreshed
timestamp cannot supply fresh runtime evidence.
Preserve exact per-network/per-family coverage, target readiness, and fatal
unknown/incomplete observations. Operator inventory remains bounded and
redacted; participants receive coarse readiness. V3 protects guest components;
it does not survive guest-root/kernel compromise or denial of service.
The physical-host boundary remains the outer launcher's responsibility.

**Egress and operator proxies.** Reuse the signed projection from
`core/appliance_boundary.py:render_egress_proxy_policy` and its limits.
Preserve exact CONNECT DNS authority/port admission, bounded headers,
connections and waits, whole-answer-set rejection, and denial on failure.
Dial validated address literals without resolving the hostname again.
Python `ipaddress.is_global` is not equivalent to Go `IsGlobalUnicast`:
retain private, metadata, reserved, IPv4-mapped, and NAT64 rejection cases.
The broker tunnels bytes; it must not become an HTTP client that inherits
ambient proxies, retries, or different redirect behavior.
Keep the operator relay separate: one declared target, loopback-only host
publication, existing target SSH-banner proof, and no CONNECT policy or
credentials. Its target cannot come from a participant request.

**Capture.** Reuse `broker.py`'s authority, accepted-session census, directional
frames, quota/loss disclosures, final metadata, and stop/await distinctions.
Preserve OBS-003 IDs, run/trace correlation, and the adapter-supplied binding;
do not hardcode a TechVault binding. A missing session exits 3; unfinished
finalization exits 4. Admission closes under its lock before quiesce signals
sessions. Metadata precedes registration removal. Duplicate sessions cannot
overwrite registrations or evidence. Preserve PTY ownership, raw mode,
resize and interrupt behavior, EOF, SIGHUP, SIGTERM, child-group cleanup,
and completion of custody updates during teardown.

Keep outer OpenSSH authentication, verified loopback inner SSH, runtime-only
host-key creation, and existing private key mounts. The sidecar shares no
workload PID or evidence namespace. Keep required `AUDIT_WRITE` for SSH PTYs
(#1495) and `KILL` for quiesce (#1407); these do not restore auditd or process
accounting. Root setup and sshd privilege separation remain necessary;
run as the existing non-root identities where those images already do.
An MCP PTY tee, raw sidecar frames, a finalized export, and a sealed transcript
are distinct evidence layers. Preserve the [#1242 harvest](issue-1242-workspace-capture-harvest-preflight.md)
and [#1372 capture-pin](issue-1372-capture-spec-version-preflight.md) boundaries.

**Images and delivery.** Select the Linux binary for the Docker daemon's
architecture, independently of the controller OS/architecture.
ADR-065 embeds prebuilt helper binaries for offline asset extraction; image
builds require neither a compiler nor module downloads. Static Go does not
remove required nftables/iproute2, OpenSSH, NSS, or DNS runtime dependencies.
`_compose_traffic_mirror.py` also uses the boundary image with entrypoint `tc`;
retain this consumer when reducing that image.
Do not choose `scratch` without proving those dependencies unnecessary.
Preserve digest-pinned bases, the [#1097 trust boundary](issue-1097-trusted-source-image-preflight.md),
signed helper identities, missing-image failure, and offline `--pull=never`.
The helper cache tag is a wire-contract version, not a build counter.
Prevent cached Python images from satisfying Go delivery accidentally;
record image identity separately without gratuitously renaming wire contracts.
Keep internal Go naming corrections separate from external `aptl.*` fields,
resource names, and versioned formats.

## Extensibility, repository gates, and evidence

Keep the existing seams explicit: authority-specific enforcement values;
observed network/address-family bindings; signed proxy authorities and limits;
trusted relay endpoint; admitted capture binding and roots; injected clock,
process, resolver/dialer, and file effects. Another scenario or daemon
architecture must supply data through these seams, not edit a topology constant.
Dual-stack ACLs require an explicit supported-contract change, not an
unvalidated optional field. No registry or generic workflow framework is needed.

The delivery surface includes `architecture/model.yaml`, root and tool module
manifests, `.golangci.yml`, `.ground-control.yaml`, `.gc/plan-rules.md`, and
`.gc/pack-ownership.json`. Runtime consumers include helper Dockerfiles,
capture SSH configuration, `docker-compose.yml`, `docker-compose.capture.yml`,
`config/`, `src/aptl/_asset_manifest.py`, `core/assets.py`, `hatch_build.py`,
`.dockerignore`, `scripts/appliance/` image closure/build scripts, and offline
payloads. Preserve tracked-asset selection and exclusion of generated secrets.
CI routing in
`tools/ci/select_checks.py` and `.github/workflows/checks.yml`,
`tools/ci/go-gates.sh`, `tools/ci/build_qualification_images.py`, mutation
thresholds, supply chain checks, and Sonar
must cover the new artifacts. Do not weaken these gates or add suppressions.
Include `appliance/input_images.py` and source-to-binary COPY dependencies;
changed sources must still select image rebuilds and scans. Distinguish the
OCI index, platform manifest, config ID, binary digest, and wire-contract version.

Before Go code, the issue's design note must name every package, component,
dependency and model change, then pass the ADR-065 design check against
`origin/go-cutover`. This preflight does not preselect that package graph.
Add contract cases first and run them against the Python release.
Reuse the serialization corpus for boundary digests, egress policy, timestamps,
and transcript chains/documents; extend it for missing helper-owned contracts.
Do not confuse sorted compact Python JSON with RFC 8785.
Use `canonical.SortedCompactJSON`, `digest`, and `clock.ISOZ` with explicit
contract projections. Preserve null versus empty collections, Unicode escaping,
framing and truncation. A shared Go type does not supply input byte limits;
generic `canonical.DecodeStrict()` does not validate a policy schema.

Evidence anchors are `tests/test_{boundary_compiler,network_boundary_helper,
network_boundary_probe,compose_boundary_realization,appliance_boundary_gate,
kali_capture_broker,transcript_export,operator_access,appliance_egress_proxy}.py`,
the ownership tests, capture Compose tests, and existing serialization dispatch.
Use contract evidence rather than translating private mocks or source-string
assertions. Qualify actual direct-path denial and admitted intermediary access
on Linux Docker, with ready positive controls. A refused connection alone can
mean a dead service. Account for host-published, gateway, and IPv6 bypass paths;
do not equate Docker's `internal` setting with all required isolation.
Preserve per-family probes and test loss of an attachment,
wrong daemon/owner, malformed policy, unsafe DNS, stale authority, quota loss,
and interrupted finalization. Renderer snapshots cannot prove these properties.

Local verification stays targeted through `tools/run-targeted-tests.sh` and
staged-file `pre-commit run`. CI owns mutation, full architecture/security
checks, and clean installed-lab/offline qualification.
Retain Python traceability; add the issue's Go `IMPLEMENTS` and `TESTS` links
when real artifacts exist. Target `go-cutover`; release waits for port 31.
This inspection establishes no live Docker/VM evidence or remote issue status.

Closed bug lessons include [#1477](https://github.com/OpenRAE/lilrae/issues/1477)
(adapter binding), [#1242](https://github.com/OpenRAE/lilrae/issues/1242)
(workspace sidecar and no workload fallback),
[#1201](https://github.com/OpenRAE/lilrae/issues/1201)
(transcript structure after redaction), and
[#1105](https://github.com/OpenRAE/lilrae/issues/1105)
(symlink and argv exposure). Preserve ADR-042's #1541 session-finalization
addendum. List each preserved invariant in the delivery PR.
Use the delivered decision in the #1242 note; it rejects the earlier native-ID
harvest proposal retained in that note's historical sections.
Per-session best-effort harvest is distinct from required full-run transcript
finalization. Validate the persisted redacted transcript, not only its export;
the source-chain digest and retained-content checksum cover different bytes.

## Non-goals

No requirement implementation, package graph, implementation plan, new service,
schema framework, exception tree, persistence store, or workflow engine.
No host realization port, Python release change, user-guide or distribution
change, topology redesign, new outbound restriction, capture-format migration,
auditd restoration, or additional privileges. Functional/security repairs beyond
parity require separate bug scope; the identified gaps must remain visible.
