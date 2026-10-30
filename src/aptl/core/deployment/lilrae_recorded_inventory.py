"""Bounded, value-free readback and deadline supervision of recorded native IDs."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
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


class RecordedNative(Protocol):
    def inspect(self, native_id: str) -> dict | None: ...
    def stop(self, native_id: str) -> None: ...


@dataclass(frozen=True)
class RecordedChild:
    creation: RecordedCreation
    state: str = "active"
    platform: str = ""
    image_id: str = ""


@dataclass(frozen=True)
class RecordedInventorySnapshot:
    children: tuple[RecordedChild, ...] = ()
    complete: bool = True
    diagnostics: tuple[str, ...] = ()


class RecordedInventory:
    def __init__(
        self,
        store: RecordingStore,
        native: RecordedNative,
        *,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.native = native
        self.wall_clock = wall_clock
        self.monotonic_clock = monotonic_clock
        self._deadlines: dict[str, float] = {}

    def _deadline(self, creation: RecordedCreation) -> float:
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
        return Path("observations") / f"{native_id}.json"

    def _retained(self, creation: RecordedCreation) -> RecordedChild:
        raw = self.store._optional_read(self._observation_path(creation.native_id))
        if raw is None:
            return RecordedChild(creation)
        if set(raw) != {"state", "platform", "image_id"} or raw["state"] not in {
            "active",
            "terminated",
            "autoremoved",
        }:
            raise OwnershipConflictError("recorded child observation is invalid")
        return RecordedChild(creation, **raw)

    def capture(self, creation: RecordedCreation) -> RecordedChild:
        self.store.verify(creation.receipt())
        self._deadline(creation)
        previous = self._retained(creation)
        info = self.native.inspect(creation.native_id)
        if info is None:
            child = RecordedChild(
                creation, "autoremoved", previous.platform, previous.image_id
            )
        else:
            if info.get("Id") != creation.native_id or not isinstance(
                info.get("State"), dict
            ):
                raise OwnershipConflictError(
                    "recorded child native identity is unavailable"
                )
            state = (
                "terminated"
                if info["State"].get("Status") in {"exited", "dead"}
                else "active"
            )
            platform = (
                info.get("Platform")
                if info.get("Platform") in {"linux", "windows"}
                else ""
            )
            image_id = info.get("Image", "")
            if not isinstance(image_id, str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", image_id, re.ASCII
            ):
                image_id = ""
            child = RecordedChild(creation, state, platform, image_id)
        payload = {
            key: value for key, value in asdict(child).items() if key != "creation"
        }
        if (
            child != previous
            or self.store._optional_read(self._observation_path(creation.native_id))
            is None
        ):
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
        replace_private_nofollow(
            self.store.ownership.root,
            self.store.relative / self._observation_path(creation.native_id),
            _encode(payload),
        )
        return child

    def observe(self) -> RecordedInventorySnapshot:
        children = []
        diagnostics = set(self.store.gaps())
        if self.store.pending():
            diagnostics.add("creation-response-unrecorded")
        for creation in self.store.records():
            try:
                children.append(self.capture(creation))
            except OSError, ValueError, OwnershipConflictError, PathContainmentError:
                diagnostics.add("child-inspect-unavailable")
                children.append(self._retained(creation))
        return RecordedInventorySnapshot(
            tuple(children), not diagnostics, tuple(sorted(diagnostics))[:16]
        )

    def supervise(
        self,
        *,
        cancelled: Callable[[], bool] = lambda: False,
        mutation_context: Callable = nullcontext,
    ) -> tuple[str, ...]:
        diagnostics = set()
        for creation in self.store.records():
            if cancelled():
                break
            try:
                if self.monotonic_clock() < self._deadline(creation):
                    continue
                with mutation_context():
                    self.store.verify(creation.receipt())
                    info = self.native.inspect(creation.native_id)
                    if info is None:
                        continue
                    if info.get("Id") != creation.native_id or not isinstance(
                        info.get("State"), dict
                    ):
                        raise OwnershipConflictError(
                            "recorded child native identity is unavailable"
                        )
                    if info["State"].get("Running") and not cancelled():
                        self.native.stop(creation.native_id)
            except LifecycleBusyError:
                break
            except OSError, ValueError, OwnershipConflictError, PathContainmentError:
                diagnostics.add("child-inspect-unavailable")
        return tuple(sorted(diagnostics))
