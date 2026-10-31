"""Bounded, value-free readback and deadline supervision of recorded native IDs."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4
import re
import time
from typing import Protocol

from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.core.deployment.lilrae_docker_recording import (
    RecordedCreation,
    RecordingStore,
    _encode,
)
from aptl.utils.pathsafe import PathContainmentError, replace_private_nofollow
from aptl.core.lifecycle_policy import LifecycleBusyError


_OBSERVATION_KEYS = frozenset({"state", "platform", "image_id"})
_INSPECT_UNAVAILABLE = "child-inspect-unavailable"


class RecordedNative(Protocol):
    """Native reads and actions that recorded inventory uses."""

    def inspect(self, native_id: str) -> dict[str, object] | None:
        """Return the container inspection, or None when it is absent."""
        ...

    def stop(self, native_id: str) -> None:
        """Stop the container when it is present."""
        ...


@dataclass(frozen=True)
class RecordedChild:
    """One recorded creation and its last value-free native observation."""

    creation: RecordedCreation
    state: str = "active"
    platform: str = ""
    image_id: str = ""


@dataclass(frozen=True)
class RecordedInventorySnapshot:
    """Observed recorded children, completeness, and bounded diagnostics."""

    children: tuple[RecordedChild, ...] = ()
    complete: bool = True
    diagnostics: tuple[str, ...] = ()


class RecordedInventory:
    """Read back recorded native children and stop them at their deadlines."""

    def __init__(
        self,
        store: RecordingStore,
        native: RecordedNative,
        *,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Bind the recording store, the native reader, and the clocks."""
        self.store = store
        self.native = native
        self.wall_clock = wall_clock
        self.monotonic_clock = monotonic_clock
        self._deadlines: dict[str, float] = {}

    def _deadline(self, creation: RecordedCreation) -> float:
        """Return the monotonic deadline of a child, bounded by its parent."""
        if creation.native_id not in self._deadlines:
            remaining = max(
                0,
                min(
                    creation.timeout_seconds, creation.deadline_utc - self.wall_clock()
                ),
            )
            deadline = self.monotonic_clock() + remaining
            if creation.parent_native_id:
                parent = self.store.creation(creation.parent_native_id)
                deadline = min(deadline, self._deadline(parent))
            self._deadlines.setdefault(creation.native_id, deadline)
        return self._deadlines[creation.native_id]

    @staticmethod
    def _observation_path(native_id: str) -> Path:
        """Return the relative path of the retained observation of a child."""
        return Path("observations") / f"{native_id}.json"

    def _retained(self, creation: RecordedCreation) -> RecordedChild:
        """Return the retained observation of a child, or an active default."""
        raw = self.store._optional_read(self._observation_path(creation.native_id))
        if raw is None:
            return RecordedChild(creation)
        if set(raw) != _OBSERVATION_KEYS or raw["state"] not in {
            "active",
            "terminated",
            "autoremoved",
        }:
            raise OwnershipConflictError("recorded child observation is invalid")
        return RecordedChild(creation, **raw)

    @staticmethod
    def _require_identity(creation: RecordedCreation, info: dict[str, object]) -> None:
        """Make sure that the inspection describes the recorded child."""
        if info.get("Id") != creation.native_id or not isinstance(
            info.get("State"), dict
        ):
            raise OwnershipConflictError(
                "recorded child native identity is unavailable"
            )

    @classmethod
    def _inspected(
        cls, creation: RecordedCreation, info: dict[str, object]
    ) -> RecordedChild:
        """Make a value-free child observation from a native inspection."""
        cls._require_identity(creation, info)
        state = (
            "terminated"
            if info["State"].get("Status") in {"exited", "dead"}
            else "active"
        )
        platform = (
            info.get("Platform") if info.get("Platform") in {"linux", "windows"} else ""
        )
        image_id = info.get("Image", "")
        if not isinstance(image_id, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", image_id, re.ASCII
        ):
            image_id = ""
        return RecordedChild(creation, state, platform, image_id)

    def _publish_readback(
        self, creation: RecordedCreation, payload: dict[str, str]
    ) -> None:
        """Append one readback record for a changed or first observation."""
        self.store._publish(
            Path("readbacks") / f"{uuid4().hex}.json",
            {
                "schema": "lilrae.native-readback/v1",
                "native_id": creation.native_id,
                "attempt_id": creation.attempt_id,
                "daemon_id": creation.daemon_id,
                "creation_digest": creation.evidence_digest,
                "recorded_utc": self.wall_clock(),
                "observation": payload,
            },
        )

    def capture(self, creation: RecordedCreation) -> RecordedChild:
        """Inspect one recorded child and retain its value-free observation."""
        self.store.verify(creation.receipt())
        self._deadline(creation)
        previous = self._retained(creation)
        info = self.native.inspect(creation.native_id)
        if info is None:
            child = RecordedChild(
                creation, "autoremoved", previous.platform, previous.image_id
            )
        else:
            child = self._inspected(creation, info)
        payload = {
            key: value for key, value in asdict(child).items() if key != "creation"
        }
        if (
            child != previous
            or self.store._optional_read(self._observation_path(creation.native_id))
            is None
        ):
            self._publish_readback(creation, payload)
        replace_private_nofollow(
            self.store.ownership.root,
            self.store.relative / self._observation_path(creation.native_id),
            _encode(payload),
        )
        return child

    def observe(self) -> RecordedInventorySnapshot:
        """Capture every recorded child and report gaps as diagnostics."""
        children = []
        diagnostics = set(self.store.gaps())
        if self.store.pending():
            diagnostics.add("creation-response-unrecorded")
        for creation in self.store.records():
            try:
                children.append(self.capture(creation))
            except OSError, ValueError, OwnershipConflictError, PathContainmentError:
                diagnostics.add(_INSPECT_UNAVAILABLE)
                children.append(self._retained(creation))
        return RecordedInventorySnapshot(
            tuple(children), not diagnostics, tuple(sorted(diagnostics))[:16]
        )

    def _stop_expired(
        self,
        creation: RecordedCreation,
        cancelled: Callable[[], bool],
        mutation_context: Callable[[], AbstractContextManager[object]],
    ) -> None:
        """Stop one running child after its deadline unless cancelled."""
        if self.monotonic_clock() < self._deadline(creation):
            return
        with mutation_context():
            self.store.verify(creation.receipt())
            info = self.native.inspect(creation.native_id)
            if info is None:
                return
            self._require_identity(creation, info)
            if info["State"].get("Running") and not cancelled():
                self.native.stop(creation.native_id)

    def supervise(
        self,
        *,
        cancelled: Callable[[], bool] = lambda: False,
        mutation_context: Callable[[], AbstractContextManager[object]] = nullcontext,
    ) -> tuple[str, ...]:
        """Stop expired recorded children and return bounded diagnostics."""
        diagnostics = set()
        for creation in self.store.records():
            if cancelled():
                break
            try:
                self._stop_expired(creation, cancelled, mutation_context)
            except LifecycleBusyError:
                break
            except OSError, ValueError, OwnershipConflictError, PathContainmentError:
                diagnostics.add(_INSPECT_UNAVAILABLE)
        return tuple(sorted(diagnostics))
