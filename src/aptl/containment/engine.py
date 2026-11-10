"""The pinned containment engine and the verified snapshot that workers import.

Verification and execution use the same bytes. ``prepare`` copies each engine
source file once into an owner-only snapshot under the state root, hashes the
exact bytes that it wrote, compares the hash with the pin, and then makes the
snapshot read-only. Workers import only that snapshot, without bytecode, so a
later change to the engine checkout or a planted cache file cannot reach them.
"""

import contextlib
import hashlib
import os
import secrets
import shutil
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from aptl.core.containment import EngineIdentity, ReasonCode
from aptl.utils.pathsafe import open_private_dir_contained_nofollow
from aptl.utils.strict_json import model_validate_json_strict

_PIN_RESOURCE = "engine_pin.json"
_SOURCE_TREE = "core"
_LICENSE = "LICENSE"
_SNAPSHOTS = "engine"
_CACHE_DIRECTORY = "__pycache__"
_SNAPSHOT_ENTRIES = frozenset({_SOURCE_TREE, _LICENSE})
_READ_ONLY_FILE = 0o400
_READ_ONLY_DIRECTORY = 0o500
_PRIVATE_DIRECTORY = 0o700
_PRIVATE_FILE = 0o600


class EnginePin(BaseModel):
    """The exact tested fork revision and the digest of its source tree."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["lilrae.containment.engine-pin/v1"]
    repository: str
    upstream: str
    commit: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    source_tree: Literal["core"]
    source_digest: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
    license_file: Literal["LICENSE"]


def load_engine_pin() -> EnginePin:
    """Read the pin that ships with this package."""
    payload = resources.files(__package__).joinpath(_PIN_RESOURCE).read_bytes()
    return model_validate_json_strict(EnginePin, payload)


def _regular_files(tree: Path, *, skip_caches: bool) -> list[tuple[str, Path]]:
    """Return the regular files under ``tree`` by relative path; refuse links."""
    files: list[tuple[str, Path]] = []
    for directory, subdirectories, names in os.walk(tree):
        if skip_caches:
            subdirectories[:] = [name for name in subdirectories if name != _CACHE_DIRECTORY]
        for name in [*subdirectories, *names]:
            path = Path(directory, name)
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"engine tree contains a symbolic link: {path}")
            if name not in names or (skip_caches and name.endswith(".pyc")):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError(f"engine tree contains a special file: {path}")
            files.append((path.relative_to(tree).as_posix(), path))
    return sorted(files)


def _read_nofollow(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read()


class _TreeDigest:
    """The pin's digest form: each relative path with the SHA-256 of its bytes."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()

    def add(self, relative: str, data: bytes) -> None:
        self._digest.update(relative.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())

    def value(self) -> str:
        return f"sha256:{self._digest.hexdigest()}"


def _tree_digest(tree: Path, *, skip_caches: bool) -> str:
    digest = _TreeDigest()
    for relative, path in _regular_files(tree, skip_caches=skip_caches):
        digest.add(relative, _read_nofollow(path))
    return digest.value()


def source_digest(root: Path) -> str:
    """Digest the engine source under ``root/core``; caches are not source."""
    return _tree_digest(root / _SOURCE_TREE, skip_caches=True)


def _write_private(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    with os.fdopen(os.open(path, flags, _PRIVATE_FILE), "wb") as stream:
        stream.write(data)


def _copy_source(source: Path, snapshot: Path) -> str:
    """Copy each source file once; digest exactly the bytes written."""
    digest = _TreeDigest()
    for relative, path in _regular_files(source / _SOURCE_TREE, skip_caches=True):
        data = _read_nofollow(path)
        target = snapshot / _SOURCE_TREE / relative
        target.parent.mkdir(mode=_PRIVATE_DIRECTORY, parents=True, exist_ok=True)
        _write_private(target, data)
        digest.add(relative, data)
    _write_private(snapshot / _LICENSE, _read_nofollow(source / _LICENSE))
    return digest.value()


def _walk_all(tree: Path) -> Iterator[Path]:
    yield tree
    yield from tree.rglob("*")


def _set_modes(tree: Path, *, read_only: bool) -> None:
    """Make every entry read-only, or owner-writable again before removal."""
    entries = list(_walk_all(tree))
    for path in sorted(entries, key=lambda item: len(item.parts), reverse=read_only):
        is_directory = stat.S_ISDIR(path.lstat().st_mode)
        if read_only:
            path.chmod(_READ_ONLY_DIRECTORY if is_directory else _READ_ONLY_FILE)
        else:
            path.chmod(_PRIVATE_DIRECTORY if is_directory else _PRIVATE_FILE)


def _remove(tree: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        _set_modes(tree, read_only=False)
        shutil.rmtree(tree)


@dataclass(frozen=True)
class EngineVerification:
    """The outcome; ``snapshot`` is the verified engine root, else None."""

    reason: ReasonCode | None
    detail: str | None = None
    snapshot: Path | None = None


class EngineInstallation:
    """An engine checkout and its pin."""

    def __init__(self, root: Path, pin: EnginePin) -> None:
        self.root = root
        self.pin = pin

    def identity(self, containment_tier: str | None = None) -> EngineIdentity:
        """Name the pinned engine in a report."""
        return EngineIdentity(
            repository=self.pin.repository,
            commit=self.pin.commit,
            source_digest=self.pin.source_digest,
            containment_tier=containment_tier,
        )

    def prepare(self, state_root: Path) -> EngineVerification:
        """Return a verified read-only snapshot under ``state_root``.

        An existing snapshot is verified again in full; a bytecode cache or an
        extra file in it refuses the engine.
        """
        parent = state_root / _SNAPSHOTS
        os.close(open_private_dir_contained_nofollow(state_root, Path(_SNAPSHOTS)))
        snapshot = parent / self.pin.source_digest.removeprefix("sha256:")
        if snapshot.is_symlink():
            return EngineVerification(ReasonCode.ENGINE_UNVERIFIED, "the engine snapshot is a link")
        if snapshot.exists():
            return self._existing(snapshot)
        if not (self.root / _SOURCE_TREE).is_dir() or not (self.root / _LICENSE).is_file():
            return EngineVerification(
                ReasonCode.ENGINE_UNAVAILABLE,
                "the engine source tree or its license file is absent",
            )
        staging = parent / f".staging-{secrets.token_hex(8)}"
        staging.mkdir(mode=_PRIVATE_DIRECTORY)
        try:
            return self._publish(staging, snapshot)
        finally:
            _remove(staging)

    def _publish(self, staging: Path, snapshot: Path) -> EngineVerification:
        try:
            observed = _copy_source(self.root, staging)
        except (OSError, ValueError) as exc:
            return EngineVerification(ReasonCode.ENGINE_UNVERIFIED, str(exc)[:512])
        if observed != self.pin.source_digest:
            return EngineVerification(
                ReasonCode.ENGINE_UNVERIFIED,
                f"engine source digest {observed} differs from the pin",
            )
        _set_modes(staging, read_only=True)
        try:
            staging.rename(snapshot)
        except OSError:
            # Another process published the same snapshot first.
            return self._existing(snapshot)
        return EngineVerification(None, snapshot=snapshot)

    def _existing(self, snapshot: Path) -> EngineVerification:
        try:
            entries = {path.name for path in snapshot.iterdir()}
            observed = _tree_digest(snapshot / _SOURCE_TREE, skip_caches=False)
        except (OSError, ValueError) as exc:
            return EngineVerification(ReasonCode.ENGINE_UNVERIFIED, str(exc)[:512])
        if entries != _SNAPSHOT_ENTRIES or observed != self.pin.source_digest:
            return EngineVerification(
                ReasonCode.ENGINE_UNVERIFIED,
                f"the engine snapshot {snapshot.name} differs from the pin",
            )
        return EngineVerification(None, snapshot=snapshot)
