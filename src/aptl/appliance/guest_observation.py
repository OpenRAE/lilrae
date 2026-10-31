"""Fresh guest-side appliance boundary observation and active traffic probes."""

from __future__ import annotations

import hashlib
import ipaddress
import posixpath
import re
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from aptl.core.appliance_boundary import (
    ApplianceBoundaryBinding,
    ApplianceBoundaryPolicy,
)
from aptl.core.appliance_boundary_inventory import (
    BoundaryEnforcementObservation,
    BoundaryProbeObservation,
    DockerAuthorityHolder,
    GuestBoundaryObservation,
    RangeWorkloadObservation,
)
from aptl.core.deployment.boundary import (
    AcesBoundarySpec,
    PlatformBoundarySpec,
    SeatProtectionBoundarySpec,
)
from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.core.deployment.realization import (
    DeploymentAclRealization,
    DeploymentRealizationSpec,
)
from aptl.core.deployment._compose_runtime_observation_helpers import (
    inspect_has_endpoint_override,
    inspect_has_socket_route,
)
from aptl.core.ephemeral_containers import (
    EphemeralContainer,
    remove_container_command,
)

_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PROBE_PATH = "/usr/local/bin/aptl-boundary-probe"
_PROTECTED_EVIDENCE_ROOTS = (
    PurePosixPath("/opt/aptl/project/.aptl/runs"),
    PurePosixPath("/var/log/aptl/captures"),
)
_PLATFORM_CREDENTIAL_ROOTS = (
    PurePosixPath("/run/aptl-source"),
    PurePosixPath("/run/aptl-launch"),
)
_PLATFORM_CREDENTIAL_FILES = frozenset(
    {
        "appliance-launch.json",
        "boundary-policy.json",
        "readiness-challenge.json",
    }
)


def _read_guest_boot_id() -> str:
    """Read a stable boot identity on Linux and portable test hosts."""

    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        try:
            observed = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        except OSError, subprocess.SubprocessError:
            observed = ""
        if not observed:
            raise ValueError("guest boot identity is unavailable")
        value = "sha256:" + hashlib.sha256(observed.encode()).hexdigest()
    if not value:
        raise ValueError("guest boot identity is unavailable")
    return value


class _ProbeBackend(Protocol):
    """Backend operations required to observe and probe the guest boundary."""

    _docker_daemon_id: str | None

    def _run(
        self, command: list[str], *, timeout: int | None = None
    ) -> subprocess.CompletedProcess[str]: ...

    def host_list_lab_containers(self) -> list[dict[str, object]]: ...

    def container_inspect(self, container: str) -> dict[str, object]: ...

    def _ephemeral_container(self, role: str) -> EphemeralContainer: ...

    def _resolve_owned_container_id(self, selector: str) -> str: ...


@dataclass(frozen=True)
class _LiveContainer:
    """Normalized live container identity and network observation."""

    identity: str
    name: str
    addresses: tuple[str, ...]
    inspection: dict[str, object]


@dataclass(frozen=True)
class _ProbePath:
    """One active reachability assertion between observed containers."""

    identity: str
    authority: str
    source: _LiveContainer
    destination: _LiveContainer
    destination_address: str
    port: int
    expectation: str


def _live_containers(backend: _ProbeBackend) -> tuple[_LiveContainer, ...]:
    """Normalize running containers from the guest backend."""

    observed: list[_LiveContainer] = []
    for row in backend.host_list_lab_containers():
        if row.get("state") not in {None, "running"}:
            continue
        candidate = row.get("id") or row.get("name")
        if not isinstance(candidate, str) or not _CONTAINER.fullmatch(candidate):
            continue
        inspection = backend.container_inspect(candidate)
        identity = inspection.get("Id", candidate)
        raw_name = inspection.get("Name", row.get("name", candidate))
        if not isinstance(identity, str) or not isinstance(raw_name, str):
            continue
        name = raw_name.removeprefix("/")
        networks = inspection.get("NetworkSettings", {})
        networks = networks.get("Networks", {}) if isinstance(networks, Mapping) else {}
        addresses = tuple(
            str(address)
            for details in networks.values()
            if isinstance(details, Mapping)
            for address in (
                details.get("IPAddress"),
                details.get("GlobalIPv6Address"),
            )
            if isinstance(address, str) and address
        )
        if _CONTAINER.fullmatch(name):
            observed.append(_LiveContainer(identity, name, addresses, inspection))
    return tuple(observed)


def _receipt_owned_containers(
    backend: _ProbeBackend,
    realization: DeploymentRealizationSpec,
    containers: tuple[_LiveContainer, ...],
) -> tuple[_LiveContainer, ...]:
    """Select probe sources only through current native container receipts."""

    owned: list[_LiveContainer] = []
    seen: set[str] = set()
    for node in realization.nodes:
        selector = node.container_name or node.service_name or f"aptl-{node.name}"
        try:
            native_id = backend._resolve_owned_container_id(selector)
        except KeyError, OSError, OwnershipConflictError, ValueError:
            continue
        container = _container_by_identity(containers, native_id)
        if container is not None and container.identity not in seen:
            owned.append(container)
            seen.add(container.identity)
    return tuple(owned)


def _container_by_identity(
    containers: tuple[_LiveContainer, ...], identity: str
) -> _LiveContainer | None:
    """Resolve an observed container by its runtime or service identity."""

    return next(
        (
            item
            for item in containers
            if identity in {item.identity, item.name}
            or item.name.endswith("-" + identity)
        ),
        None,
    )


def _container_by_ip(
    containers: tuple[_LiveContainer, ...], address: str
) -> _LiveContainer | None:
    """Resolve an observed container that owns an exact address."""

    return next((item for item in containers if address in item.addresses), None)


def _peer_on_network(
    containers: tuple[_LiveContainer, ...],
    network: ipaddress.IPv4Network,
    *,
    exclude: _LiveContainer | None = None,
) -> tuple[_LiveContainer, str] | None:
    """Select a peer and address on one network, excluding an optional owner."""

    for item in containers:
        if item == exclude:
            continue
        for address in item.addresses:
            if ipaddress.ip_address(address) in network:
                return item, address
    return None


def _probe_command(
    *,
    image: str,
    network_container: str,
    arguments: list[str],
    lifecycle: list[str],
) -> list[str]:
    """Build the fixed, least-privilege active-probe command.

    ``lifecycle`` carries how the container is named, detached and removed; the
    probe itself — the namespace it joins, its capabilities, its image and
    arguments — is fixed here and not the caller's to vary.
    """

    if not _CONTAINER.fullmatch(network_container):
        raise ValueError("boundary probe container identity is invalid")
    return [
        "docker",
        "run",
        *lifecycle,
        "--network",
        f"container:{network_container}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--entrypoint",
        "python3",
        image,
        _PROBE_PATH,
        *arguments,
    ]


def _host_probe_command(
    *,
    image: str,
    arguments: list[str],
    lifecycle: list[str],
) -> list[str]:
    """Build the fixed host-network probe used only for guest bridge targets."""

    return [
        "docker",
        "run",
        *lifecycle,
        "--network",
        "host",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--entrypoint",
        "python3",
        image,
        _PROBE_PATH,
        *arguments,
    ]


def _connect(
    backend: _ProbeBackend,
    *,
    image: str,
    source: _LiveContainer,
    address: str,
    port: int,
    protocol: str = "tcp",
) -> bool:
    """Run one bounded transport probe from an observed container."""

    helper = backend._ephemeral_container("boundary-probe")
    result = helper.run(
        backend._run,
        _probe_command(
            image=image,
            network_container=source.name,
            arguments=[
                "connect",
                "--address",
                address,
                "--port",
                str(port),
                "--protocol",
                protocol,
                "--timeout",
                "3",
            ],
            lifecycle=helper.run_options(),
        ),
        timeout=10,
    )
    return result.returncode == 0


def _start_listener(
    backend: _ProbeBackend,
    *,
    image: str,
    destination: _LiveContainer,
    address: str,
    port: int,
    protocol: str = "tcp",
) -> str | None:
    """Start a temporary bounded listener for an otherwise quiet target."""

    helper = backend._ephemeral_container("boundary-listener")
    # Detached, and still auto-removed: the listener exits on its own timeout,
    # so a caller that never gets to remove it does not leave it behind.
    command = _probe_command(
        image=image,
        network_container=destination.name,
        arguments=[
            "listen",
            "--address",
            address,
            "--port",
            str(port),
            "--protocol",
            protocol,
            "--timeout",
            "15",
        ],
        lifecycle=["-d", *helper.run_options()],
    )
    # A detached start returns once the container starts, so any failure —
    # including the timeout killing the CLI — can leave it created and never
    # started, where auto-remove does not reach it.
    try:
        started = backend._run(command, timeout=10)
    except Exception:
        helper.discard(backend._run)
        raise
    if started.returncode != 0:
        helper.discard(backend._run)
        return None
    for _attempt in range(50):
        logs = backend._run(["docker", "logs", helper.name], timeout=5)
        if logs.returncode == 0 and logs.stdout.strip() == "ready":
            return helper.name
        time.sleep(0.1)
    helper.discard(backend._run)
    return None


def _connect_host(
    backend: _ProbeBackend,
    *,
    image: str,
    address: str,
    port: int,
    protocol: str = "tcp",
) -> bool:
    """Run one bounded connection from the guest host network namespace."""

    helper = backend._ephemeral_container("boundary-host-probe")
    result = helper.run(
        backend._run,
        _host_probe_command(
            image=image,
            arguments=[
                "connect",
                "--address",
                address,
                "--port",
                str(port),
                "--protocol",
                protocol,
                "--timeout",
                "3",
            ],
            lifecycle=helper.run_options(),
        ),
        timeout=10,
    )
    return result.returncode == 0


def _start_host_listener(
    backend: _ProbeBackend,
    *,
    image: str,
    address: str,
    port: int,
    protocol: str = "tcp",
) -> str | None:
    """Start a bounded host listener and prove its bind from its ready record."""

    helper = backend._ephemeral_container("boundary-host-listener")
    command = _host_probe_command(
        image=image,
        arguments=[
            "listen",
            "--address",
            address,
            "--port",
            str(port),
            "--protocol",
            protocol,
            "--timeout",
            "15",
        ],
        lifecycle=["-d", *helper.run_options()],
    )
    try:
        started = backend._run(command, timeout=10)
    except Exception:
        helper.discard(backend._run)
        raise
    if started.returncode != 0:
        helper.discard(backend._run)
        return None
    for _attempt in range(50):
        logs = backend._run(["docker", "logs", helper.name], timeout=5)
        if logs.returncode == 0 and logs.stdout.strip() == "ready":
            return helper.name
        time.sleep(0.1)
    helper.discard(backend._run)
    return None


def _probe_path(
    backend: _ProbeBackend,
    path: _ProbePath,
    *,
    image: str,
) -> BoundaryProbeObservation:
    """Execute and record one expected reachable or blocked path."""

    listener: str | None = None
    try:
        target_ready = _connect(
            backend,
            image=image,
            source=path.destination,
            address=path.destination_address,
            port=path.port,
        )
        if not target_ready:
            listener = _start_listener(
                backend,
                image=image,
                destination=path.destination,
                address=path.destination_address,
                port=path.port,
            )
            target_ready = listener is not None
        reachable = target_ready and _connect(
            backend,
            image=image,
            source=path.source,
            address=path.destination_address,
            port=path.port,
        )
        passed = target_ready and (
            reachable if path.expectation == "reachable" else not reachable
        )
    finally:
        if listener is not None:
            backend._run(remove_container_command(listener), timeout=10)
    return BoundaryProbeObservation(
        identity=path.identity,
        authority=path.authority,
        source=path.source.name,
        destination=path.destination.name,
        protocol="tcp",
        port=path.port,
        expectation=path.expectation,
        passed=passed,
    )


def _probe_host_reply(
    backend: _ProbeBackend,
    *,
    image: str,
    source: _LiveContainer,
    network: str,
    family: str,
    address: str,
) -> BoundaryProbeObservation:
    """Prove host-initiated traffic and its reply on one range scope."""

    port = 43100
    listener = _start_listener(
        backend,
        image=image,
        destination=source,
        address=address,
        port=port,
    )
    try:
        reachable = listener is not None and _connect_host(
            backend,
            image=image,
            address=address,
            port=port,
        )
    finally:
        if listener is not None:
            backend._run(remove_container_command(listener), timeout=10)
    return BoundaryProbeObservation(
        identity=f"seat-protection/{network}/{family}/host-reply",
        authority="seat-protection",
        source="guest-host",
        destination="ordinary-range-workload",
        source_network=network,
        address_family=family,
        protocol="tcp",
        port=port,
        expectation="reachable",
        target_ready=listener is not None,
        passed=reachable,
    )


def _probe_host_component(
    backend: _ProbeBackend,
    *,
    image: str,
    source: _LiveContainer,
    network: str,
    family: str,
    gateway: str,
    target: object,
    port: int,
) -> BoundaryProbeObservation:
    """Prove one protected host target is ready, then test the signed outcome."""

    component_class = getattr(target, "component_class", None)
    destination = component_class or getattr(target, "destination")
    probe_identity = str(getattr(target, "probe_identity"))
    protocol = str(getattr(target, "protocol"))
    expectation = "blocked" if component_class is not None else "reachable"
    identity = probe_identity
    if component_class is None:
        identity = f"{probe_identity}/port-{port}"
    listener = _start_host_listener(
        backend,
        image=image,
        address=gateway,
        port=port,
        protocol=protocol,
    )
    try:
        reachable = listener is not None and _connect(
            backend,
            image=image,
            source=source,
            address=gateway,
            port=port,
            protocol=protocol,
        )
    finally:
        if listener is not None:
            backend._run(remove_container_command(listener), timeout=10)
    passed = listener is not None and (
        reachable if expectation == "reachable" else not reachable
    )
    return BoundaryProbeObservation(
        identity=f"seat-protection/{network}/{family}/{identity}",
        authority="seat-protection",
        source="ordinary-range-workload",
        destination=str(destination),
        source_network=network,
        address_family=family,
        protocol=protocol,
        port=port,
        expectation=expectation,
        target_ready=listener is not None,
        passed=passed,
    )


def _seat_protection_probes(
    backend: _ProbeBackend,
    spec: SeatProtectionBoundarySpec,
    containers: tuple[_LiveContainer, ...],
    *,
    image: str,
) -> tuple[BoundaryProbeObservation, ...]:
    """Run full component coverage for every observed network address family."""

    probes: list[BoundaryProbeObservation] = []
    for network in spec.networks:
        scopes = (
            ("ipv4", network.ipv4_cidr, network.ipv4_gateway),
            ("ipv6", network.ipv6_cidr, network.ipv6_gateway),
        )
        for family, cidr, gateway in scopes:
            if cidr is None or gateway is None:
                continue
            subnet = ipaddress.ip_network(cidr, strict=False)
            source_pair = next(
                (
                    (container, address)
                    for container in containers
                    for address in container.addresses
                    if ipaddress.ip_address(address) in subnet
                ),
                None,
            )
            if source_pair is None:
                continue
            source, address = source_pair
            probes.append(
                _probe_host_reply(
                    backend,
                    image=image,
                    source=source,
                    network=network.name,
                    family=family,
                    address=address,
                )
            )
            targets = (
                *((target, target.port) for target in spec.protected_components),
                *(
                    (target, port)
                    for target in spec.permitted_flows
                    for port in target.ports
                ),
            )
            for target, port in targets:
                probes.append(
                    _probe_host_component(
                        backend,
                        image=image,
                        source=source,
                        network=network.name,
                        family=family,
                        gateway=gateway,
                        target=target,
                        port=port,
                    )
                )
    return tuple(probes)


def _platform_probe_paths(
    spec: PlatformBoundarySpec,
    containers: tuple[_LiveContainer, ...],
) -> tuple[_ProbePath, ...]:
    """Build representative allow and default-deny platform probes."""

    crossing = next((item for item in spec.crossings if item.protocol == "tcp"), None)
    if crossing is None:
        return ()
    anchors = dict(spec.anchors)
    source = _container_by_identity(containers, anchors[crossing.source].identity)
    destination = _container_by_identity(
        containers, anchors[crossing.destination].identity
    )
    if source is None or destination is None:
        return ()
    destination_addresses = dict(anchors[crossing.destination].ipv4_by_network)
    shared = sorted(
        set(dict(anchors[crossing.source].ipv4_by_network)) & set(destination_addresses)
    )
    if not shared:
        return ()
    allowed_ports = {
        port for item in spec.crossings for port in item.ports if item.protocol == "tcp"
    }
    denied_port = next(
        (port for port in range(65535, 63999, -1) if port not in allowed_ports),
        None,
    )
    if denied_port is None:
        return ()
    address = destination_addresses[shared[0]]
    return (
        _ProbePath(
            identity="platform-allowed-crossing",
            authority="platform",
            source=source,
            destination=destination,
            destination_address=address,
            port=crossing.ports[0],
            expectation="reachable",
        ),
        _ProbePath(
            identity="platform-default-deny",
            authority="platform",
            source=source,
            destination=destination,
            destination_address=address,
            port=denied_port,
            expectation="blocked",
        ),
    )


def _network_cidrs(spec: AcesBoundarySpec) -> dict[str, ipaddress.IPv4Network]:
    """Index RAES IPv4 networks with concrete CIDRs."""

    return {
        item.name: ipaddress.ip_network(item.ipv4_cidr)
        for item in spec.networks
        if item.ipv4_cidr is not None
    }


def _raes_rule_path(
    spec: AcesBoundarySpec,
    rule: DeploymentAclRealization,
    containers: tuple[_LiveContainer, ...],
) -> _ProbePath | None:
    """Resolve one RAES ACL rule into an executable container probe."""

    if rule.protocol != "tcp" or not rule.ports:
        return None
    networks = _network_cidrs(spec)
    bindings = {item.owner_address: item for item in spec.owner_bindings}
    binding = bindings.get(rule.owner_address)
    if binding is None:
        return None
    direction = "out" if rule.direction == "inout" else rule.direction
    if binding.owner_resource_type == "node":
        owner_addresses = dict(binding.ipv4_by_network)
        owner_network = rule.from_network if direction == "out" else rule.to_network
        owner_ip = owner_addresses.get(owner_network or "")
        owner = _container_by_ip(containers, owner_ip or "")
        peer_network = rule.to_network if direction == "out" else rule.from_network
        peer = (
            _peer_on_network(containers, networks[peer_network], exclude=owner)
            if peer_network in networks
            else None
        )
        if owner is None or peer is None:
            return None
        if direction == "out":
            source, destination, destination_address = owner, peer[0], peer[1]
        else:
            source, destination, destination_address = peer[0], owner, owner_ip
    else:
        owner_network = networks.get(rule.owner_name)
        peer_network_name = rule.to_network if direction == "out" else rule.from_network
        peer_network = networks.get(peer_network_name or "")
        if owner_network is None or peer_network is None:
            return None
        owner = _peer_on_network(containers, owner_network)
        peer = _peer_on_network(
            containers, peer_network, exclude=owner[0] if owner else None
        )
        if owner is None or peer is None:
            return None
        if direction == "out":
            source, destination, destination_address = owner[0], peer[0], peer[1]
        else:
            source, destination, destination_address = peer[0], owner[0], owner[1]
    return _ProbePath(
        identity=f"{rule.owner_address}/{rule.name}",
        authority="raes",
        source=source,
        destination=destination,
        destination_address=str(destination_address),
        port=rule.ports[0],
        expectation="reachable" if rule.action == "allow" else "blocked",
    )


def _raes_probe_paths(
    spec: AcesBoundarySpec,
    containers: tuple[_LiveContainer, ...],
) -> tuple[_ProbePath, ...]:
    """Select one representative allowed and denied RAES rule path."""

    selected: list[_ProbePath] = []
    for action in ("allow", "deny"):
        for rule in spec.rules:
            if rule.action != action:
                continue
            path = _raes_rule_path(spec, rule, containers)
            if path is not None:
                selected.append(path)
                break
    return tuple(selected)


def _enforcement_observations(
    receipts: dict[str, dict[str, object]],
) -> tuple[BoundaryEnforcementObservation, ...]:
    """Normalize signed boundary realization receipts into observations."""

    observations = []
    for authority in sorted(receipts):
        receipt = receipts[authority]
        observations.append(
            BoundaryEnforcementObservation(
                authority=authority,
                source_digest=str(receipt["source_digest"]),
                enforcement_digest=str(receipt["enforcement_digest"]),
                families=tuple(receipt["families"]),
                default_deny_observed=bool(receipt["default_deny"]),
                network_coverage=tuple(receipt.get("network_coverage", ())),
            )
        )
    return tuple(observations)


def _authority_holders(
    *,
    backend: _ProbeBackend,
    realization: DeploymentRealizationSpec,
    policy: ApplianceBoundaryPolicy,
    containers: tuple[_LiveContainer, ...],
    daemon_id: str,
) -> tuple[DockerAuthorityHolder, ...]:
    """Observe admitted holders of the guest Docker authority."""

    nodes = {item.address: item for item in realization.nodes}
    holders = []
    admitted_identities: set[str] = set()
    for admission in realization.docker_authority_admissions:
        node = nodes.get(admission.node_address)
        identity = (node.container_name or node.service_name) if node else None
        try:
            native_id = (
                backend._resolve_owned_container_id(identity)
                if identity is not None
                else None
            )
        except KeyError, OSError, OwnershipConflictError, ValueError:
            native_id = None
        container = _container_by_identity(containers, native_id or "")
        if container is None or not (
            inspect_has_socket_route(container.inspection)
            or inspect_has_endpoint_override(container.inspection)
        ):
            continue
        admitted_identities.add(container.identity)
        holders.append(
            _observed_authority_holder(container, policy, daemon_id, admitted=True)
        )
    for container in containers:
        if container.identity in admitted_identities:
            continue
        if inspect_has_socket_route(
            container.inspection
        ) or inspect_has_endpoint_override(container.inspection):
            holders.append(
                _observed_authority_holder(container, policy, daemon_id, admitted=False)
            )
    return tuple(holders)


def _observed_authority_holder(
    container: _LiveContainer,
    policy: ApplianceBoundaryPolicy,
    daemon_id: str,
    *,
    admitted: bool,
) -> DockerAuthorityHolder:
    """Attribute one live Docker control route to its actual container labels."""

    inspection = container.inspection
    config = inspection.get("Config", {})
    labels = config.get("Labels", {}) if isinstance(config, Mapping) else {}
    selector = (
        "raes.docker-authority=admitted"
        if admitted and policy.seat_component_protection
        else next(
            (
                value
                for value in policy.docker_authority.allowed_holder_labels
                if isinstance(labels, Mapping)
                and labels.get(value.split("=", 1)[0]) == value.split("=", 1)[1]
            ),
            "org.aptl.unapproved=holder",
        )
    )
    host = inspection.get("HostConfig", {})
    host = host if isinstance(host, Mapping) else {}
    devices = host.get("Devices", [])
    return DockerAuthorityHolder(
        identity=container.identity,
        label_selector=selector,
        daemon_id=daemon_id,
        access="socket" if inspect_has_socket_route(inspection) else "api",
        privileged=host.get("Privileged") is True,
        host_pid_namespace=host.get("PidMode") == "host",
        host_network_namespace=host.get("NetworkMode") == "host",
        device_count=len(devices) if isinstance(devices, list) else 0,
        admitted=admitted,
    )


def _range_workload_observations(
    *,
    backend: _ProbeBackend,
    realization: DeploymentRealizationSpec,
    containers: tuple[_LiveContainer, ...],
    holders: tuple[DockerAuthorityHolder, ...],
) -> tuple[RangeWorkloadObservation, ...]:
    """Inspect every admitted range node through its native container receipt."""

    holder_admission = {item.identity: item.admitted for item in holders}
    observations: list[RangeWorkloadObservation] = []
    for node in realization.nodes:
        selector = node.container_name or node.service_name or f"aptl-{node.name}"
        try:
            native_id = backend._resolve_owned_container_id(selector)
        except OSError, OwnershipConflictError, ValueError:
            observations.append(
                RangeWorkloadObservation(
                    identity=selector,
                    networks=tuple(node.networks),
                    receipt_bound=False,
                    inspect_complete=False,
                    privileged=False,
                    host_pid_namespace=False,
                    host_network_namespace=False,
                    device_count=0,
                    unapproved_docker_authority=False,
                    protected_mount=False,
                    credential_exposure=False,
                )
            )
            continue
        container = _container_by_identity(containers, native_id)
        if container is None:
            observations.append(
                RangeWorkloadObservation(
                    identity=native_id,
                    networks=tuple(node.networks),
                    receipt_bound=True,
                    inspect_complete=False,
                    privileged=False,
                    host_pid_namespace=False,
                    host_network_namespace=False,
                    device_count=0,
                    unapproved_docker_authority=False,
                    protected_mount=False,
                    credential_exposure=False,
                )
            )
            continue
        inspection = container.inspection
        config = inspection.get("Config")
        host = inspection.get("HostConfig")
        mounts = inspection.get("Mounts")
        networks = inspection.get("NetworkSettings")
        complete = (
            isinstance(config, Mapping)
            and isinstance(host, Mapping)
            and isinstance(mounts, list)
            and isinstance(networks, Mapping)
        )
        host = host if isinstance(host, Mapping) else {}
        devices = host.get("Devices")
        devices = devices if isinstance(devices, list) else []
        mounted = mounts if isinstance(mounts, list) else []
        protected_mount = any(_is_protected_mount(item) for item in mounted)
        environment = config.get("Env") if isinstance(config, Mapping) else None
        credential_exposure = _has_platform_credential(environment) or any(
            _is_platform_credential_mount(item) for item in mounted
        )
        docker_route = inspect_has_socket_route(
            inspection
        ) or inspect_has_endpoint_override(inspection)
        observations.append(
            RangeWorkloadObservation(
                identity=container.identity,
                networks=tuple(node.networks),
                receipt_bound=True,
                inspect_complete=complete,
                privileged=host.get("Privileged") is True,
                host_pid_namespace=host.get("PidMode") == "host",
                host_network_namespace=host.get("NetworkMode") == "host",
                device_count=len(devices),
                unapproved_docker_authority=(
                    docker_route and not holder_admission.get(container.identity, False)
                ),
                protected_mount=protected_mount,
                credential_exposure=credential_exposure,
            )
        )
    return tuple(observations)


def _bind_source_path(raw: Mapping[object, object]) -> PurePosixPath | None:
    """Return one absolute, normalized bind source without following it."""

    value = raw.get("Source")
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        return None
    unnormalized = PurePosixPath(value)
    if ".." in unnormalized.parts:
        return None
    normalized = PurePosixPath(posixpath.normpath(value))
    if not normalized.is_absolute():
        return None
    return normalized


def _paths_overlap(source: PurePosixPath, protected: PurePosixPath) -> bool:
    """Report whether a bind source exposes a protected path or its contents."""

    return (
        source == protected
        or source in protected.parents
        or protected in source.parents
    )


def _is_protected_mount(raw: object) -> bool:
    """Identify capture and run-store custody sources without retaining values."""

    if not isinstance(raw, Mapping):
        return True
    mount_type = raw.get("Type")
    if mount_type == "volume":
        name = raw.get("Name")
        return isinstance(name, str) and (
            name == "kali_captures" or name.endswith("_kali_captures")
        )
    if mount_type == "tmpfs":
        return False
    if mount_type != "bind":
        return True
    source = _bind_source_path(raw)
    if source is None:
        return True
    return any(_paths_overlap(source, root) for root in _PROTECTED_EVIDENCE_ROOTS)


def _is_platform_credential_mount(raw: object) -> bool:
    """Identify platform launch/key material bind sources by path class only."""

    if not isinstance(raw, Mapping):
        return True
    mount_type = raw.get("Type")
    if mount_type in {"volume", "tmpfs"}:
        return False
    if mount_type != "bind":
        return True
    source = _bind_source_path(raw)
    if source is None:
        return True
    return source.name in _PLATFORM_CREDENTIAL_FILES or any(
        _paths_overlap(source, root) for root in _PLATFORM_CREDENTIAL_ROOTS
    )


def _has_platform_credential(environment: object) -> bool:
    """Inspect environment names only; never retain or report their values."""

    if not isinstance(environment, list):
        return False
    names = {
        value.split("=", 1)[0]
        for value in environment
        if isinstance(value, str) and "=" in value
    }
    return any(
        name.startswith(
            (
                "LILRAE_APPLIANCE_",
                "LILRAE_SEAT_",
                "APTL_APPLIANCE_",
                "APTL_SEAT_",
            )
        )
        for name in names
    )


def collect_guest_observation(
    *,
    backend: _ProbeBackend,
    policy: ApplianceBoundaryPolicy,
    binding: ApplianceBoundaryBinding,
    boundary_specs: dict[str, object],
    boundary_receipts: dict[str, dict[str, object]],
    realization: DeploymentRealizationSpec,
) -> GuestBoundaryObservation:
    """Collect fresh kernel readback, active probes, and Docker authority state."""

    daemon_id = backend._docker_daemon_id
    if not daemon_id:
        raise ValueError("guest Docker daemon identity is unavailable")
    containers = _live_containers(backend)
    receipt_owned = _receipt_owned_containers(backend, realization, containers)
    paths: tuple[_ProbePath, ...] = ()
    platform = boundary_specs.get("platform")
    if isinstance(platform, PlatformBoundarySpec):
        paths += _platform_probe_paths(platform, containers)
    raes = boundary_specs.get("raes")
    if binding.raes_boundary_required and isinstance(raes, AcesBoundarySpec):
        paths += _raes_probe_paths(raes, containers)
    probes = tuple(
        _probe_path(backend, path, image=binding.boundary_helper_image)
        for path in paths
    )
    seat = boundary_specs.get("seat-protection")
    if policy.seat_component_protection and isinstance(
        seat, SeatProtectionBoundarySpec
    ):
        probes += _seat_protection_probes(
            backend,
            seat,
            receipt_owned,
            image=binding.boundary_helper_image,
        )
    enforcements = _enforcement_observations(boundary_receipts)
    expected_authorities = {"platform"} if policy.internal_zone_isolation else set()
    if policy.seat_component_protection:
        expected_authorities.add("seat-protection")
    if binding.raes_boundary_required or realization.acls:
        expected_authorities.add("raes")
    complete = {item.authority for item in enforcements} == expected_authorities and (
        not (policy.internal_zone_isolation or policy.seat_component_protection)
        or all(
            any(
                item.authority == authority and item.expectation == expectation
                for item in probes
            )
            for authority in expected_authorities
            for expectation in ("reachable", "blocked")
            if authority != "seat-protection"
        )
    )
    if policy.seat_component_protection:
        seat_probes = [item for item in probes if item.authority == "seat-protection"]
        complete = (
            complete
            and all(
                any(item.expectation == expectation for item in seat_probes)
                for expectation in ("reachable", "blocked")
            )
            and all(item.target_ready and item.passed for item in seat_probes)
        )
    holders = _authority_holders(
        backend=backend,
        realization=realization,
        policy=policy,
        containers=containers,
        daemon_id=daemon_id,
    )
    admitted_holder_count = sum(item.admitted for item in holders)
    holder_identities = [item.identity for item in holders]
    complete = (
        complete
        and admitted_holder_count == len(realization.docker_authority_admissions)
        and len(holder_identities) == len(set(holder_identities))
    )
    workloads = (
        _range_workload_observations(
            backend=backend,
            realization=realization,
            containers=containers,
            holders=holders,
        )
        if policy.seat_component_protection
        else ()
    )
    if policy.seat_component_protection:
        complete = (
            complete
            and bool(workloads)
            and all(item.receipt_bound and item.inspect_complete for item in workloads)
        )
    if binding.raes_plan_digest is None:
        raise ValueError("admitted runtime plan digest is unavailable")
    return GuestBoundaryObservation(
        policy_digest=binding.policy_digest,
        raes_plan_digest=binding.raes_plan_digest,
        raes_boundary_required=binding.raes_boundary_required,
        boot_id=_read_guest_boot_id(),
        guest_daemon_id=daemon_id,
        workbench_policy_version=policy.workbench_policy_version,
        enforcements=enforcements,
        observation_complete=complete,
        probes=probes,
        docker_authority_holders=holders,
        range_workloads=workloads,
    )
