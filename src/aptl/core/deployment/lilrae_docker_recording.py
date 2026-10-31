"""Private causal receipts for cooperative Docker API creation recording.

Only a daemon-issued create response supplies a native ID. Intents, labels,
names and image matches never grant authority. These records describe calls
through the recorder; unrestricted daemon holders can bypass that boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import time
from uuid import uuid4

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    ResourceReceipt,
    WorkspaceOwnership,
)
from aptl.utils.pathsafe import (
    PathContainmentError,
    REASON_NOT_FOUND,
    create_exclusive_nofollow,
    listdir_contained_nofollow,
    read_contained_nofollow,
)

_NATIVE_ID = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ADDRESS = re.compile(r"provision\.node\.[A-Za-z0-9_.-]{1,240}\Z", re.ASCII)
_TOKEN = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_INVALID = "Docker creation receipt is absent, invalid, or outside this attempt"
_RECORD_SUFFIX = ".json"


def recording_digest(value: object) -> str:
    """Digest only a value-free identity record, never a Docker request body."""
    return "sha256:" + hashlib.sha256(_encode(value)).hexdigest()


def _encode(value: object) -> bytes:
    """Encode a value as one canonical JSON line."""
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


@dataclass(frozen=True)
class CreationIntent:
    """Record one admitted create request before the daemon answers it."""

    operation_id: str
    source_address: str
    parent_native_id: str
    created_utc: float
    deadline_utc: float
    timeout_seconds: int

    def __post_init__(self) -> None:
        """Reject an intent with an invalid identity or time window."""
        if not (self._valid_identity() and self._valid_window()):
            raise OwnershipConflictError(_INVALID)

    def _valid_identity(self) -> bool:
        """Return True when the operation, source, and parent IDs are valid."""
        valid_parent = not self.parent_native_id or _NATIVE_ID.fullmatch(
            self.parent_native_id
        )
        return bool(
            _TOKEN.fullmatch(self.operation_id)
            and _ADDRESS.fullmatch(self.source_address)
            and valid_parent
        )

    def _valid_window(self) -> bool:
        """Return True when the timeout and the deadline window are valid."""
        return (
            type(self.timeout_seconds) is int
            and 0 < self.timeout_seconds <= 86400
            and math.isfinite(self.created_utc)
            and math.isfinite(self.deadline_utc)
            and 0 <= self.created_utc
            and self.deadline_utc <= self.created_utc + self.timeout_seconds
        )


@dataclass(frozen=True)
class RecordedCreation:
    """Record one container that a daemon create response identified."""

    native_id: str
    address: str
    parent_address: str
    source_address: str
    parent_native_id: str
    created_utc: float
    deadline_utc: float
    timeout_seconds: int
    operation_id: str
    workspace_id: str
    project_name: str
    daemon_id: str
    attempt_id: str

    @property
    def evidence_digest(self) -> str:
        """Return the digest of this creation record."""
        return recording_digest(asdict(self))

    def receipt(self) -> ResourceReceipt:
        """Return the native resource receipt for this child container."""
        return ResourceReceipt(
            kind="container",
            native_id=self.native_id,
            external_name=self.native_id,
            semantic_name=self.address.removeprefix("provision.node."),
            node_address=self.address,
            workspace_id=self.workspace_id,
            project_name=self.project_name,
            daemon_id=self.daemon_id,
            attempt_id=self.attempt_id,
            managed_by="child",
        )


class RecordingStore:
    """Append-only creation state alongside the incumbent native receipt store."""

    def __init__(
        self,
        ownership: WorkspaceOwnership,
        *,
        daemon_id: str,
        attempt_id: str,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        ownership.labels(attempt_id=attempt_id)
        if not daemon_id or len(daemon_id) > 256:
            raise OwnershipConflictError(_INVALID)
        self.ownership = ownership
        self.daemon_id = daemon_id
        self.attempt_id = attempt_id
        self.wall_clock = wall_clock
        self.relative = (
            Path(".aptl/lifecycle/lilrae-docker-recording-v1")
            / hashlib.sha256(attempt_id.encode()).hexdigest()
        )

    def begin(
        self,
        source_address: str,
        *,
        timeout_seconds: int,
        parent_native_id: str = "",
    ) -> CreationIntent:
        """Publish a create intent for a source, bounded by its parent deadline."""
        now = self.wall_clock()
        deadline = now + timeout_seconds
        if parent_native_id:
            parent = self.creation(parent_native_id)
            self.verify(parent.receipt())
            if parent.source_address != source_address:
                raise OwnershipConflictError(_INVALID)
            deadline = min(deadline, parent.deadline_utc)
        intent = CreationIntent(
            uuid4().hex,
            source_address,
            parent_native_id,
            now,
            deadline,
            timeout_seconds,
        )
        self._publish(Path("intents") / f"{intent.operation_id}.json", asdict(intent))
        return intent

    def commit(self, intent: CreationIntent, native_id: str) -> RecordedCreation:
        """Publish the response ID and lineage before returning it to a holder."""
        if not _NATIVE_ID.fullmatch(native_id):
            raise OwnershipConflictError(_INVALID)
        if self._read(Path("intents") / f"{intent.operation_id}.json") != asdict(
            intent
        ):
            raise OwnershipConflictError(_INVALID)
        parent_address = intent.source_address
        if intent.parent_native_id:
            parent_address = self.creation(intent.parent_native_id).address
        identity = recording_digest(
            [self.daemon_id, self.attempt_id, native_id]
        ).removeprefix("sha256:")
        creation = RecordedCreation(
            native_id=native_id,
            address=f"provision.node.lilrae-{identity[:28]}",
            parent_address=parent_address,
            source_address=intent.source_address,
            parent_native_id=intent.parent_native_id,
            created_utc=intent.created_utc,
            deadline_utc=intent.deadline_utc,
            timeout_seconds=intent.timeout_seconds,
            operation_id=intent.operation_id,
            workspace_id=self.ownership.workspace_id,
            project_name=self.ownership.project_name,
            daemon_id=self.daemon_id,
            attempt_id=self.attempt_id,
        )
        # Binding the operation first also rejects a conflicting repeated response.
        self._publish(
            Path("responses") / f"{intent.operation_id}.json", {"native_id": native_id}
        )
        self._publish(Path("children") / f"{native_id}.json", asdict(creation))
        self.ownership.record(creation.receipt())
        return creation

    def failed(self, intent: CreationIntent) -> None:
        """A conclusive rejected create did not allocate a native resource."""
        self._publish(
            Path("responses") / f"{intent.operation_id}.json", {"native_id": ""}
        )

    def creation(self, native_id: str) -> RecordedCreation:
        """Return a verified creation record, or raise an ownership conflict."""
        try:
            return self._creation(native_id)
        except (OSError, PathContainmentError, TypeError, ValueError) as exc:
            raise OwnershipConflictError(_INVALID) from exc

    def _creation(self, native_id: str) -> RecordedCreation:
        """Read a creation record and check it against its intent and response."""
        if not _NATIVE_ID.fullmatch(native_id):
            raise OwnershipConflictError(_INVALID)
        try:
            creation = RecordedCreation(
                **self._read(Path("children") / f"{native_id}.json")
            )
            intent = CreationIntent(
                creation.operation_id,
                creation.source_address,
                creation.parent_native_id,
                creation.created_utc,
                creation.deadline_utc,
                creation.timeout_seconds,
            )
        except (TypeError, ValueError) as exc:
            raise OwnershipConflictError(_INVALID) from exc
        if (
            creation.native_id != native_id
            or creation.workspace_id != self.ownership.workspace_id
            or creation.project_name != self.ownership.project_name
            or creation.daemon_id != self.daemon_id
            or creation.attempt_id != self.attempt_id
            or self._read(Path("intents") / f"{intent.operation_id}.json")
            != asdict(intent)
            or self._read(Path("responses") / f"{intent.operation_id}.json")
            != {"native_id": native_id}
        ):
            raise OwnershipConflictError(_INVALID)
        return creation

    def verify(self, receipt: ResourceReceipt) -> RecordedCreation:
        """Verify a receipt and its parent chain, and return its creation record."""
        creation = self.creation(receipt.native_id)
        if receipt != creation.receipt():
            raise OwnershipConflictError(_INVALID)
        child = creation
        seen = {creation.native_id}
        while child.parent_native_id:
            parent = self.creation(child.parent_native_id)
            if (
                parent.native_id in seen
                or len(seen) >= 64
                or parent.address != child.parent_address
                or parent.source_address != creation.source_address
                or child.deadline_utc > parent.deadline_utc
            ):
                raise OwnershipConflictError(_INVALID)
            seen.add(parent.native_id)
            child = parent
        if child.parent_address != child.source_address:
            raise OwnershipConflictError(_INVALID)
        return creation

    def records(self) -> tuple[RecordedCreation, ...]:
        """Return all verified creation records of this attempt."""
        return tuple(
            self.creation(name.removesuffix(_RECORD_SUFFIX))
            for name in self._names("children")
        )

    def pending(self) -> tuple[CreationIntent, ...]:
        """Return the intents that have no complete recorded outcome."""
        pending = []
        receipts = set(self.ownership.receipts("container"))
        for name in self._names("intents"):
            relative = Path("responses") / name
            response = self._optional_read(relative)
            complete = response == {"native_id": ""}
            if response is not None and response.get("native_id"):
                try:
                    complete = (
                        self.creation(response["native_id"]).receipt() in receipts
                    )
                except OwnershipConflictError:
                    complete = False
            if not complete:
                pending.append(CreationIntent(**self._read(Path("intents") / name)))
        return tuple(pending)

    def recover_responses(self) -> None:
        """Finish publication only when a trusted daemon response ID survived."""
        for intent in self.pending():
            response = self._optional_read(
                Path("responses") / f"{intent.operation_id}.json"
            )
            if response is not None and response.get("native_id"):
                self.commit(intent, response["native_id"])

    def gap(self, code: str) -> None:
        """Retain a bounded controlled diagnostic without native payload text."""
        if not re.fullmatch(r"[a-z-]{1,64}", code, re.ASCII):
            raise ValueError("invalid recording diagnostic")
        self._publish(Path("gaps") / f"{code}.json", {"code": code})

    def gaps(self) -> tuple[str, ...]:
        """Return the recorded diagnostic gap codes."""
        return tuple(name.removesuffix(_RECORD_SUFFIX) for name in self._names("gaps"))

    def _names(self, directory: str) -> list[str]:
        """Return the sorted record names in a state directory."""
        try:
            names = listdir_contained_nofollow(
                self.ownership.root, self.relative / directory
            )
        except FileNotFoundError:
            return []
        except PathContainmentError as exc:
            if exc.reason == REASON_NOT_FOUND:
                return []
            raise OwnershipConflictError(_INVALID) from exc
        return sorted(name for name in names if name.endswith(_RECORD_SUFFIX))

    def _optional_read(self, relative: Path) -> dict[str, object] | None:
        """Return a state record, or None when it does not exist."""
        try:
            return self._read(relative)
        except FileNotFoundError:
            return None
        except PathContainmentError as exc:
            if exc.reason == REASON_NOT_FOUND:
                return None
            raise OwnershipConflictError(_INVALID) from exc

    def _read(self, relative: Path) -> dict[str, object]:
        """Return a state record that must be a JSON object."""
        try:
            value = json.loads(
                read_contained_nofollow(self.ownership.root, self.relative / relative)
            )
            if not isinstance(value, dict):
                raise ValueError(_INVALID)
            return value
        except (ValueError, TypeError) as exc:
            raise OwnershipConflictError(_INVALID) from exc

    def _publish(self, relative: Path, value: dict[str, object]) -> None:
        """Write a state record once, and reject a different later value."""
        payload = _encode(value)
        try:
            create_exclusive_nofollow(
                self.ownership.root, self.relative / relative, payload
            )
        except FileExistsError:
            if self._read(relative) != value:
                raise OwnershipConflictError(_INVALID)
