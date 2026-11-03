"""Read-only access checks against the managed executor's exact approved route."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from aptl.core.opencode import OpenRouterRoute
from aptl.utils.curl_safe import curl_json
from aptl.utils.probe_execution import probe_output_byte_limit


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
    key = environment.get("OPENROUTER_API_KEY")
    if (
        not key
        or probe_output_byte_limit() is None
        or not model.startswith("openrouter/")
    ):
        return False
    auth = "Bearer " + key
    account = curl_json(route.endpoint + "/key", auth_header=auth)
    data = account.get("data") if isinstance(account, dict) else None
    if not isinstance(data, dict) or type(data.get("is_free_tier")) is not bool:
        return False
    if data.get("is_provisioning_key") is True or data.get("is_management_key") is True:
        return False
    remaining = data.get("limit_remaining")
    try:
        if remaining is not None and (
            isinstance(remaining, bool)
            or not Decimal(str(remaining)).is_finite()
            or Decimal(str(remaining)) <= 0
        ):
            return False
    except InvalidOperation:
        return False
    selected = model.removeprefix("openrouter/")
    # Pagination is fixed and bounded, independent of server-supplied links.
    found = False
    for offset in range(0, 640, 10):
        catalog = curl_json(
            route.endpoint + f"/models/user?limit=10&offset={offset}", auth_header=auth
        )
        models = catalog.get("data") if isinstance(catalog, dict) else None
        if not isinstance(models, list) or len(models) > 10:
            return False
        if any(
            not isinstance(item, dict) or not isinstance(item.get("id"), str)
            for item in models
        ):
            return False
        if any(item["id"] == selected for item in models):
            found = True
            break
        if len(models) < 10:
            return False
    if not found:
        return False
    response = curl_json(
        route.endpoint + "/models/" + quote(selected, safe="/") + "/endpoints",
        auth_header=auth,
    )
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or data.get("id") != selected:
        return False
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list):
        return False
    return any(
        isinstance(endpoint, dict)
        and endpoint.get("tag") == route.serving_provider
        and type(endpoint.get("status")) is int
        and endpoint["status"] == 0
        and type(endpoint.get("max_completion_tokens")) is int
        and endpoint["max_completion_tokens"] >= output_tokens
        for endpoint in endpoints
    )
