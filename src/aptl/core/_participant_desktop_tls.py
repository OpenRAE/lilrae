"""Verify desktop TLS against the backend's declared, issued certificates."""

from __future__ import annotations

import socket
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from aptl.core.deployment._compose_stateful_model import (
    _consumer_output_names,
    artifact_source_path,
)
from aptl.core.deployment._compose_stateful_constants import SOC_CERT_PROFILE
from aptl.core.soc_ca import derive_soc_service_certs
from aptl.utils.pathsafe import PathContainmentError, read_contained_nofollow

_LOOPBACK = "127.0.0.1"
_TLS_TIMEOUT = 10


def served_certificate_names(
    root: Path, realization: object, node: object, port: int
) -> frozenset[str]:
    """Authenticate the endpoint's chain, hostname and exact issued leaf.

    Identity comes from public certificate outputs selected for this node,
    never from an unauthenticated peer. No application data is exchanged.
    """

    expected, authorities = _node_material(root, realization, node)
    names = _certificate_names(expected)
    ca_data = "".join(
        certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")
        for certificate in authorities
    )
    context = ssl.create_default_context(cadata=ca_data)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with (
        socket.create_connection((_LOOPBACK, port), timeout=_TLS_TIMEOUT) as raw,
        context.wrap_socket(raw, server_hostname=_connection_name(names)) as tls,
    ):
        observed = tls.getpeercert(binary_form=True)
    if observed != expected.public_bytes(serialization.Encoding.DER):
        raise ValueError("console-certificate-mismatch")
    return names


def _connection_name(names: frozenset[str]) -> str:
    """Prefer a covered loopback identity, then a declared DNS identity."""

    for preferred in ("localhost", _LOOPBACK, "::1"):
        if preferred in names:
            return preferred
    if not names:
        raise ValueError("console-certificate-unnamed")
    return min(names)


def _certificate_names(certificate: x509.Certificate) -> frozenset[str]:
    """Read the DNS and IP SANs of one backend-issued leaf."""

    try:
        names = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound:
        raise ValueError("console-certificate-unnamed") from None
    dns = names.get_values_for_type(x509.DNSName)
    addresses = [str(value) for value in names.get_values_for_type(x509.IPAddress)]
    return frozenset(name.lower() for name in (*dns, *addresses))


def _node_material(
    root: Path, realization: object, node: object
) -> tuple[x509.Certificate, list[x509.Certificate]]:
    """Resolve public certificate outputs through declared artifact consumers."""

    authorities: list[x509.Certificate] = []
    leaves: dict[bytes, x509.Certificate] = {}
    address = getattr(node, "address", None)
    if not address:
        raise ValueError("console-certificate-node-missing")
    for artifact in getattr(realization, "generated_artifacts", ()):
        if artifact.generator != "certificate_bundle":
            continue
        selected = _selected_outputs(artifact, address)
        if not selected:
            continue
        roots, candidates = _artifact_material(root, artifact, selected)
        authorities.extend(roots)
        leaves.update(candidates)
    if len(leaves) != 1 or not authorities:
        raise ValueError("console-certificate-unavailable")
    return next(iter(leaves.values())), authorities


def _selected_outputs(artifact: object, address: str) -> set[str]:
    """Use the same consumer-selection rules as artifact delivery."""

    return {
        name
        for consumer in artifact.consumers
        if consumer.target_address == address
        for name in _consumer_output_names(artifact, consumer)
    }


def _artifact_material(
    root: Path, artifact: object, selected: set[str]
) -> tuple[list[x509.Certificate], dict[bytes, x509.Certificate]]:
    """Read public PEM outputs without following links or opening private keys."""

    relative = artifact_source_path(root, artifact).relative_to(root.resolve())
    authorities: list[x509.Certificate] = []
    leaves: dict[bytes, x509.Certificate] = {}
    selected_paths = _selected_certificate_paths(artifact, selected)
    public_paths = {
        output.path for output in artifact.outputs if _public_certificate(output)
    } | selected_paths
    for path in sorted(public_paths):
        certificate = _read_certificate(root, relative / path)
        if _is_authority(certificate):
            authorities.append(certificate)
        elif path in selected_paths:
            leaves[certificate.public_bytes(serialization.Encoding.DER)] = certificate
    return authorities, leaves


def _selected_certificate_paths(artifact: object, selected: set[str]) -> set[str]:
    """Resolve public identities for PEM and native PKCS#12 deliveries.

    The SOC producer writes a public PEM beside its keystore, including when
    only the keystore is selected for delivery. Reuse that producer's contract;
    the desktop probe never opens private keys or keystore passwords.
    """

    outputs = [output for output in artifact.outputs if output.name in selected]
    paths = {output.path for output in outputs if _public_certificate(output)}
    if artifact.provenance == SOC_CERT_PROFILE:
        services = derive_soc_service_certs(tuple(output.path for output in outputs))
        paths.update(
            f"{service.name}/{service.cert_filename}"
            for service in services
            if service.needs_keystore
        )
    return paths


def _read_certificate(root: Path, relative: Path) -> x509.Certificate:
    """Translate rejected file paths into a bounded desktop failure."""

    try:
        return x509.load_pem_x509_certificate(read_contained_nofollow(root, relative))
    except (PathContainmentError, ValueError):
        raise ValueError("console-certificate-unavailable") from None


def _is_authority(certificate: x509.Certificate) -> bool:
    """A certificate without CA basic constraints is a leaf, never an issuer."""

    try:
        return certificate.extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value.ca
    except x509.ExtensionNotFound:
        return False


def _public_certificate(output: object) -> bool:
    """Exclude secret outputs and key/container formats before any file read."""

    path = Path(output.path)
    return (
        output.sensitivity != "secret"
        and path.suffix.lower() in {".pem", ".crt", ".cer"}
        and not path.name.endswith("-key.pem")
    )
