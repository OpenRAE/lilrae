"""Authenticated public artifact staging tests."""

from __future__ import annotations

import hashlib
import io
import urllib.request
import urllib.response
from email.message import Message
from pathlib import Path

import pytest

from aptl.appliance import download
from aptl.appliance.download import (
    ApplianceAuthenticationRequired,
    ApplianceDownloadError,
    fetch_https_metadata,
    stage_https_artifact,
)


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, *, status: int, headers: dict[str, str]):
        super().__init__(payload)
        self.status = status
        self.headers = headers

    def geturl(self) -> str:
        return "https://objects.example.test/artifact"


def test_download_resumes_and_publishes_content_addressed_bytes(tmp_path: Path) -> None:
    payload = b"qualified-appliance-bytes"
    digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    digest_dir = tmp_path / digest.removeprefix("sha256:")
    digest_dir.mkdir(parents=True)
    partial = digest_dir / ".disk.qcow2.partial"
    partial.write_bytes(payload[:9])
    requests = []

    def open_request(request):
        requests.append(request)
        remaining = payload[9:]
        return _Response(
            remaining,
            status=206,
            headers={
                "Content-Length": str(len(remaining)),
                "Content-Range": f"bytes 9-{len(payload) - 1}/{len(payload)}",
            },
        )

    staged = stage_https_artifact(
        url="https://example.test/disk.qcow2",
        cache_dir=tmp_path,
        filename="disk.qcow2",
        sha256=digest,
        size_bytes=len(payload),
        open_request=open_request,
    )

    assert staged.path.read_bytes() == payload
    assert staged.reused is False
    assert requests[0].headers["Range"] == "bytes=9-"
    assert staged.path.stat().st_mode & 0o777 == 0o444


def test_download_rejects_wrong_digest_and_keeps_partial(tmp_path: Path) -> None:
    payload = b"wrong"
    digest = "sha256:" + "a" * 64

    with pytest.raises(ApplianceDownloadError, match="identity"):
        stage_https_artifact(
            url="https://example.test/disk.qcow2",
            cache_dir=tmp_path,
            filename="disk.qcow2",
            sha256=digest,
            size_bytes=len(payload),
            open_request=lambda _request: _Response(
                payload,
                status=200,
                headers={"Content-Length": str(len(payload))},
            ),
        )

    assert not (tmp_path / ("a" * 64) / "disk.qcow2").exists()
    assert (tmp_path / ("a" * 64) / ".disk.qcow2.partial").exists()


def test_download_rejects_non_https_source(tmp_path: Path) -> None:
    with pytest.raises(ApplianceDownloadError, match="invalid"):
        stage_https_artifact(
            url="http://example.test/disk.qcow2",
            cache_dir=tmp_path,
            filename="disk.qcow2",
            sha256="sha256:" + "a" * 64,
            size_bytes=1,
        )


def test_metadata_fetch_is_bounded_and_requires_exact_length() -> None:
    payload = b'{"signed":"later"}'

    fetched = fetch_https_metadata(
        "https://github.example.test/release/index.json",
        max_bytes=1024,
        open_request=lambda _request: _Response(
            payload,
            status=200,
            headers={"Content-Length": str(len(payload))},
        ),
    )

    assert fetched == payload


def test_metadata_fetch_rejects_oversized_declaration() -> None:
    with pytest.raises(ApplianceDownloadError, match="response is invalid"):
        fetch_https_metadata(
            "https://github.example.test/release/index.json",
            max_bytes=8,
            open_request=lambda _request: _Response(
                b"too-large",
                status=200,
                headers={"Content-Length": "9"},
            ),
        )


INDEX_URL = "https://github.example.test/release/index.json"
REGISTRY_PING = "https://registry.example.test/v2/"
CHALLENGE = 'Bearer realm="https://auth.example.test/token",service="registry"'


class _Origin(urllib.request.BaseHandler):
    """Answer HTTPS requests from a table, ahead of the network handler."""

    handler_order = 100

    def __init__(self, answers: dict[str, tuple[int, list[tuple[str, str]]]]):
        self.answers = answers

    def https_open(self, request: urllib.request.Request):
        status, headers = self.answers[request.full_url]
        message = Message()
        for name, value in headers:
            message[name] = value
        response = urllib.response.addinfourl(
            io.BytesIO(b""), message, request.full_url, status
        )
        response.msg = "answer"
        return response


def _through_urllib(answers: dict[str, tuple[int, list[tuple[str, str]]]]):
    """Open requests with urllib's real error and bounded redirect handling."""

    opener = urllib.request.build_opener(
        download._BoundedRedirectHandler(), _Origin(answers)
    )
    return lambda request: opener.open(request, timeout=5)


def test_metadata_401_hands_every_challenge_to_the_caller() -> None:
    second = 'Basic realm="registry"'
    open_request = _through_urllib(
        {
            REGISTRY_PING: (
                401,
                [("WWW-Authenticate", CHALLENGE), ("WWW-Authenticate", second)],
            )
        }
    )

    with pytest.raises(ApplianceAuthenticationRequired) as raised:
        fetch_https_metadata(REGISTRY_PING, max_bytes=1024, open_request=open_request)

    assert raised.value.challenges == (CHALLENGE, second)


@pytest.mark.parametrize(
    "answers",
    [
        pytest.param({REGISTRY_PING: (401, [])}, id="401-without-challenge"),
        pytest.param(
            {REGISTRY_PING: (404, [("WWW-Authenticate", CHALLENGE)])},
            id="challenge-on-404",
        ),
        pytest.param(
            {
                REGISTRY_PING: (302, [("Location", "https://other.example.test/v2/")]),
                "https://other.example.test/v2/": (
                    401,
                    [("WWW-Authenticate", CHALLENGE)],
                ),
            },
            id="challenge-from-redirect-target",
        ),
        pytest.param(
            {REGISTRY_PING: (302, [("Location", "http://registry.example.test/v2/")])},
            id="cleartext-redirect",
        ),
    ],
)
def test_metadata_failure_without_a_challenge_for_the_url_stays_generic(
    answers,
) -> None:
    open_request = _through_urllib(answers)

    with pytest.raises(ApplianceDownloadError, match="download failed") as raised:
        fetch_https_metadata(REGISTRY_PING, max_bytes=1024, open_request=open_request)

    assert not isinstance(raised.value, ApplianceAuthenticationRequired)


def test_unframed_metadata_is_admitted_only_when_asked_and_stays_bounded() -> None:
    payload = b'{"token":"chunked"}'

    def unframed(body: bytes):
        return lambda _request: _Response(body, status=200, headers={})

    chunked = unframed(payload)

    with pytest.raises(ApplianceDownloadError, match="response is invalid"):
        fetch_https_metadata(INDEX_URL, max_bytes=1024, open_request=chunked)
    fetched = fetch_https_metadata(
        INDEX_URL, max_bytes=1024, open_request=chunked, require_length=False
    )
    assert fetched == payload
    for body in (b"x" * 1025, b""):
        open_request = unframed(body)
        with pytest.raises(ApplianceDownloadError, match="length did not match"):
            fetch_https_metadata(
                INDEX_URL,
                max_bytes=1024,
                open_request=open_request,
                require_length=False,
            )


def test_unframed_admission_still_checks_a_declared_length() -> None:
    with pytest.raises(ApplianceDownloadError, match="length did not match"):
        fetch_https_metadata(
            INDEX_URL,
            max_bytes=1024,
            open_request=lambda _request: _Response(
                b"short", status=200, headers={"Content-Length": "9"}
            ),
            require_length=False,
        )
