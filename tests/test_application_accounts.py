"""Application account providers make the declared credential true (#1273).

Each provider runs inside the container that serves the product, keeps every
credential on stdin, and refuses the start when the declared credential does
not authenticate. These tests drive the providers through a fake
``container_exec_with_input`` that models each product's API.
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from aptl.core.deployment import _account_provider as provider
from aptl.core.deployment import _application_account_requests as requests
from aptl.core.deployment import _compose_application_accounts as accounts
from aptl.core.deployment.realization import (
    DeclaredAccountCredential,
    DeploymentAccountRealization,
    DeploymentNodeRealization,
    DeploymentServicePort,
)

_SECRET = "In-World-Console-2026!"


def _node(name, container, *, listeners=(), applications=()):
    runtime = SimpleNamespace(applications=list(applications))
    return DeploymentNodeRealization(
        address=f"provision.node.{name}",
        name=name,
        service_name=name,
        container_name=container,
        networks=(),
        services=tuple(
            DeploymentServicePort(service, port) for service, port in listeners
        ),
        runtime=runtime,
    )


def _account(username, *, auth_method="password", secret=_SECRET, name="console"):
    return DeploymentAccountRealization(
        address=f"provision.account-placement.{name}",
        target_address="provision.node.console",
        username=username,
        auth_method=auth_method,
        credential=DeclaredAccountCredential(
            credential_id=f"{name}-primary", value=secret
        ),
    )


class _Product:
    """A fake product: answers curl programs and MISP database programs."""

    def __init__(self, *, accepts=(), misp=None):
        self.accepts = set(accepts)
        self.misp = misp if misp is not None else {}
        self.calls: list[tuple[str, list[str], str]] = []

    def __call__(self, container, cmd, payload, *, timeout=None):
        self.calls.append((container, list(cmd), payload))
        if cmd[0] == "curl":
            return self._curl(payload)
        return self._php(cmd[2], payload)

    def _curl(self, config):
        blocks = config.split("\nnext\n")
        codes = []
        for block in blocks:
            url = _field(block, "url")
            headers = _fields(block, "header")
            body = _field(block, "data-raw")
            codes.append(self._answer(url, headers, body))
        return _done("".join(f"{code}\n" for code in codes))

    def _answer(self, url, headers, body):
        presented = {h for h in headers if h.startswith("Authorization")}
        if body is not None:
            presented.add(body)
        return 200 if presented & self.accepts else 401

    def _php(self, program, payload):
        data = json.loads(payload)
        if program == requests.MISP_PASSWORD_PROGRAM:
            if data["username"] not in self.misp:
                return _done("absent\n")
            current = self.misp[data["username"]] == data["secret"]
            self.misp[data["username"]] = data["secret"]
            return _done("current\n" if current else "applied\n")
        if data["owner"] not in self.misp:
            return _done("absent\n")
        self.accepts.add(f"Authorization: {data['secret']}")
        return _done("applied\n")


def _field(block, key):
    values = _fields(block, key)
    return values[0] if values else None


def _fields(block, key):
    prefix = f"{key} = "
    return [
        json.loads(line[len(prefix) :])
        for line in block.splitlines()
        if line.startswith(prefix)
    ]


def _done(stdout, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class _Backend(accounts.ComposeApplicationAccountMixin):
    def __init__(self, product):
        self.container_exec_with_input = product


@pytest.fixture(autouse=True)
def _instant_proofs(monkeypatch):
    monkeypatch.setattr(accounts, "_PROOF_TIMEOUT", 0)


def _target(kind, container, *items):
    return provider.AccountTarget(
        container_name=container, provider=kind, accounts=items
    )


def _run(kind, product, node, *items, nodes=None):
    backend = _Backend(product)
    target = _target(kind, node.container_name, *items)
    return backend._realize_application_target(target, nodes or (node,), timeout=30)


def _assert_no_secret_in_argv(product, secret=_SECRET):
    for _container, argv, _payload in product.calls:
        assert all(secret not in token for token in argv)


def test_an_env_realized_credential_is_proven_on_the_declared_listener():
    node = _node("wazuh-manager", "aptl-wazuh-manager", listeners=(("api", 55000),))
    product = _Product(accepts={requests.basic_authorization("wazuh-wui", _SECRET)})

    assert _run(provider.WAZUH_API, product, node, _account("wazuh-wui")) is None
    container, argv, config = product.calls[0]
    assert container == "aptl-wazuh-manager"
    assert argv == ["curl", "--config", "-"]
    assert '"https://localhost:55000/security/user/authenticate"' in config
    _assert_no_secret_in_argv(product)


def test_a_credential_that_never_authenticates_fails_the_start():
    node = _node("wazuh-indexer", "aptl-wazuh-indexer", listeners=(("search", 9200),))
    result = _run(provider.OPENSEARCH_SECURITY, _Product(), node, _account("admin"))

    assert result is not None
    assert result.success is False
    assert "account-credential-not-authenticable" in (result.error or "")
    assert _SECRET not in (result.error or "")


def test_an_undeclared_listener_is_refused_before_any_request():
    node = _node("wazuh-indexer", "aptl-wazuh-indexer", listeners=(("search", 9201),))
    product = _Product()
    result = _run(provider.OPENSEARCH_SECURITY, product, node, _account("admin"))

    assert "account-provider-ingress-unresolved" in (result.error or "")
    assert product.calls == []


def test_account_requests_do_not_expose_authentication_in_their_repr():
    step = requests.opensearch_login("admin@example.test", _SECRET)[0]

    assert requests.basic_authorization("admin@example.test", _SECRET) not in repr(step)


def test_shuffle_is_proven_through_the_node_that_fronts_its_backend():
    backend = _node(
        "shuffle-backend", "aptl-shuffle-backend", listeners=(("api", 5001),)
    )
    route = SimpleNamespace(
        upstream_target=SimpleNamespace(target_node_ref="shuffle-backend")
    )
    frontend = _node(
        "shuffle-frontend",
        "aptl-shuffle-frontend",
        listeners=(("https", 443),),
        applications=(
            SimpleNamespace(
                service="https",
                protocol=SimpleNamespace(value="https"),
                routes=[route],
            ),
        ),
    )
    login = requests.json_body({"username": "admin@example.test", "password": _SECRET})
    product = _Product(accepts={login})

    result = _run(
        provider.SHUFFLE,
        product,
        backend,
        _account("admin@example.test"),
        nodes=(backend, frontend),
    )

    assert result is None
    assert product.calls[0][0] == "aptl-shuffle-frontend"
    assert '"https://localhost:443/api/v1/login"' in product.calls[0][2]


def test_misp_sets_the_password_then_adds_the_read_only_key_it_proves():
    node = _node("misp", "aptl-misp", listeners=(("https", 443),))
    key = "7ea54cbe19564f9893940770bbc659f890726557"
    product = _Product(misp={"admin@example.test": "old"})
    sync = _account("techvault-sync", auth_method="key", secret=key, name="sync")

    result = _run(provider.MISP, product, node, sync, _account("admin@example.test"))

    assert result is None
    assert product.misp["admin@example.test"] == _SECRET
    php = [call for call in product.calls if call[1][0] == "php"]
    assert [json.loads(call[2]).get("owner") for call in php] == [
        None,
        "admin@example.test",
    ]
    assert json.loads(php[1][2])["comment"] == "techvault-sync"
    _assert_no_secret_in_argv(product)
    _assert_no_secret_in_argv(product, key)


def test_misp_refuses_a_principal_its_database_does_not_hold():
    node = _node("misp", "aptl-misp", listeners=(("https", 443),))
    result = _run(provider.MISP, _Product(), node, _account("admin@example.test"))

    assert "account-principal-absent" in (result.error or "")


def test_misp_refuses_a_key_with_no_single_owner():
    node = _node("misp", "aptl-misp", listeners=(("https", 443),))
    sync = _account("sync", auth_method="key", secret="k" * 40, name="sync")
    result = _run(provider.MISP, _Product(), node, sync)

    assert "account-key-owner-ambiguous" in (result.error or "")


def test_curl_configuration_cannot_be_broken_out_of_by_a_value():
    hostile = 'x"\nurl = "http://evil'
    config = requests.curl_config(
        "https://localhost:1", requests.shuffle_login("admin", hostile)
    )

    assert config.count("\nurl = ") == 1
    assert (
        "evil"
        not in [line for line in config.splitlines() if line.startswith("url")][0]
    )


def test_every_released_techvault_account_provider_resolves_its_ingress(released_techvault_realization):
    """Each SOC product the released pack declares is reachable (#1273)."""

    realization = released_techvault_realization
    spec = realization.deployment_spec(sorted(realization.profiles))
    resolved = {
        node.backend_account_provider: accounts.product_ingress(
            node.backend_account_provider, node, spec.nodes
        )
        for node in spec.nodes
        if node.backend_account_provider in provider.APPLICATION_ACCOUNT_PROVIDERS
    }

    assert set(resolved) == set(provider.APPLICATION_ACCOUNT_PROVIDERS)
    assert {kind: item.base_url for kind, item in resolved.items()} == {
        provider.OPENSEARCH_SECURITY: "https://localhost:9200",
        provider.WAZUH_API: "https://localhost:55000",
        provider.MISP: "https://localhost:443",
        provider.SHUFFLE: "https://localhost:443",
    }
    assert resolved[provider.SHUFFLE].container == "aptl-shuffle-frontend"
