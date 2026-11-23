"""Read-only build and approved-route checks for the managed executor."""

import os
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from aptl.core.opencode import OpenRouterRoute
from aptl.utils.curl_safe import curl_json
from aptl.utils.probe_execution import (
    ProbeProcessRunner,
    note_probe_cessation,
    probe_output_byte_limit,
)


def openrouter_access_ready(
    model: str,
    route: OpenRouterRoute,
    environment: Mapping[str, str],
    output_tokens: int,
) -> bool:
    """Observe authentication, account-scoped model access, and selected capacity.

    Never invoke inference, use ambient credentials, follow returned links, or
    change the selected route. Every response is bounded by the probe runner.
    """
    try:
        return _observe_access(model, route, environment, output_tokens)
    except RuntimeError, OSError, ValueError:
        return False


def _observe_access(
    model: str,
    route: OpenRouterRoute,
    environment: Mapping[str, str],
    output_tokens: int,
) -> bool:
    """Read only the approved account, selected model and exact serving route."""
    key = environment.get("OPENROUTER_API_KEY")
    if (
        not key
        or probe_output_byte_limit() is None
        or not model.startswith("openrouter/")
    ):
        return False
    auth = "Bearer " + key
    account = curl_json(route.endpoint + "/key", auth_header=auth)
    selected = model.removeprefix("openrouter/")
    return (
        _account_ready(account)
        and _model_accessible(route.endpoint, auth, selected)
        and _endpoint_ready(route, auth, selected, output_tokens)
    )


def _account_ready(account: object) -> bool:
    """Require a usable inference key and positive finite effective quota."""
    data = account.get("data") if isinstance(account, dict) else None
    if not isinstance(data, dict) or type(data.get("is_free_tier")) is not bool:
        return False
    if data.get("is_provisioning_key") is True or data.get("is_management_key") is True:
        return False
    return _quota_available(data.get("limit_remaining"))


def _quota_available(remaining: object) -> bool:
    """Accept unlimited quota or a finite positive balance, rejecting booleans."""
    if remaining is None:
        return True
    try:
        value = Decimal(str(remaining))
        return not isinstance(remaining, bool) and value.is_finite() and value > 0
    except InvalidOperation:
        return False


def _model_accessible(endpoint: str, auth: str, selected: str) -> bool:
    """Search fixed bounded catalog pages without following returned links."""
    for offset in range(0, 640, 10):
        catalog = curl_json(
            endpoint + f"/models/user?limit=10&offset={offset}", auth_header=auth
        )
        models = catalog.get("data") if isinstance(catalog, dict) else None
        if not _valid_catalog(models):
            break
        if any(item["id"] == selected for item in models):
            return True
        if len(models) < 10:
            break
    return False


def _valid_catalog(models: object) -> bool:
    """Require one bounded page of explicit model identifiers."""
    return (
        isinstance(models, list)
        and len(models) <= 10
        and all(
            isinstance(item, dict) and isinstance(item.get("id"), str)
            for item in models
        )
    )


def _endpoint_ready(
    route: OpenRouterRoute, auth: str, selected: str, output_tokens: int
) -> bool:
    """Observe capacity at the exact selected serving provider."""
    response = curl_json(
        route.endpoint + "/models/" + quote(selected, safe="/") + "/endpoints",
        auth_header=auth,
    )
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or data.get("id") != selected:
        return False
    endpoints = data.get("endpoints")
    return isinstance(endpoints, list) and any(
        _has_capacity(endpoint, route.serving_provider, output_tokens)
        for endpoint in endpoints
    )


def _has_capacity(endpoint: object, provider: str, output_tokens: int) -> bool:
    """Require an available exact route with sufficient completion capacity."""
    return (
        isinstance(endpoint, dict)
        and endpoint.get("tag") == provider
        and type(endpoint.get("status")) is int
        and endpoint["status"] == 0
        and type(endpoint.get("max_completion_tokens")) is int
        and endpoint["max_completion_tokens"] >= output_tokens
    )


def probe_opencode_version(
    runner: ProbeProcessRunner,
    executable: Path,
    work_root: Path,
    expected_version: str,
    timeout_seconds: float,
) -> bool:
    """Read only the selected executable's version in an empty private context."""
    with TemporaryDirectory(
        prefix="participant-readiness-", dir=work_root
    ) as temporary:
        try:
            result = runner.run(
                (str(executable), "--version"),
                env={
                    "PATH": os.defpath,
                    "HOME": temporary,
                    "OPENCODE_DISABLE_AUTOUPDATE": "true",
                    "OPENCODE_DISABLE_MODELS_FETCH": "true",
                },
                cwd=Path(temporary),
                stdin=b"",
                timeout_seconds=timeout_seconds,
                max_output_bytes=4096,
            )
        except Exception as exc:
            cleanup = getattr(exc, "cleanup", None)
            note_probe_cessation(cleanup is not None and not cleanup.residual)
            return False
    note_probe_cessation(result.cleanup is not None and not result.cleanup.residual)
    return (
        result.returncode == 0
        and result.cleanup is not None
        and not result.cleanup.residual
        and len(result.stdout) + len(result.stderr) <= 4096
        and result.stdout.decode("utf-8", errors="strict").strip() == expected_version
    )
