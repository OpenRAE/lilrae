"""Owned loopback publications without adding links to scenario nodes."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from aptl.core.deployment.realization import (
    DeploymentNodeRealization,
    DeploymentPublishedPort,
    DeploymentRealizationSpec,
)
from aptl.core.deployment._compose_resource_ownership import WorkspaceOwnership

if TYPE_CHECKING:
    from aptl.core.deployment.docker_compose import DockerComposeBackend

from aptl.core.deployment.boundary import NativeRangeAllowance, NativeRangeBoundarySpec
from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    ResourceReceipt,
)
from aptl.core.deployment._operator_access_endpoints import OPERATOR_ACCESS_IMAGE
from aptl.core.lab_types import LabResult
from aptl.core.ephemeral_containers import remove_container_command
from aptl.core.deployment.errors import BackendTimeoutError

_PREFIX = "lilrae-publication-"
_TARGET = "lilrae.publication.target"


def refresh_native_policy(
    backend: DockerComposeBackend, *, required: bool = False
) -> LabResult | None:
    """Cover newly owned apparatus bridges before starting their processes."""
    if not required and "native-range" not in getattr(
        backend, "_boundary_receipts", {}
    ):
        return None
    try:
        for network in backend.host_list_lab_networks(backend._project_name):
            backend._resolve_owned_network_id(network)
        policy = NativeRangeBoundarySpec(
            backend._project_name,
            backend._project_boundary_network_observations(),
            tuple(
                NativeRangeAllowance(a.destination, a.protocol, a.port)
                for a in backend._range_egress_allowances
            ),
        )
        result = backend.realize_boundary(policy)
    except ValueError, OwnershipConflictError:
        return LabResult(
            success=False,
            error="Native apparatus network policy could not be verified.",
        )
    return None if result.success else result


def publication_bindings(
    backend: DockerComposeBackend, container_name: str
) -> dict[str, Any] | None:
    """Read real node/relay bindings, verifying ownership and the relay target."""
    if (
        "native-range" not in getattr(backend, "_boundary_receipts", {})
        and backend._resource_ownership is None
    ):
        return None
    ownership = backend._ensure_resource_ownership()
    relays = [
        r
        for r in ownership.receipts("container")
        if r.semantic_name.startswith(_PREFIX)
    ]
    if not relays and "native-range" not in getattr(backend, "_boundary_receipts", {}):
        return None
    native = backend._resolve_owned_container_id(container_name)
    node = backend.container_inspect(native)
    attached = node.get("NetworkSettings", {}).get("Networks", {})
    addresses = {n.get("IPAddress") for n in attached.values()}
    result = dict(node.get("NetworkSettings", {}).get("Ports") or {})
    for receipt in relays:
        relay = backend.container_inspect(
            backend._resolve_owned_container_id(receipt.native_id)
        )
        config = relay.get("Config", {})
        labels = config.get("Labels") or {}
        if labels.get(_TARGET) != native:
            continue
        _validate_relay_target(relay, attached, addresses)
        _append_publication_ports(result, relay)
    return result


def _append_publication_ports(result: dict[str, Any], relay: dict[str, Any]) -> None:
    """Merge only the daemon's effective bindings from a verified relay."""
    ports = relay.get("NetworkSettings", {}).get("Ports") or {}
    for key, entries in ports.items():
        result[key] = list(result.get(key) or []) + list(entries or [])


def _validate_relay_target(
    relay: dict[str, Any], attached: dict[str, Any], addresses: set[str]
) -> None:
    """Verify the relay process, image, network and exact forwarding target."""
    config = relay.get("Config", {})
    labels = config.get("Labels") or {}
    target = labels.get("lilrae.publication.address")
    port = labels.get("lilrae.publication.port")
    protocol = labels.get("lilrae.publication.protocol")
    environment = set(config.get("Env") or ())
    networks = relay.get("NetworkSettings", {}).get("Networks", {})
    required = {
        f"APTL_PROXY_TARGET_HOST={target}",
        f"APTL_PROXY_TARGET_PORT={port}",
        f"APTL_PROXY_LISTEN_PORT={port}",
        f"LILRAE_PROXY_PROTOCOL={protocol}",
    }
    if (
        not relay.get("State", {}).get("Running")
        or target not in addresses
        or not set(attached).intersection(networks)
        or not required.issubset(environment)
        or config.get("Image") != OPERATOR_ACCESS_IMAGE
    ):
        raise OwnershipConflictError("native publication target readback mismatch")


def _binding_present(
    port: DeploymentPublishedPort, observed: dict[str, Any] | None
) -> bool:
    """Require a real host address and exact or allocated host port."""
    entries = (observed or {}).get(f"{port.container_port}/{port.protocol}") or ()
    return any(
        e.get("HostIp") == port.host_ip
        and str(e.get("HostPort", "")).isdigit()
        and (port.host_port is None or str(e["HostPort"]) == str(port.host_port))
        for e in entries
    )


def realize_publications(
    backend: DockerComposeBackend, realization: DeploymentRealizationSpec
) -> LabResult | None:
    """Use the existing byte relay when Docker drops an internal publication."""
    try:
        return _realize_publications(backend, realization)
    except (
        BackendTimeoutError,
        OwnershipConflictError,
        OSError,
        ValueError,
        KeyError,
        AttributeError,
    ):
        return LabResult(
            success=False,
            error="Native publication ownership or target readback failed.",
        )


def _realize_publications(
    backend: DockerComposeBackend, realization: DeploymentRealizationSpec
) -> LabResult | None:
    """Resolve absent bindings and apply only their owned apparatus."""
    if "native-range" not in getattr(backend, "_boundary_receipts", {}):
        return None
    pending = _pending_publications(backend, realization)
    failure = None
    if pending:
        network, failure = _prepare_publication_network(backend)
        if failure is None:
            failure = _create_publications(backend, pending, network)
    return failure


def _pending_publications(
    backend: DockerComposeBackend, realization: DeploymentRealizationSpec
) -> list[tuple[DeploymentNodeRealization, DeploymentPublishedPort]]:
    """Select only declarations Docker did not effectively publish."""
    pending = []
    for node in realization.nodes:
        if node.published_ports:
            observed = publication_bindings(backend, node.container_name)
            pending.extend(
                (node, port)
                for port in node.published_ports
                if not _binding_present(port, observed)
            )
    return pending


def _prepare_publication_network(
    backend: DockerComposeBackend,
) -> tuple[str | None, LabResult | None]:
    """Build existing apparatus and protect its bridge before any process."""
    failures = backend.ensure_generic_base_image(OPERATOR_ACCESS_IMAGE)
    if failures:
        return None, LabResult(
            success=False, error="Native publication relay image was unavailable."
        )
    network, failures = backend._ensure_operator_access_network()
    if failures or network is None:
        return None, LabResult(
            success=False, error="Native publication network was unavailable."
        )
    return network, refresh_native_policy(backend)


def _create_publications(
    backend: DockerComposeBackend,
    pending: list[tuple[DeploymentNodeRealization, DeploymentPublishedPort]],
    network: str,
) -> LabResult | None:
    """Stop at the first publication whose ownership or readback fails."""
    for node, port in pending:
        failure = _create_publication(backend, node, port, network)
        if failure is not None:
            return failure
    return None


def _publication_target(
    backend: DockerComposeBackend, node: DeploymentNodeRealization
) -> tuple[str, str, str]:
    """Bind the relay to the actual owned node address, never a new link."""
    native = backend._resolve_owned_container_id(node.container_name)
    attached = (
        backend.container_inspect(native).get("NetworkSettings", {}).get("Networks", {})
    )
    if not attached:
        raise ValueError("native publication target has no network")
    network = min(attached)
    address = attached[network]["IPAddress"]
    if not address:
        raise ValueError("native publication target requires IPv4")
    return native, network, address


def _create_publication(
    backend: DockerComposeBackend,
    node: DeploymentNodeRealization,
    port: DeploymentPublishedPort,
    network: str,
) -> LabResult | None:
    """Create dormant apparatus, receipt it, then connect and start it."""
    native, target_network, target = _publication_target(backend, node)
    identity = f"{node.address}/{port.container_port}/{port.protocol}"
    semantic = _PREFIX + hashlib.sha256(identity.encode()).hexdigest()[:16]
    backend._remove_existing_relay(semantic)
    ownership = backend._ensure_resource_ownership()
    command = _publication_command(
        backend, ownership, semantic, native, target, port, network
    )
    created = backend._run([*command, OPERATOR_ACCESS_IMAGE], timeout=60)
    relay_id = created.stdout.strip()
    if created.returncode != 0 or not relay_id:
        return LabResult(
            success=False, error="Native publication relay creation failed."
        )
    failure = _record_publication(backend, ownership, semantic, node, relay_id)
    if failure is None:
        failure = _activate_publication(backend, native, target_network, relay_id, port)
    return failure


def _publication_command(
    backend: DockerComposeBackend,
    ownership: WorkspaceOwnership,
    semantic: str,
    native: str,
    target: str,
    port: DeploymentPublishedPort,
    network: str,
) -> list[str]:
    """Reuse the existing credential-free relay with minimum capabilities."""
    labels = {
        **ownership.labels(attempt_id=backend._resource_attempt_id),
        "com.docker.compose.project": backend._project_name,
        _TARGET: native,
        "lilrae.publication.address": target,
        "lilrae.publication.port": str(port.container_port),
        "lilrae.publication.protocol": port.protocol,
    }
    command = [
        "docker",
        "create",
        "--name",
        ownership.container_name(semantic),
        "--network",
        network,
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=64m",
        "-p",
        f"{'[' + port.host_ip + ']' if ':' in port.host_ip else port.host_ip}:"
        f"{port.host_port or ''}:{port.container_port}/{port.protocol}",
    ]
    for key, value in labels.items():
        command += ["--label", f"{key}={value}"]
    for value in (
        f"APTL_PROXY_TARGET_HOST={target}",
        f"APTL_PROXY_TARGET_PORT={port.container_port}",
        f"APTL_PROXY_LISTEN_PORT={port.container_port}",
        f"LILRAE_PROXY_PROTOCOL={port.protocol}",
    ):
        command += ["-e", value]
    return command


def _record_publication(
    backend: DockerComposeBackend,
    ownership: WorkspaceOwnership,
    semantic: str,
    node: DeploymentNodeRealization,
    relay_id: str,
) -> LabResult | None:
    """Record exact container ownership or remove the just-created object."""
    try:
        ownership.record(
            ResourceReceipt(
                kind="container",
                native_id=relay_id,
                external_name=ownership.container_name(semantic),
                semantic_name=semantic,
                node_address=f"publication.{node.address}",
                workspace_id=ownership.workspace_id,
                project_name=ownership.project_name,
                daemon_id=backend._ownership_daemon_id(),
                attempt_id=backend._resource_attempt_id,
                managed_by="direct",
            )
        )
    except OwnershipConflictError:
        backend._run(remove_container_command(relay_id), timeout=60)
        return LabResult(
            success=False, error="Native publication relay ownership failed."
        )
    return None


def _activate_publication(
    backend: DockerComposeBackend,
    native: str,
    target_network: str,
    relay_id: str,
    port: DeploymentPublishedPort,
) -> LabResult | None:
    """Start only after receipt capture, and require effective readback."""
    connected = backend._run(
        ["docker", "network", "connect", target_network, relay_id], timeout=60
    )
    started = (
        backend._run(["docker", "start", relay_id], timeout=60)
        if connected.returncode == 0
        else connected
    )
    if started.returncode != 0 or not _binding_present(
        port, publication_bindings(backend, native)
    ):
        return LabResult(
            success=False, error="Native publication relay readback failed."
        )
    return None
