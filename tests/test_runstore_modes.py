"""Owner-only modes on every ``LocalRunStore`` write path (#1329).

ADR-033 "Security layers": run captures are readable only by the owning
user, directories ``0700`` and files ``0600``. These tests drive each write
path under a group/world-readable umask and walk every entry the store
created, starting at a missing ancestor of the store root.
"""

import json
import os
import stat
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from aptl.core.runstore import LocalRunStore

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="run store modes are POSIX permission bits"
)

RUN_ID = "r1"
SOURCE_BYTES = b"copied artifact bytes\n"


@pytest.fixture(params=[0o022, 0o002, 0o000], ids=["umask022", "umask002", "umask000"])
def umask(request: pytest.FixtureRequest) -> Iterator[int]:
    previous = os.umask(request.param)
    try:
        yield request.param
    finally:
        os.umask(previous)


@pytest.fixture
def umask_022() -> Iterator[None]:
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _shared_source(tmp_path: Path) -> Path:
    """A ``0644`` file outside the store, as a collector artifact would be."""
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    source = source_dir / "artifact.bin"
    source.write_bytes(SOURCE_BYTES)
    source.chmod(0o644)
    return source


def _hold_lock(store: LocalRunStore, _source: Path) -> None:
    with store.finalization_lock(RUN_ID):
        pass


#: Every ``LocalRunStore`` write path. Each takes the store and a ``0644``
#: source file outside the store.
WRITE_PATHS: dict[str, Callable[[LocalRunStore, Path], object]] = {
    "create_run": lambda store, _src: store.create_run(RUN_ID),
    "write_file": lambda store, _src: store.write_file(RUN_ID, "a/b/blob.bin", b"x"),
    "write_json": lambda store, _src: store.write_json(RUN_ID, "a/data.json", {"n": 1}),
    "write_jsonl": lambda store, _src: store.write_jsonl(RUN_ID, "a/rows.jsonl", [{"n": 1}]),
    "append_jsonl": lambda store, _src: store.append_jsonl(
        RUN_ID, "a/events.jsonl", [{"n": 1}]
    ),
    "copy_file": lambda store, src: store.copy_file(RUN_ID, "a/artifact.bin", src),
    "create_run_json_once": lambda store, _src: store.create_run_json_once(
        RUN_ID, "a/b/once.json", {"n": 1}
    ),
    "commit_seal_marker": lambda store, _src: store.commit_seal_marker(
        RUN_ID, {"sealed": True}
    ),
    "create_json_once": lambda store, _src: store.create_json_once(
        "plans", "trial", {"n": 1}
    ),
    "finalization_lock": _hold_lock,
}

#: The writers whose target lives in ``<base_dir>/<run_id>/``.
RUN_WRITERS = [
    name for name in WRITE_PATHS if name not in {"create_json_once", "finalization_lock"}
]


@pytest.mark.parametrize("path_name", list(WRITE_PATHS))
def test_write_path_creates_owner_only_entries(
    tmp_path: Path, umask: int, path_name: str
) -> None:
    source = _shared_source(tmp_path)
    state = tmp_path / "state"
    store = LocalRunStore(state / "runs")

    WRITE_PATHS[path_name](store, source)

    entries = [state, *state.rglob("*")]
    assert len(entries) > 2, entries
    wrong = {
        str(entry.relative_to(tmp_path)): oct(_mode(entry))
        for entry in entries
        if _mode(entry) != (0o700 if entry.is_dir() else 0o600)
    }
    assert wrong == {}, f"umask {umask:03o}"
    assert _mode(source) == 0o644


def test_copy_file_keeps_bytes_and_timestamps_not_source_mode(
    tmp_path: Path, umask_022: None
) -> None:
    source = _shared_source(tmp_path)
    atime_ns, mtime_ns = 1_600_000_000_123_456_789, 1_650_000_000_987_654_321
    os.utime(source, ns=(atime_ns, mtime_ns))
    store = LocalRunStore(tmp_path / "runs")

    store.copy_file(RUN_ID, "artifact.bin", source)

    target = tmp_path / "runs" / RUN_ID / "artifact.bin"
    target_status = os.stat(target)
    assert target.read_bytes() == SOURCE_BYTES
    assert _mode(target) == 0o600
    assert _mode(source) == 0o644
    # Tolerate filesystems with coarser than nanosecond timestamps.
    assert abs(target_status.st_mtime_ns - mtime_ns) < 1_000_000_000
    assert target_status.st_mtime_ns == os.stat(source).st_mtime_ns
    assert abs(target_status.st_atime_ns - os.stat(source).st_atime_ns) < 1_000_000_000


def test_copy_file_onto_its_own_source_keeps_the_bytes(
    tmp_path: Path, umask_022: None
) -> None:
    store = LocalRunStore(tmp_path / "runs")
    store.write_file(RUN_ID, "artifact.bin", SOURCE_BYTES)
    target = tmp_path / "runs" / RUN_ID / "artifact.bin"

    with pytest.raises(OSError, match="same file"):
        store.copy_file(RUN_ID, "artifact.bin", target)

    assert target.read_bytes() == SOURCE_BYTES


def test_append_jsonl_new_file_is_private_and_existing_file_is_tightened(
    tmp_path: Path, umask_022: None
) -> None:
    store = LocalRunStore(tmp_path / "runs")
    store.append_jsonl(RUN_ID, "new.jsonl", [{"n": 1}])
    new_file = tmp_path / "runs" / RUN_ID / "new.jsonl"
    assert _mode(new_file) == 0o600

    legacy = tmp_path / "runs" / RUN_ID / "legacy.jsonl"
    legacy.write_text('{"n":0}\n', encoding="utf-8")
    legacy.chmod(0o644)

    store.append_jsonl(RUN_ID, "legacy.jsonl", [{"n": 1}])

    lines = legacy.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"n": 0}, {"n": 1}]
    assert _mode(legacy) == 0o600


def _legacy_store(tmp_path: Path, *existing: str) -> Path:
    """A pre-existing ``0755`` store root holding ``0755`` directories."""
    base = tmp_path / "runs"
    for directory in (base, *(base / name for name in existing)):
        directory.mkdir()
        directory.chmod(0o755)
    return base


@pytest.mark.parametrize("path_name", RUN_WRITERS)
def test_write_tightens_existing_run_directory(
    tmp_path: Path, umask_022: None, path_name: str
) -> None:
    source = _shared_source(tmp_path)
    base = _legacy_store(tmp_path, RUN_ID)

    WRITE_PATHS[path_name](LocalRunStore(base), source)

    assert _mode(base / RUN_ID) == 0o700
    assert _mode(base) == 0o755


@pytest.mark.parametrize(
    ("path_name", "directory"),
    [("create_json_once", "plans"), ("finalization_lock", "locks")],
)
def test_write_tightens_existing_store_directory(
    tmp_path: Path, umask_022: None, path_name: str, directory: str
) -> None:
    source = _shared_source(tmp_path)
    base = _legacy_store(tmp_path, directory)

    WRITE_PATHS[path_name](LocalRunStore(base), source)

    assert _mode(base / directory) == 0o700
    assert _mode(base) == 0o755


@pytest.mark.parametrize(
    ("path_name", "relative_path"),
    [
        ("write_file", "a/b/blob.bin"),
        ("append_jsonl", "a/events.jsonl"),
        ("copy_file", "a/artifact.bin"),
    ],
)
def test_foreign_owned_entries_are_left_unchanged(
    tmp_path: Path,
    umask_022: None,
    monkeypatch: pytest.MonkeyPatch,
    path_name: str,
    relative_path: str,
) -> None:
    source = _shared_source(tmp_path)
    base = _legacy_store(tmp_path, RUN_ID)
    existing = base / RUN_ID / relative_path
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"")
    existing.chmod(0o644)
    real_euid = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: real_euid + 1)

    WRITE_PATHS[path_name](LocalRunStore(base), source)

    assert existing.read_bytes() != b""
    assert _mode(base / RUN_ID) == 0o755
    assert _mode(existing) == 0o644


def test_symlinked_run_directory_is_not_re_moded_through_the_link(
    tmp_path: Path, umask_022: None
) -> None:
    base = _legacy_store(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    elsewhere.chmod(0o755)
    (base / RUN_ID).symlink_to(elsewhere, target_is_directory=True)

    LocalRunStore(base).create_run(RUN_ID)

    assert _mode(elsewhere) == 0o755


def test_run_path_occupied_by_a_file_still_raises(
    tmp_path: Path, umask_022: None
) -> None:
    base = _legacy_store(tmp_path)
    (base / RUN_ID).write_bytes(b"")

    with pytest.raises(FileExistsError):
        LocalRunStore(base).create_run(RUN_ID)
