"""Compose realization of application accounts (issue #1273, ADR-046).

An SDL account placed on a product node declares the credential a participant
or attacker meets at that product's console. The product's implementation
profile names its account provider; this mixin makes the authored
``secret_fixture`` credential true there and proves it by authenticating with
it. A provider that cannot apply or prove the declared credential fails the
start with a bounded reason; it never substitutes another credential.

Every request runs inside the container that serves the product, against its
own loopback listener, with each value on stdin
(:mod:`aptl.core.deployment._application_account_requests`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from aptl.core.deployment import _account_provider as provider
from aptl.core.deployment import _application_account_requests as requests
from aptl.core.deployment._compose_account_verification import _failure
from aptl.core.deployment.realization import (
    DeploymentAccountRealization,
    DeploymentNodeRealization,
)
from aptl.core.lab_types import LabResult
from aptl.core.services import wait_for_service

_CURL = ["curl", "--config", "-"]
_PHP = "php"
_EXEC_TIMEOUT = 60
# A product finishes creating its env-declared principal shortly after its
# listener answers, so a proof is retried briefly before it fails the start.
_PROOF_TIMEOUT = 180
_PROOF_INTERVAL = 5

#: The loopback listener each product serves its API on, as ``(scheme, port)``.
#: These are image facts; the node must also declare the port as an SDL service.
_PRODUCT_LISTENERS: dict[str, tuple[str, int]] = {
    provider.OPENSEARCH_SECURITY: ("https", 9200),
    provider.WAZUH_API: ("https", 55000),
    provider.MISP: ("https", 443),
}
_KEY = "key"


@dataclass(frozen=True)
class _Ingress(object):
    """Where a product's API is reached: the serving container and its URL."""

    container: str
    base_url: str


def product_ingress(
    account_provider: str,
    node: DeploymentNodeRealization,
    nodes: Sequence[DeploymentNodeRealization],
) -> _Ingress | None:
    """Return the container and loopback URL that serve ``node``'s product API.

    A product the node serves itself is reached on its declared service port. A
    product whose API another node fronts (Shuffle's backend has no HTTP client
    and no listener of its own for participants) is reached through the node
    whose SDL application route names ``node`` as its upstream target.
    """

    listener = _PRODUCT_LISTENERS.get(account_provider)
    if listener is not None:
        scheme, port = listener
        if node.container_name and port in _declared_listener_ports(node):
            return _Ingress(node.container_name, f"{scheme}://localhost:{port}")
        return None
    return _fronting_ingress(node, nodes)


def _declared_listener_ports(node: DeploymentNodeRealization) -> set[int]:
    """Return the service ports the node's SDL declares."""

    return {int(item.port) for item in node.services}


def _fronting_ingress(
    node: DeploymentNodeRealization,
    nodes: Sequence[DeploymentNodeRealization],
) -> _Ingress | None:
    """Return the single node whose application route fronts ``node``."""

    found: list[_Ingress] = []
    for candidate in nodes:
        for scheme, port in _routes_to(candidate, node.name):
            if candidate.container_name:
                found.append(
                    _Ingress(candidate.container_name, f"{scheme}://localhost:{port}")
                )
    unique = set(found)
    return found[0] if len(unique) == 1 else None


def _routes_to(
    candidate: DeploymentNodeRealization, target: str
) -> list[tuple[str, int]]:
    """Return ``(scheme, port)`` of each application on ``candidate`` routing to ``target``."""

    runtime = candidate.runtime
    listeners = {item.name: int(item.port) for item in candidate.services}
    routes: list[tuple[str, int]] = []
    for application in getattr(runtime, "applications", None) or ():
        targets = {
            str(getattr(getattr(route, "upstream_target", None), "target_node_ref", ""))
            for route in (getattr(application, "routes", None) or ())
        }
        port = listeners.get(str(getattr(application, "service", "")), 0)
        protocol = getattr(application, "protocol", "https")
        if target in targets and port:
            routes.append((str(getattr(protocol, "value", protocol)).lower(), port))
    return routes


class ComposeApplicationAccountMixin(object):
    """Realize and prove application accounts through ``container_exec``."""

    def _realize_application_target(
        self,
        target: provider.AccountTarget,
        nodes: Sequence[DeploymentNodeRealization],
        *,
        timeout: int,
    ) -> LabResult | None:
        """Realize one product's declared accounts, passwords before keys."""

        node = next(
            (item for item in nodes if item.container_name == target.container_name),
            None,
        )
        ingress = (
            product_ingress(target.provider, node, nodes) if node is not None else None
        )
        if ingress is None:
            return _failure(
                target.container_name, "account-provider-ingress-unresolved"
            )
        return self._realize_product_accounts(target, ingress, timeout)

    def _realize_product_accounts(
        self, target: provider.AccountTarget, ingress: _Ingress, timeout: int
    ) -> LabResult | None:
        """Realize one product's accounts in password-before-key order."""

        ordered = sorted(target.accounts, key=lambda item: item.auth_method == _KEY)
        for account in ordered:
            reason = self._realize_application_account(
                target, ingress, account, timeout=timeout
            )
            if reason is not None:
                return _failure(account.address, reason)
        return None

    def _realize_application_account(
        self,
        target: provider.AccountTarget,
        ingress: _Ingress,
        account: DeploymentAccountRealization,
        *,
        timeout: int,
    ) -> str | None:
        """Dispatch one account to its product's realization."""

        username = account.username
        secret = account.credential.value  # type: ignore[union-attr]
        kind = target.provider
        if kind == provider.MISP:
            return self._realize_misp_account(target, ingress, account, timeout=timeout)
        proofs = {
            provider.OPENSEARCH_SECURITY: requests.opensearch_login,
            provider.WAZUH_API: requests.wazuh_api_login,
            provider.SHUFFLE: requests.shuffle_login,
        }
        return self._await_proof(ingress, proofs[kind](username, secret), timeout)

    def _realize_misp_account(
        self,
        target: provider.AccountTarget,
        ingress: _Ingress,
        account: DeploymentAccountRealization,
        *,
        timeout: int,
    ) -> str | None:
        """Converge a MISP password or read-only API key, then prove it."""

        secret = account.credential.value  # type: ignore[union-attr]
        if account.auth_method != _KEY:
            payload = requests.misp_password_input(account.username, secret)
            status = self._run_php(
                ingress, requests.MISP_PASSWORD_PROGRAM, payload, timeout
            )
            return _misp_reason(status)
        owners = [item for item in target.accounts if item.auth_method != _KEY]
        if len(owners) != 1:
            return "account-key-owner-ambiguous"
        return self._realize_misp_key(ingress, owners[0], account, timeout)

    def _realize_misp_key(
        self,
        ingress: _Ingress,
        owner: DeploymentAccountRealization,
        account: DeploymentAccountRealization,
        timeout: int,
    ) -> str | None:
        """Apply one declared API key and prove its read-only access."""

        secret = account.credential.value  # type: ignore[union-attr]
        payload = requests.misp_key_input(owner.username, account.username, secret)
        reason = _misp_reason(
            self._run_php(ingress, requests.MISP_KEY_PROGRAM, payload, timeout)
        )
        if reason is not None:
            return reason
        return self._await_proof(ingress, requests.misp_key_login(secret), timeout)

    def _await_proof(
        self,
        ingress: _Ingress,
        proof: Sequence[requests.CurlStep],
        timeout: int,
    ) -> str | None:
        """Retry a credential proof briefly; refuse the start if it never holds."""

        result = wait_for_service(
            lambda: self._curl_proves(ingress, proof, timeout),
            _PROOF_TIMEOUT,
            _PROOF_INTERVAL,
            f"account-credential:{ingress.container}",
        )
        return None if result.ready else "account-credential-not-authenticable"

    def _curl_proves(
        self,
        ingress: _Ingress,
        proof: Sequence[requests.CurlStep],
        timeout: int,
    ) -> bool:
        """Return whether every step of ``proof`` answered 2xx."""

        codes = self._run_curl(ingress, proof, timeout)
        return len(codes) == len(proof) and all(map(requests.succeeded, codes))

    def _run_curl(
        self,
        ingress: _Ingress,
        steps: Sequence[requests.CurlStep],
        timeout: int,
    ) -> tuple[int, ...]:
        """Run one curl program in the serving container; return its statuses."""

        completed = self.container_exec_with_input(  # type: ignore[attr-defined]
            ingress.container,
            _CURL,
            requests.curl_config(ingress.base_url, steps),
            timeout=min(timeout, _EXEC_TIMEOUT),
        )
        if completed.returncode != 0:
            return ()
        return requests.status_codes(completed.stdout)

    def _run_php(
        self,
        ingress: _Ingress,
        program: str,
        payload: str,
        timeout: int,
    ) -> str:
        """Run one fixed PHP program in the serving container; return its status."""

        completed = self.container_exec_with_input(  # type: ignore[attr-defined]
            ingress.container,
            [_PHP, "-r", program],
            payload,
            timeout=min(timeout, _EXEC_TIMEOUT),
        )
        if completed.returncode != 0:
            return ""
        return requests.program_status(completed.stdout)


_MISP_REASONS: dict[str, str | None] = {
    "current": None,
    "applied": None,
    "absent": "account-principal-absent",
    "unproven": "account-credential-not-authenticable",
}


def _misp_reason(status: str) -> str | None:
    """Map a MISP database program's status word to a failure reason."""

    return _MISP_REASONS.get(status, "account-credential-not-applied")


__all__ = ("ComposeApplicationAccountMixin", "product_ingress")
