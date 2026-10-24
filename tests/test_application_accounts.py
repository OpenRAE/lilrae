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
from urllib.parse import unquote, urlsplit

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

    def __init__(self, *, accepts=(), converge_grants=(), misp=None):
        self.accepts = set(accepts)
        self.converge_grants = set(converge_grants)
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
        if url.endswith(("/password/set", "/api/user")) and body is not None:
            self.accepts |= self.converge_grants
            return 204
        if url.endswith("/api/maintenance/migrate"):
            return 204
        presented = {h for h in headers if h.startswith("Authorization")}
        if body is not None:
            presented.add(body)
        return (
            200
            if presented & self.accepts
            or (url.endswith("/current") and "session" in self.accepts)
            else 401
        )

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


class _TheHiveProduct(_Product):
    """Model authenticated user creation, password changes and readback."""

    def __init__(
        self,
        *,
        users=None,
        rotation_status=204,
        apply_rotation=True,
        bootstrap_status=None,
        revoke_declared=False,
    ):
        super().__init__()
        self.users = {
            requests.THEHIVE_BOOTSTRAP_USER: requests.THEHIVE_BOOTSTRAP_PASSWORD
        }
        self.users.update(users or {})
        self.rotation_status = rotation_status
        self.apply_rotation = apply_rotation
        self.bootstrap_status = bootstrap_status
        self.revoke_declared = revoke_declared
        self.rotations = []

    def _answer(self, url, headers, body):
        path = unquote(urlsplit(url).path)
        actor = next(
            (
                user
                for user, password in self.users.items()
                if requests.basic_authorization(user, password) in headers
            ),
            None,
        )
        bootstrap = (
            requests.basic_authorization(
                requests.THEHIVE_BOOTSTRAP_USER, requests.THEHIVE_BOOTSTRAP_PASSWORD
            )
            in headers
        )
        if path.endswith("/current"):
            if bootstrap and self.bootstrap_status is not None:
                return self.bootstrap_status
            return 200 if actor else 401
        if actor is None:
            return 401
        data = json.loads(body) if body is not None else {}
        if path == "/api/v1/user":
            if data["login"] in self.users:
                return 400
            self.users[data["login"]] = "unset"
            return 201
        if path.endswith("/password/set"):
            user = path.removeprefix("/api/v1/user/").removesuffix("/password/set")
            if user == requests.THEHIVE_BOOTSTRAP_USER:
                self.rotations.append((actor, data["password"]))
                if self.rotation_status != 204:
                    return self.rotation_status
                if not self.apply_rotation:
                    return 204
                if self.revoke_declared:
                    self.users.pop(actor, None)
            self.users[user] = data["password"]
            return 204
        return 404


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


def test_thehive_creates_the_declared_administrator_then_proves_it():
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct()

    assert _run(provider.THEHIVE, product, node, _account("admin@example.test")) is None
    converge = next(
        config
        for _, _, config in product.calls
        if '"https://localhost:9000/api/v1/user"' in config
    )
    assert '"https://localhost:9000/api/v1/user"' in converge
    assert "/api/v1/user/admin%40example.test/password/set" in converge
    _assert_no_secret_in_argv(product)


def test_thehive_keeps_a_credential_that_already_authenticates():
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct(users={"admin@example.test": _SECRET})

    assert _run(provider.THEHIVE, product, node, _account("admin@example.test")) is None
    assert product.users["admin@example.test"] == _SECRET
    assert not any(
        "admin%40example.test/password/set" in config for _, _, config in product.calls
    )


def test_thehive_closes_bootstrap_access_only_after_the_declared_admin_works():
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct()

    assert _run(provider.THEHIVE, product, node, _account("admin@example.test")) is None
    assert product.users["admin@example.test"] == _SECRET
    assert (
        product.users[requests.THEHIVE_BOOTSTRAP_USER]
        != requests.THEHIVE_BOOTSTRAP_PASSWORD
    )
    assert product.rotations[0][0] == "admin@example.test"
    generated = product.rotations[0][1]
    assert 32 <= len(generated) <= 128
    _assert_no_secret_in_argv(product, generated)
    _assert_no_secret_in_argv(product)
    assert _run(provider.THEHIVE, product, node, _account("admin@example.test")) is None
    assert len(product.rotations) == 2
    assert product.rotations[0][1] != product.rotations[1][1]


def test_thehive_existing_declared_admin_also_closes_bootstrap_access():
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct(users={"admin@example.test": _SECRET})

    assert _run(provider.THEHIVE, product, node, _account("admin@example.test")) is None
    assert len(product.rotations) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"rotation_status": 403},
        {"apply_rotation": False},
        {"bootstrap_status": 500},
        {"bootstrap_status": 403},
        {"bootstrap_status": 0},
        {"revoke_declared": True},
    ],
)
def test_thehive_refuses_start_when_bootstrap_closure_is_not_proven(options):
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct(users={"admin@example.test": _SECRET}, **options)

    result = _run(provider.THEHIVE, product, node, _account("admin@example.test"))

    assert result is not None
    assert not result.success
    assert "account-bootstrap-retirement-unproven" in (result.error or "")
    assert _SECRET not in repr(result)
    for _, generated in product.rotations:
        assert generated not in repr(result)


def test_thehive_can_add_another_declared_admin_after_bootstrap_is_closed():
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct(users={"admin@example.test": _SECRET})
    product.users[requests.THEHIVE_BOOTSTRAP_USER] = "already-rotated"

    assert (
        _run(
            provider.THEHIVE,
            product,
            node,
            _account("new@example.test", secret="new-fixture", name="new"),
            _account("admin@example.test"),
        )
        is None
    )
    assert product.users["new@example.test"] == "new-fixture"
    assert len(product.rotations) == 1


def test_thehive_preserves_an_explicitly_declared_bootstrap_principal():
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct()

    assert (
        _run(provider.THEHIVE, product, node, _account(requests.THEHIVE_BOOTSTRAP_USER))
        is None
    )
    assert product.users[requests.THEHIVE_BOOTSTRAP_USER] == _SECRET


def test_thehive_does_not_rotate_without_a_working_declared_administrator():
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct()
    product.users.clear()

    result = _run(provider.THEHIVE, product, node, _account("admin@example.test"))

    assert result is not None
    assert not result.success
    assert product.rotations == []


def test_thehive_refuses_failed_exec_as_proof_of_bootstrap_retirement():
    class FailedExec(_TheHiveProduct):
        def _curl(self, config):
            result = super()._curl(config)
            if (
                requests.basic_authorization(
                    requests.THEHIVE_BOOTSTRAP_USER, requests.THEHIVE_BOOTSTRAP_PASSWORD
                )
                in config
            ):
                result.returncode = 1
            return result

    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = FailedExec(users={"admin@example.test": _SECRET})
    product.users[requests.THEHIVE_BOOTSTRAP_USER] = "already-rotated"

    result = _run(provider.THEHIVE, product, node, _account("admin@example.test"))

    assert result is not None
    assert not result.success
    assert "account-bootstrap-retirement-unproven" in (result.error or "")


def test_account_requests_do_not_expose_authentication_in_their_repr():
    step = requests.thehive_login("admin@example.test", _SECRET)[0]

    assert requests.basic_authorization("admin@example.test", _SECRET) not in repr(step)


@pytest.mark.parametrize("applies", [True, False])
def test_thehive_requires_password_replacement_even_if_the_default_login_is_locked(
    applies,
):
    node = _node("thehive", "aptl-thehive", listeners=(("thehive", 9000),))
    product = _TheHiveProduct(
        users={"admin@example.test": _SECRET},
        bootstrap_status=401,
        apply_rotation=applies,
    )

    result = _run(provider.THEHIVE, product, node, _account("admin@example.test"))

    if applies:
        assert result is None
        assert (
            product.users[requests.THEHIVE_BOOTSTRAP_USER]
            != requests.THEHIVE_BOOTSTRAP_PASSWORD
        )
    else:
        assert result is not None
        assert not result.success


def test_cortex_migrates_then_uses_the_first_run_window_for_the_administrator():
    node = _node("cortex", "aptl-cortex", listeners=(("cortex", 9001),))
    login = requests.json_body({"user": "admin@example.test", "password": _SECRET})
    product = _Product(converge_grants={login, "session"})

    assert _run(provider.CORTEX, product, node, _account("admin@example.test")) is None
    assert "/api/maintenance/migrate" in product.calls[0][2]
    assert '"http://localhost:9001/api/user"' in product.calls[2][2]
    _assert_no_secret_in_argv(product)


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


def test_every_released_techvault_account_provider_resolves_its_ingress(tmp_path):
    """Each SOC product the released pack declares is reachable (#1273)."""

    from tests.techvault_pack import realize_techvault_pack

    realization = realize_techvault_pack(tmp_path)
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
        provider.THEHIVE: "https://localhost:9000",
        provider.CORTEX: "http://localhost:9001",
        provider.MISP: "https://localhost:443",
        provider.SHUFFLE: "https://localhost:443",
    }
    assert resolved[provider.SHUFFLE].container == "aptl-shuffle-frontend"
