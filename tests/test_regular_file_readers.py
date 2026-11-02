"""#1618: the no-follow regular-file readers refuse a FIFO without blocking.

Each reader promises a bounded read of one regular file. A FIFO without a
writer blocked their open, so each case plants a FIFO where the reader looks
and requires a refusal at once.
"""

from __future__ import annotations

import hashlib
import io
import os
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from aptl.appliance.download import ApplianceDownloadError, stage_https_artifact
from aptl.appliance.seat import access, access_state, image_trust, overlay_identity
from aptl.appliance.seat.errors import SeatLauncherError
from aptl.appliance.seat.image_disk_cache import SeatImageError
from aptl.appliance.seat.overlay_identity import ApplianceBootstrapError
from aptl.appliance.seat.persistence import load_seat_record, seat_state_path
from aptl.utils.deterministic_archive import hash_file_nofollow, open_nofollow
from aptl.workbench.profiles import WorkbenchConfigurationError

pytestmark = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs")

_PAYLOAD = b"qualified-appliance-bytes"
_DIGEST = f"sha256:{hashlib.sha256(_PAYLOAD).hexdigest()}"


def _fifo(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(path)
    path.chmod(0o600)
    return path


def _stage(cache_dir: Path, open_request: Callable[[object], object]) -> object:
    return stage_https_artifact(
        url="https://example.test/disk.qcow2",
        cache_dir=cache_dir,
        filename="disk.qcow2",
        sha256=_DIGEST,
        size_bytes=len(_PAYLOAD),
        open_request=open_request,
    )


def _unexpected_request(_request: object) -> object:
    raise AssertionError("the cached artifact needs no request")


def _cached_artifact(tmp_path: Path) -> tuple[Path, Callable[[], object]]:
    fifo = _fifo(tmp_path / _DIGEST.removeprefix("sha256:") / "disk.qcow2")
    return fifo, lambda: _stage(tmp_path, _unexpected_request)


class _PartialResponse(io.BytesIO):
    """The answer to the resumed request of the last bytes of the artifact."""

    status = 206
    headers = {
        "Content-Length": str(len(_PAYLOAD) - 9),
        "Content-Range": f"bytes 9-{len(_PAYLOAD) - 1}/{len(_PAYLOAD)}",
    }

    def geturl(self) -> str:
        return "https://objects.example.test/artifact"


def _resumed_partial(tmp_path: Path) -> tuple[Path, Callable[[], object]]:
    """A FIFO replaces the partial file after its check, before its open."""

    partial = tmp_path / _DIGEST.removeprefix("sha256:") / ".disk.qcow2.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(_PAYLOAD[:9])

    def swap_then_answer(_request: object) -> object:
        partial.unlink()
        _fifo(partial)
        return _PartialResponse(_PAYLOAD[9:])

    return partial, lambda: _stage(tmp_path, swap_then_answer)


_CASES: dict[
    str, tuple[Callable[[Path], tuple[Path, Callable[[], object]]], type[BaseException]]
] = {
    "open_nofollow": (
        lambda tmp: (f := _fifo(tmp / "f"), lambda: open_nofollow(f)),
        OSError,
    ),
    "hash_file_nofollow": (
        lambda tmp: (f := _fifo(tmp / "f"), lambda: hash_file_nofollow(f)),
        OSError,
    ),
    "transport identity": (
        lambda tmp: (
            f := _fifo(tmp / "identity"),
            lambda: access._read_private_regular(f),
        ),
        OSError,
    ),
    "guest access request": (
        lambda tmp: (
            f := _fifo(tmp / "access-request"),
            lambda: access.read_guest_access_request(f),
        ),
        WorkbenchConfigurationError,
    ),
    "access record": (
        lambda tmp: (
            f := _fifo(tmp / "access.json"),
            lambda: access_state._read_access_record(f),
        ),
        OSError,
    ),
    "seat trust file": (
        lambda tmp: (
            f := _fifo(tmp / "trust.pub"),
            lambda: image_trust._read_regular(f),
        ),
        SeatImageError,
    ),
    "overlay identity": (
        lambda tmp: (
            f := _fifo(tmp / "identity.json"),
            lambda: overlay_identity._read_existing(f),
        ),
        ApplianceBootstrapError,
    ),
    "seat record": (
        lambda tmp: (_fifo(seat_state_path(tmp)), lambda: load_seat_record(tmp)),
        SeatLauncherError,
    ),
    "cached artifact": (_cached_artifact, ApplianceDownloadError),
    "resumed partial artifact": (_resumed_partial, ApplianceDownloadError),
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_each_regular_file_reader_refuses_a_fifo_without_blocking(
    tmp_path: Path, case: str
) -> None:
    setup, expected = _CASES[case]
    fifo, call = setup(tmp_path)
    raised: list[BaseException] = []

    def attempt() -> None:
        try:
            call()
        except expected as exc:
            raised.append(exc)

    reader = threading.Thread(target=attempt, daemon=True)
    reader.start()
    reader.join(timeout=10)
    blocked = reader.is_alive()
    if blocked:
        # Opening the FIFO for reading and writing releases a blocked open of
        # either side, so that the thread ends.
        release = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        reader.join(timeout=10)
        os.close(release)
    assert not blocked, f"the {case} reader blocked on a FIFO"
    assert len(raised) == 1, f"the {case} reader did not refuse the FIFO"


def test_open_nofollow_returns_a_blocking_handle(tmp_path: Path) -> None:
    (tmp_path / "f").write_bytes(b"x")
    with open_nofollow(tmp_path / "f") as handle:
        assert os.get_blocking(handle.fileno())
        assert handle.read() == b"x"
