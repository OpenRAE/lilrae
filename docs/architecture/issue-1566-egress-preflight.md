# Issue #1566: SAF-002 egress preflight

Preserve the existing network-egress contracts while porting the container helpers.
This note adds SAF-002 guardrails to the
[container helpers preflight](issue-1566-container-helpers-preflight.md).
It records repository evidence at `f573683d1`, not an implementation plan,
a completed package design, or live containment qualification.
No new ADR or runtime abstraction is needed.

## Current behavior and authority

The supplied SAF-002 rationale describes an earlier revision.
`docker-compose.yml` already sets `internal: true` on `aptl-dmz`,
`aptl-internal`, and `aptl-redteam`.
`tests/test_consistency.py:TestNetworkEgressControls` preserves those flags
and the security network's existing external access.
Do not add another firewall merely to repeat that historical change.
For dynamic scenarios, the admitted RAES network's `internal` property and
attachments remain authoritative; the fixed Compose topology is an example.

Keep network-egress denial, inter-zone ACLs, and guest-host input protection separate.
V3 seat protection does not claim outbound isolation or restore historical V1 controlled egress.
An approved V1 egress projection cannot authorize another seat version or a range workload.
An internal network alone cannot establish end-to-end containment for a multi-homed workload.
Check every attachment and the existing relay/gateway paths through the selected daemon's observations.
Docker permits communication with an internal network's gateway and appropriately configured host services.
See [Docker internal network semantics](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal).
Retain the existing protected-seat and active-probe gates; do not infer their results from a Compose flag.

## Egress-specific design guardrails

| Layer and canonical incumbent | Required outcome |
| --- | --- |
| Admission and policy: `src/aptl/core/appliance_boundary.py`, `boundary_compiler.py`, signed seat binding and gate | Preserve the policy version and authority intersection. The CONNECT service receives only `render_egress_proxy_policy()` output, not SDL, the full appliance policy, or participant-authored destinations. |
| Schema and configuration: `EgressAuthority`, `EgressProxyLimits`, proxy `_load_policy()` and `parse_connect()` | Retain closed authority/port records, unique entries, nonempty authorities, exact field names, integer types, and every signed limit's units and bounds. Apply ADR-065 strict decoding before semantic checks and network effects. Record Python leniencies rather than silently widening admission. |
| Environment and secrets: `_environment_bindings.py`, `_realization_primitives.py`, ADR-029, shared redaction | Preserve explicit grants, environment-file representability, private policy/key delivery, and existing `APTL_*` meanings. Do not inherit host proxy settings, credentials, or arbitrary target overrides. Policies use stdin/private files; argument arrays do not conceal secret values. |
| Transport: `containers/appliance-egress-proxy/proxy.py` | Admit only exact DNS authority and port CONNECT requests. Validate every DNS answer before connecting, reject the complete answer set if any address is unsafe, and dial the validated numeric address without another lookup. Keep mapped IPv4 and well-known NAT64 checks. |
| OS and daemon: `_docker_endpoint_binding.py`, resource receipts, `_operator_access.py`, effective runtime checks | Use the selected Linux daemon and native resource bindings. Preserve non-root proxies, read-only roots, existing capabilities, and loopback-only host publications. The operator relay remains a separate byte relay to one admitted target; its target's SSH service owns authentication. No new Docker socket, host networking, or privileged workload grant. |
| Results and evidence: `LabResult`, deployment errors, boundary receipts, `appliance_boundary_gate.py`, shared logging/redaction | Preserve exact receipt comparison and independent observations. Keep proxy 403/503 behavior, safe errors, bounded diagnostics, and protocol stdout. Use injected `slog` on stderr when needed; no raw DNS, parser, command, environment, or payload values in outward errors/spans. |

Do not substitute Go `IsGlobalUnicast()` for Python `ipaddress.is_global`.
Go explicitly includes private IPv4 and unique-local IPv6 in that predicate.
Its `IsPrivate()` method also does not define the complete destination policy.
See the [Go address documentation](https://pkg.go.dev/net/netip#Addr.IsGlobalUnicast).
The current contract and Python-first conformance cases must define admission
for private, metadata, reserved, multicast, mapped, and NAT64 destinations.

The CONNECT broker is an opaque tunnel, not a host HTTP client.
`internal/httpclient` already owns bounded host HTTP/TLS behavior; it does not
supply CONNECT authorization or replace bidirectional socket relay semantics.
Do not add TLS interception, redirects, wildcard matching, retries, alternate DNS,
direct-network fallback, DoH, QUIC, or UDP egress.
Preserve authority normalization and request rejection against the existing parser tests.
Keep buffered tunnel bytes when handing a parsed CONNECT stream to the relay.
Use the container's configured DNS path; add no public resolver or DNS service.
Keep the signed connection/header limits and header/connect/idle timeout behavior.
Every connection owns both relay directions and releases capacity and sockets when it ends.

## Shared mechanisms, delivery, and extension seams

Reuse `internal/canonical` and `internal/digest` for the existing named schemes.
Boundary enforcement and the egress projection use sorted compact Python JSON;
signed appliance-policy bytes use RFC 8785.
Do not merge those identities or replace them with ordinary Go JSON output.
Reuse contained files, locks, clocks, waits, process handling, redaction,
error categories, and ownership gates as specified in the main preflight.
Missing foundation capabilities belong with their existing owners.
RAES/env-packs semantics require their released upstream APIs, not local copies.

The extension seams are the existing authority variants, signed DNS-authority/port
records and limits, admitted network bindings, and daemon target architecture.
Another reviewed authority or Linux architecture changes those inputs;
it must not require scenario branches in the parser, firewall renderer, or relay.
Policy generations still require their explicit contract and qualification.
Do not generalize these seams into arbitrary nft syntax or a proxy plugin framework.

ADR-065 requires one static Linux helper binary with closed role dispatch.
Select its architecture for the daemon, independently of the controller host.
Keep digest-pinned runtime images, trusted image selection, and exact offline staged identities.
Do not add a compiler, module download, runtime pull, or developer rebuild fallback to offline seats.

`src/aptl/_asset_manifest.py` and `hatch_build.py` currently include tracked
`containers/` assets in Python wheels.
Changing a default helper Dockerfile can therefore change the Python release
even without editing Python code.
The delivery design must name a Go-only image/build-context boundary and retain
the Python asset and interpreter consumers until their authorized handoff.
Host realization belongs to #1571; Go port 31 owns the distribution switch.
Do not disguise the binary as an interpreter or retain Python in Go helper images.

## Evidence and non-goals

Use `test_appliance_egress_proxy.py`, `test_network_boundary_helper.py`,
`test_network_boundary_probe.py`, `test_operator_access.py`,
`test_compose_boundary_realization.py`, and `TestNetworkEgressControls` as contract anchors.
Reuse boundary-policy and egress-proxy serialization vectors.
Add missing conformance cases before Go and run them on Python first.
Preserve both denied destinations and admitted positive controls, including
mixed DNS answers, stale or foreign ownership, and explicit IPv4/IPv6 behavior.
A dead listener or a rendered rule is not proof of traffic denial.

The implementation must pass ADR-065's package-design check before coding.
Keep `architecture/model.yaml`, `.gc/pack-ownership.json`, CI selection,
image scanning, and installed-lab/offline qualification in scope.
Local tests remain targeted; CI owns mutation, full architecture/security
checks, and clean lifecycle qualification. Keep Python traceability links.

This preflight implements no requirement and changes no runtime behavior.
It adds no network topology, firewall backend, proxy schema, service, exception
hierarchy, persistence store, workflow, privilege, or public management endpoint.
Functional repairs need separate issue scope; new security findings follow
`SECURITY.md` and remain private until disclosure is authorized.
No user-guide rewrite, release, publication, or merge belongs here.
