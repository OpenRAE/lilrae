"""Anonymous pull tokens from the token service a seat image registry names.

A registry answers an unauthenticated request with ``401`` and a
``WWW-Authenticate: Bearer realm="…",service="…"`` challenge; the realm is
its token service.  The service is not always on the registry's own host
(Docker Hub's is ``auth.docker.io``), nor at one path (``/token`` on ghcr.io,
``/v2/auth`` on quay.io), so the token request follows the challenge.

The network fetch is passed in by the caller, so this module adds no seam of
its own: requests go through the same bounded HTTPS metadata fetch as every
other registry request.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable

from aptl.appliance.download import (
    ApplianceAuthenticationRequired,
    ApplianceDownloadError,
)
from aptl.appliance.seat.image_disk_cache import SeatImageError

MetadataFetch = Callable[..., bytes]

# RFC 9110 challenge syntax, enough to read one Bearer challenge's parameters.
_HTTP_TOKEN = r"[\w!#$%&'*+.^`|~-]+"
_BEARER_SCHEME = re.compile(r"Bearer[ \t]+", re.IGNORECASE)
_AUTH_PARAM_NAME = re.compile(rf"({_HTTP_TOKEN})[ \t]*=[ \t]*", re.ASCII)
_AUTH_PARAM_VALUE = re.compile(rf'({_HTTP_TOKEN})|"((?:[^"\\]|\\.)*)"', re.ASCII)
_AUTH_PARAM_END = re.compile(r"[ \t]*(?:,[ \t]*|\Z)")
_QUOTED_PAIR = re.compile(r"\\(.)")


def _auth_param(challenge: str, position: int) -> tuple[str, str, int] | None:
    """Read one ``name=value`` auth-param, returning it and where the next starts."""

    name = _AUTH_PARAM_NAME.match(challenge, position)
    value = _AUTH_PARAM_VALUE.match(challenge, name.end()) if name else None
    end = _AUTH_PARAM_END.match(challenge, value.end()) if value else None
    if name is None or value is None or end is None:
        return None
    token, quoted = value.groups()
    text = token if quoted is None else _QUOTED_PAIR.sub(r"\1", quoted)
    return name.group(1).lower(), text, end.end()


def bearer_parameters(challenge: str) -> dict[str, str] | None:
    """Parse one ``Bearer`` challenge, or return ``None`` for anything else.

    A malformed list or a repeated parameter is refused rather than guessed.
    """

    scheme = _BEARER_SCHEME.match(challenge)
    if scheme is None:
        return None
    parameters: dict[str, str] = {}
    position = scheme.end()
    while position < len(challenge):
        param = _auth_param(challenge, position)
        if param is None or param[0] in parameters:
            return None
        name, value, position = param
        parameters[name] = value
    return parameters


def bearer_challenge(
    registry: str, fetch: MetadataFetch, *, max_bytes: int
) -> dict[str, str] | None:
    """Return the one Bearer challenge an unauthenticated request receives.

    ``None`` means the registry sent no usable challenge: it answered without
    asking for a token, or its answer named no single Bearer scheme.
    """

    try:
        fetch(f"https://{registry}/v2/", max_bytes=max_bytes)
    except ApplianceAuthenticationRequired as exc:
        bearers = [
            parameters
            for parameters in map(bearer_parameters, exc.challenges)
            if parameters is not None
        ]
        return bearers[0] if len(bearers) == 1 else None
    except ApplianceDownloadError:
        return None
    return None


def _issued_token(url: str, fetch: MetadataFetch, *, max_bytes: int) -> str | None:
    """Request one token document and return the token it carries, if any."""

    try:
        # Token services may reply chunked; the read stays size-bounded.
        document = json.loads(fetch(url, max_bytes=max_bytes, require_length=False))
    except (ApplianceDownloadError, ValueError):
        return None
    token = (
        document.get("token") or document.get("access_token")
        if isinstance(document, dict)
        else None
    )
    return token if isinstance(token, str) and token else None


def anonymous_token(
    registry: str, repository: str, fetch: MetadataFetch, *, max_bytes: int
) -> str | None:
    """Obtain a pull token from the token service the registry advertises.

    The token comes from the challenge's ``realm``, for its ``service`` and
    the repository pull scope.  A registry that sends no challenge needs no
    token, so the pull proceeds without one.  A realm that is not HTTPS is
    refused before any request is sent to it.
    """

    challenge = bearer_challenge(registry, fetch, max_bytes=max_bytes) or {}
    realm = challenge.get("realm")
    if not realm:
        return None
    if not realm.lower().startswith("https://"):
        raise SeatImageError(
            f"seat image registry {registry} advertises a token service "
            "that is not HTTPS"
        )
    query = {"scope": f"repository:{repository}:pull"}
    if challenge.get("service"):
        query = {"service": challenge["service"], **query}
    separator = "&" if "?" in realm else "?"
    url = f"{realm}{separator}{urllib.parse.urlencode(query)}"
    return _issued_token(url, fetch, max_bytes=max_bytes)
