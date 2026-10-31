"""Desktop discovery verifies the issued certificate before trusting its names."""

from __future__ import annotations

import socket
import ssl
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from aptl.core import _participant_desktop_tls as tls
from aptl.core.soc_ca import ServiceCert, ensure_soc_certs
from aptl.core.deployment._compose_stateful_constants import SOC_CERT_PROFILE


@pytest.fixture(autouse=True)
def handshake_keys(monkeypatch):
    """Real TLS handshakes need full keys instead of the shared fast-chain fixture."""

    from aptl.core import _soc_ca_builders

    monkeypatch.setattr(_soc_ca_builders, "_CA_KEY_SIZE", 2048)
    monkeypatch.setattr(_soc_ca_builders, "_SVC_KEY_SIZE", 2048)


def _issued(
    root: Path, *, impostor_names: tuple[str, ...] = (), keystore: bool = False
):
    services = [
        ServiceCert(
            "console",
            "console.example.test",
            ("localhost", "console.example.test"),
            needs_keystore=keystore,
        )
    ]
    if impostor_names:
        services.append(
            ServiceCert("impostor", "impostor.example.test", impostor_names)
        )
    result = ensure_soc_certs(root, services=tuple(services))
    assert result.success
    node = SimpleNamespace(address="provision.node.console")
    outputs = tuple(
        SimpleNamespace(
            name=name,
            path=path,
            sensitivity=sensitivity,
            disposition="consumer_selected",
        )
        for name, path, sensitivity in (
            ("ca", "lab-ca.pem", "public"),
            ("leaf", "console/server.pem", "public"),
            ("key", "console/server.key", "secret"),
        )
    )
    consumer = SimpleNamespace(
        target_address=node.address, selected_outputs=("ca", "leaf", "key")
    )
    artifact = SimpleNamespace(
        generator="certificate_bundle",
        provenance=SOC_CERT_PROFILE,
        outputs=outputs,
        consumers=(consumer,),
    )
    return SimpleNamespace(generated_artifacts=(artifact,)), node


@contextmanager
def _server(root: Path, service: str = "console"):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    directory = root / "config/soc_certs" / service
    context.load_cert_chain(directory / "server.pem", directory / "server.key")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(10)

    def accept() -> None:
        try:
            with (
                listener.accept()[0] as connection,
                context.wrap_socket(connection, server_side=True),
            ):
                pass
        except OSError:
            pass

    worker = threading.Thread(target=accept, daemon=True)
    worker.start()
    try:
        yield listener.getsockname()[1]
    finally:
        listener.close()
        worker.join(timeout=15)
        assert not worker.is_alive()


def test_the_probe_verifies_the_issued_leaf_and_reads_only_public_outputs(
    tmp_path, mocker
):
    realization, node = _issued(tmp_path)
    read = mocker.spy(tls, "read_contained_nofollow")
    create = mocker.spy(tls.ssl, "create_default_context")
    with _server(tmp_path) as port:
        names = tls.served_certificate_names(tmp_path, realization, node, port)

    assert names == frozenset({"localhost", "console.example.test"})
    assert create.spy_return.check_hostname is True
    assert create.spy_return.verify_mode == ssl.CERT_REQUIRED
    assert create.spy_return.minimum_version == ssl.TLSVersion.TLSv1_2
    assert {str(call.args[1]) for call in read.call_args_list} == {
        "config/soc_certs/lab-ca.pem",
        "config/soc_certs/console/server.pem",
    }


def test_issued_artifacts_support_strict_tls_validation(tmp_path, monkeypatch):
    realization, node = _issued(tmp_path)
    original = tls.ssl.create_default_context

    def strict_context(**kwargs):
        context = original(**kwargs)
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        return context

    monkeypatch.setattr(tls.ssl, "create_default_context", strict_context)
    with _server(tmp_path) as port:
        assert "localhost" in tls.served_certificate_names(
            tmp_path, realization, node, port
        )


def test_an_untrusted_authority_is_refused(tmp_path):
    realization, node = _issued(tmp_path)
    other = tmp_path / "other"
    _issued(other)
    with _server(other) as port:
        with pytest.raises(ssl.SSLCertVerificationError):
            tls.served_certificate_names(tmp_path, realization, node, port)


def test_a_different_hostname_is_refused(tmp_path):
    realization, node = _issued(tmp_path, impostor_names=("impostor.example.test",))
    with _server(tmp_path, "impostor") as port:
        with pytest.raises(ssl.SSLCertVerificationError):
            tls.served_certificate_names(tmp_path, realization, node, port)


def test_a_different_leaf_from_the_same_authority_is_refused(tmp_path):
    realization, node = _issued(tmp_path, impostor_names=("localhost",))
    with _server(tmp_path, "impostor") as port:
        with pytest.raises(ValueError, match="console-certificate-mismatch"):
            tls.served_certificate_names(tmp_path, realization, node, port)


def test_another_nodes_certificate_is_not_an_identity_source(tmp_path):
    realization, _node = _issued(tmp_path)
    foreign = SimpleNamespace(address="provision.node.other")
    with pytest.raises(ValueError, match="console-certificate-unavailable"):
        tls.served_certificate_names(tmp_path, realization, foreign, 443)


def test_linked_certificate_outputs_are_refused(tmp_path):
    realization, node = _issued(tmp_path)
    source = tmp_path / "config/soc_certs/console/server.pem"
    saved = source.with_suffix(".saved")
    source.rename(saved)
    source.symlink_to(saved)
    with pytest.raises(ValueError, match="console-certificate-unavailable"):
        tls.served_certificate_names(tmp_path, realization, node, 443)


def test_keystore_delivery_uses_only_its_public_companion(tmp_path, mocker):
    realization, node = _issued(tmp_path, keystore=True)
    artifact = realization.generated_artifacts[0]
    keystore = SimpleNamespace(
        name="keystore",
        path="console/keystore.p12",
        sensitivity="secret",
        disposition="consumer_selected",
    )
    artifact.outputs = (artifact.outputs[0], keystore)
    artifact.consumers[0].selected_outputs = ("ca", "keystore")
    read = mocker.spy(tls, "read_contained_nofollow")

    with _server(tmp_path) as port:
        names = tls.served_certificate_names(tmp_path, realization, node, port)

    assert "localhost" in names
    assert {str(call.args[1]) for call in read.call_args_list} == {
        "config/soc_certs/lab-ca.pem",
        "config/soc_certs/console/server.pem",
    }


def test_released_console_bindings_have_a_public_certificate_identity(released_techvault_realization):
    result = released_techvault_realization
    realization = result.deployment_spec(sorted(result.profiles))
    expected = {
        "shuffle-frontend": "shuffle-frontend/server.pem",
        "wazuh-dashboard": "wazuh.dashboard.pem",
    }
    for node in realization.nodes:
        if node.name not in expected:
            continue
        paths = set()
        for artifact in realization.generated_artifacts:
            if artifact.generator == "certificate_bundle":
                selected = tls._selected_outputs(artifact, node.address)
                paths.update(tls._selected_certificate_paths(artifact, selected))
        assert expected[node.name] in paths
