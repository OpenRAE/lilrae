"""Seat VM disk resolution from an OCI registry reference."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path

import pytest

from aptl.appliance.download import (
    ApplianceAuthenticationRequired,
    ApplianceDownloadError,
    StagedDownload,
)
from aptl.appliance.seat import image as seat_image
from aptl.appliance.seat.image import (
    DISK_MEDIA_TYPE,
    SeatImageError,
    parse_seat_image_reference,
    resolve_seat_image,
)

DISK_BYTES = b"qcow2-disk-bytes"
DISK_DIGEST = "sha256:" + hashlib.sha256(DISK_BYTES).hexdigest()


def _manifest(layers: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "layers": layers,
        }
    ).encode()


def _disk_layer(size: int = len(DISK_BYTES)) -> dict[str, object]:
    return {"mediaType": DISK_MEDIA_TYPE, "digest": DISK_DIGEST, "size": size}


# ghcr.io's challenge as it answers ``GET https://ghcr.io/v2/``, scope included.
GHCR_CHALLENGE = (
    'Bearer realm="https://ghcr.io/token",service="ghcr.io",'
    'scope="repository:user/image:pull"'
)
PULL_SCOPE = "repository:owner/seat:pull"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch):
    """Serve canned registry documents behind a token challenge.

    Like a real registry, it answers a request that lacks the token with 401
    and its ``WWW-Authenticate`` challenge.  The token service answers only at
    its realm, for its own service name and the repository pull scope, and
    ``framed=False`` makes it reply without ``Content-Length`` (chunked), as
    Docker Hub's does.  No challenges is a registry that needs no token.
    """

    # Transport fixtures have passed signature admission, covered separately.
    monkeypatch.setattr("aptl.appliance.seat.image_trust.verify_remote_image", lambda *a: None)
    monkeypatch.setattr("aptl.appliance.seat.image_trust.publish_verified_image", lambda *a: None)
    state: dict[str, object] = {
        "documents": {},
        "requests": [],
        "staged": [],
        "challenges": (GHCR_CHALLENGE,),
        "token_service": {
            "realm": "https://ghcr.io/token",
            "service": "ghcr.io",
            "token": "pull-token",
            "framed": True,
        },
    }

    def authorized(headers: dict[str, str]) -> bool:
        service = state["token_service"]
        return not state["challenges"] or (
            service is not None
            and headers.get("Authorization") == f"Bearer {service['token']}"
        )

    def token_reply(url: str, require_length: bool) -> bytes | None:
        service = state["token_service"]
        if service is None or url.partition("?")[0] != service["realm"]:
            return None
        expected = {"service": [service["service"]], "scope": [PULL_SCOPE]}
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if query != expected or (require_length and not service["framed"]):
            raise ApplianceDownloadError("token request refused")
        return json.dumps({"token": service["token"]}).encode()

    def fake_metadata(
        url: str, *, max_bytes: int, headers=None, require_length: bool = True
    ) -> bytes:
        headers = dict(headers or {})
        state["requests"].append((url, headers))
        token = token_reply(url, require_length)
        if token is not None:
            return token
        if not authorized(headers):
            raise ApplianceAuthenticationRequired(state["challenges"])
        documents: dict[str, bytes] = state["documents"]  # type: ignore[assignment]
        for suffix, payload in documents.items():
            if url.endswith(suffix):
                return payload
        raise ApplianceDownloadError("not found")

    def fake_stage(*, url, cache_dir, filename, sha256, size_bytes, headers=None):
        state["staged"].append((url, sha256, size_bytes, dict(headers or {})))
        if not authorized(dict(headers or {})):
            raise ApplianceDownloadError("blob request was not authorized")
        path = Path(cache_dir) / sha256.removeprefix("sha256:") / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(DISK_BYTES)
        return StagedDownload(path, sha256, size_bytes, reused=False)

    monkeypatch.setattr(seat_image, "fetch_https_metadata", fake_metadata)
    monkeypatch.setattr(seat_image, "stage_https_artifact", fake_stage)
    return state


def _serve(registry, *, manifest: bytes, token: str | None = "pull-token") -> None:
    registry["documents"] = {"/manifests/latest": manifest}
    if token is None:
        registry["challenges"] = ()
        registry["token_service"] = None
    else:
        registry["token_service"]["token"] = token


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("ghcr.io/owner/seat:v1", "ghcr.io/owner/seat:v1"),
        ("ghcr.io/owner/seat", "ghcr.io/owner/seat:latest"),
        (f"ghcr.io/owner/seat@{DISK_DIGEST}", f"ghcr.io/owner/seat@{DISK_DIGEST}"),
        ("registry.example:5000/a/b/c:tag", "registry.example:5000/a/b/c:tag"),
    ],
)
def test_reference_parsing_round_trips(reference: str, expected: str) -> None:
    assert str(parse_seat_image_reference(reference)) == expected


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "   ",
        "seat:latest",
        "ghcr.io/Owner/seat",
        "ghcr.io/owner/seat@sha256:notadigest",
        "ghcr.io/owner/seat@SHA256:" + "a" * 64,
        "ghcr.io/owner/seat:bad tag",
        "ghcr.io/owner/seat:",
    ],
)
def test_ambiguous_references_are_refused(reference: str) -> None:
    # A reference selects what a seat boots, so it is refused rather than
    # normalized into something the operator did not write.
    with pytest.raises(SeatImageError):
        parse_seat_image_reference(reference)


def test_resolves_disk_layer_and_verifies_it_by_digest(registry, tmp_path) -> None:
    _serve(registry, manifest=_manifest([_disk_layer()]))

    staged = resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)

    assert staged.digest == DISK_DIGEST
    assert staged.path.read_bytes() == DISK_BYTES
    url, sha256, size, headers = registry["staged"][0]
    assert url.endswith(f"/v2/owner/seat/blobs/{DISK_DIGEST}")
    # The staging helper is what enforces the digest, so it must receive the
    # full sha256:<hex> form the manifest declared.
    assert sha256 == DISK_DIGEST
    assert size == len(DISK_BYTES)
    assert headers["Authorization"] == "Bearer pull-token"


def test_manifest_request_is_authenticated_and_accepts_oci_types(
    registry, tmp_path
) -> None:
    _serve(registry, manifest=_manifest([_disk_layer()]))

    resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)

    manifest_url, headers = next(
        entry for entry in registry["requests"] if "/manifests/" in entry[0]
    )
    assert manifest_url == "https://ghcr.io/v2/owner/seat/manifests/latest"
    assert headers["Authorization"] == "Bearer pull-token"
    assert "application/vnd.oci.image.manifest.v1+json" in headers["Accept"]


def test_registry_that_sends_no_challenge_is_pulled_without_a_token(
    registry, tmp_path
) -> None:
    # A registry that needs no token must not be treated as unreachable, and
    # no token service is guessed for it.
    _serve(registry, manifest=_manifest([_disk_layer()]), token=None)

    staged = resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)

    assert staged.digest == DISK_DIGEST
    _, _, _, headers = registry["staged"][0]
    assert "Authorization" not in headers
    requested = [url for url, _ in registry["requests"]]
    assert all(url.startswith("https://ghcr.io/v2/") for url in requested)
    assert all("Authorization" not in sent for _, sent in registry["requests"])


DOCKER_HUB_CHALLENGE = (
    'Bearer realm="https://auth.docker.io/token",service="registry.docker.io"'
)


@pytest.mark.parametrize(
    ("reference", "challenge", "realm", "service", "framed"),
    [
        pytest.param(
            "ghcr.io/owner/seat:latest",
            GHCR_CHALLENGE,
            "https://ghcr.io/token",
            "ghcr.io",
            True,
            id="ghcr-io",
        ),
        pytest.param(
            "quay.io/owner/seat:latest",
            'Bearer realm="https://quay.io/v2/auth",service="quay.io"',
            "https://quay.io/v2/auth",
            "quay.io",
            True,
            id="quay-io-v2-auth-path",
        ),
        pytest.param(
            "registry-1.docker.io/owner/seat:latest",
            DOCKER_HUB_CHALLENGE,
            "https://auth.docker.io/token",
            "registry.docker.io",
            False,
            id="docker-hub-own-token-host-service-and-chunked-reply",
        ),
        pytest.param(
            "gcr.io/owner/seat:latest",
            'bearer Realm="https://gcr.io/v2/token", Service=gcr.io',
            "https://gcr.io/v2/token",
            "gcr.io",
            True,
            id="gcr-io-unquoted-service-any-case",
        ),
    ],
)
def test_pull_token_comes_from_the_challenged_realm_and_service(
    registry, tmp_path, reference, challenge, realm, service, framed
) -> None:
    host = reference.partition("/")[0]
    registry["challenges"] = (challenge,)
    registry["token_service"] = {
        "realm": realm,
        "service": service,
        "token": "realm-token",
        "framed": framed,
    }
    registry["documents"] = {"/manifests/latest": _manifest([_disk_layer()])}

    staged = resolve_seat_image(reference, cache_dir=tmp_path)

    assert staged.digest == DISK_DIGEST
    first, second, manifest = registry["requests"][:3]
    # An unauthenticated request draws the challenge; the token request
    # carries no credential of its own.
    assert first == (f"https://{host}/v2/", {})
    assert second[0].partition("?")[0] == realm
    assert "Authorization" not in second[1]
    assert manifest[0] == f"https://{host}/v2/owner/seat/manifests/latest"
    assert manifest[1]["Authorization"] == "Bearer realm-token"
    assert registry["staged"][0][3]["Authorization"] == "Bearer realm-token"


@pytest.mark.parametrize(
    "challenges",
    [
        pytest.param(('Basic realm="registry"',), id="no-bearer-scheme"),
        pytest.param(('Bearer service="ghcr.io"',), id="no-realm"),
        pytest.param((GHCR_CHALLENGE, DOCKER_HUB_CHALLENGE), id="two-bearer-challenges"),
        pytest.param(
            ('Bearer realm="https://ghcr.io/token",realm="https://auth.example/t"',),
            id="repeated-realm",
        ),
        pytest.param(('Bearer realm="https://ghcr.io/token" service',), id="malformed"),
    ],
)
def test_unusable_challenge_requests_no_token(registry, tmp_path, challenges) -> None:
    # Guessing a token service for an unreadable challenge would send the
    # request somewhere the registry never named.
    _serve(registry, manifest=_manifest([_disk_layer()]))
    registry["challenges"] = challenges

    with pytest.raises(SeatImageError, match="manifest is unavailable"):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)

    requested = [url for url, _ in registry["requests"]]
    assert requested == [
        "https://ghcr.io/v2/",
        "https://ghcr.io/v2/owner/seat/manifests/latest",
    ]


def test_cleartext_token_realm_is_refused(registry, tmp_path) -> None:
    _serve(registry, manifest=_manifest([_disk_layer()]))
    registry["challenges"] = ('Bearer realm="http://ghcr.io/token",service="ghcr.io"',)
    registry["token_service"]["realm"] = "http://ghcr.io/token"

    with pytest.raises(SeatImageError, match="not HTTPS"):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)

    assert [url for url, _ in registry["requests"]] == ["https://ghcr.io/v2/"]


def test_quoted_pairs_in_a_challenge_are_unescaped() -> None:
    parameters = seat_image._bearer_parameters(
        'Bearer realm="https://auth.example/t\\"x",error="invalid_token"'
    )

    assert parameters == {"realm": 'https://auth.example/t"x', "error": "invalid_token"}


def test_ordinary_container_image_is_refused(registry, tmp_path) -> None:
    # An ordinary image would otherwise be booted as though it were a disk.
    _serve(
        registry,
        manifest=_manifest(
            [
                {
                    "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": DISK_DIGEST,
                    "size": 10,
                }
            ]
        ),
    )

    with pytest.raises(SeatImageError, match="not a seat VM disk"):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)


def test_multiple_disk_layers_are_refused(registry, tmp_path) -> None:
    _serve(registry, manifest=_manifest([_disk_layer(), _disk_layer()]))

    with pytest.raises(SeatImageError, match="more than one disk layer"):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)


@pytest.mark.parametrize(
    "layer",
    [
        {"mediaType": DISK_MEDIA_TYPE, "digest": "sha256:short", "size": 10},
        {"mediaType": DISK_MEDIA_TYPE, "digest": DISK_DIGEST, "size": 0},
        {"mediaType": DISK_MEDIA_TYPE, "digest": DISK_DIGEST, "size": -1},
        {"mediaType": DISK_MEDIA_TYPE, "digest": DISK_DIGEST},
        {"mediaType": DISK_MEDIA_TYPE, "size": 10},
    ],
)
def test_unusable_disk_descriptors_are_refused(registry, tmp_path, layer) -> None:
    _serve(registry, manifest=_manifest([layer]))

    with pytest.raises(SeatImageError):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)


def test_oversized_disk_declaration_is_refused(registry, tmp_path) -> None:
    _serve(registry, manifest=_manifest([_disk_layer(size=1 << 60)]))

    with pytest.raises(SeatImageError):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)


def test_missing_manifest_is_reported_against_the_reference(registry, tmp_path) -> None:
    registry["documents"] = {}

    with pytest.raises(SeatImageError, match="manifest is unavailable"):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)


def test_non_json_manifest_is_refused(registry, tmp_path) -> None:
    _serve(registry, manifest=b"<html>not a manifest</html>")

    with pytest.raises(SeatImageError, match="not valid JSON"):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)


def test_index_resolves_to_its_single_x86_64_manifest(registry, tmp_path) -> None:
    child = _manifest([_disk_layer()])
    child_digest = "sha256:" + hashlib.sha256(child).hexdigest()
    index = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {
                    "digest": child_digest,
                    "platform": {"architecture": "amd64", "os": "linux"},
                },
                {
                    "digest": "sha256:" + "b" * 64,
                    "platform": {"architecture": "arm64", "os": "linux"},
                },
            ],
        }
    ).encode()
    registry["documents"] = {
        "/manifests/latest": index,
        f"/manifests/{child_digest}": child,
    }

    staged = resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)

    assert staged.digest == DISK_DIGEST
    _, child_headers = registry["requests"][-1]
    assert child_headers["Authorization"] == "Bearer pull-token"


def test_ambiguous_index_is_refused(registry, tmp_path) -> None:
    index = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {"digest": "sha256:" + "a" * 64, "platform": {"architecture": "amd64"}},
                {"digest": "sha256:" + "b" * 64, "platform": {"architecture": "amd64"}},
            ],
        }
    ).encode()
    registry["documents"] = {"/manifests/latest": index}

    with pytest.raises(SeatImageError, match="exactly one x86_64 manifest"):
        resolve_seat_image("ghcr.io/owner/seat:latest", cache_dir=tmp_path)
