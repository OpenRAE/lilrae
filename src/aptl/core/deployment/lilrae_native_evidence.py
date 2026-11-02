"""Original native proof bytes and immutable, non-authorizing cleanup witnesses."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Protocol
from uuid import uuid4

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    ResourceReceipt,
    WorkspaceOwnership,
    _decode_receipt,
    _receipt_bytes,
)
from aptl.core.deployment.lilrae_docker_recording import RecordingStore
from aptl.utils.pathsafe import (
    PathContainmentError,
    REASON_NOT_FOUND,
    create_exclusive_nofollow,
    listdir_contained_nofollow,
    open_contained_nofollow,
)

_ROOT = Path(".aptl/lifecycle/lilrae-native-evidence-v1")
_LIMIT = 128 * 1024
_FILES = 1024
_CLEANUP_CAUSES = frozenset({"after-remove", "already-absent"})


class _NativeAbsenceBackend(Protocol):
    """Backend surface that a native absence check uses."""

    def _current_docker_daemon_id(self) -> str | None:
        """Return the ID of the daemon that the backend uses now."""

        ...

    def _run(
        self, cmd: list[str], *, timeout: int | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run one backend-scoped command."""

        ...


def confirm_native_absence(
    backend: _NativeAbsenceBackend, receipt: ResourceReceipt
) -> bool:
    """Require a successful bounded enumeration on the receipt's daemon."""
    if backend._current_docker_daemon_id() != receipt.daemon_id:
        raise OwnershipConflictError(
            "cleanup daemon identity is unavailable or changed"
        )
    if receipt.kind == "container":
        command = ["docker", "container", "ls", "--all", "--no-trunc"]
        selector, output = f"id={receipt.native_id}", "{{.ID}}"
    elif receipt.kind == "network":
        command = ["docker", "network", "ls", "--no-trunc"]
        selector, output = f"id={receipt.native_id}", "{{.ID}}"
    elif receipt.kind == "volume":
        command = ["docker", "volume", "ls"]
        selector, output = f"name={receipt.native_id}", "{{.Name}}"
    else:
        raise OwnershipConflictError("cleanup resource kind is unsupported")
    result = backend._run(
        [*command, "--filter", selector, "--format", output], timeout=30
    )
    if (
        result.returncode != 0
        or not isinstance(result.stdout, str)
        or len(result.stdout) > 64 * 1024
    ):
        raise OwnershipConflictError("native absence could not be established")
    identities = result.stdout.splitlines()
    if len(identities) > _FILES or any(
        not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*"
            if receipt.kind == "volume"
            else r"[0-9a-f]{64}",
            identity,
        )
        for identity in identities
    ):
        raise OwnershipConflictError("native absence response is invalid")
    if backend._current_docker_daemon_id() != receipt.daemon_id:
        raise OwnershipConflictError("cleanup daemon identity changed")
    return receipt.native_id not in identities


def _read(root: Path, path: Path) -> bytes:
    """Read one protected native evidence file within its byte bound."""
    with open_contained_nofollow(root, path) as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise OwnershipConflictError("native evidence is not protected")
        if info.st_size > _LIMIT:
            raise BufferError("native proof exceeds its byte bound")
        data = handle.read(_LIMIT + 1)
    if len(data) > _LIMIT:
        raise BufferError("native proof exceeds its byte bound")
    return data


def _publish(root: Path, path: Path, data: bytes) -> None:
    """Write evidence once; accept an existing file only with the same bytes."""
    try:
        create_exclusive_nofollow(root, path, data)
    except FileExistsError:
        if _read(root, path) != data:
            raise OwnershipConflictError("native evidence identity conflicts") from None


def _directory(attempt_id: str) -> Path:
    """Return the evidence directory for one attempt."""
    return _ROOT / hashlib.sha256(attempt_id.encode()).hexdigest()


def record_cleanup(
    ownership: WorkspaceOwnership, receipt: ResourceReceipt, *, cause: str
) -> None:
    """Retain a receipt and an already verified absence; grant no authority."""
    if cause not in _CLEANUP_CAUSES:
        raise ValueError("invalid native cleanup observation")
    if (
        receipt.workspace_id != ownership.workspace_id
        or receipt.project_name != ownership.project_name
    ):
        raise OwnershipConflictError("native cleanup has another owner")
    original = _read(
        ownership.root, ownership._receipt_path(receipt.kind, receipt.native_id)
    )
    if original != _receipt_bytes(receipt):
        raise OwnershipConflictError("native cleanup receipt changed")
    digest = hashlib.sha256(original).hexdigest()
    directory = _directory(receipt.attempt_id)
    _publish(ownership.root, directory / "receipts" / f"{digest}.json", original)
    observation = {
        "schema": "lilrae.native-cleanup/v1",
        "kind": receipt.kind,
        "native_id": receipt.native_id,
        "attempt_id": receipt.attempt_id,
        "workspace_id": receipt.workspace_id,
        "project_name": receipt.project_name,
        "daemon_id": receipt.daemon_id,
        "receipt_sha256": digest,
        "state": "absent",
        "cause": cause,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    data = (
        json.dumps(observation, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    _publish(ownership.root, directory / "cleanup" / f"{uuid4().hex}.json", data)


def _files(root: Path, directory: Path) -> tuple[Path, ...]:
    """List the JSON files in one evidence directory; a missing directory is empty."""
    try:
        names = listdir_contained_nofollow(root, directory)
    except FileNotFoundError:
        return ()
    except PathContainmentError as exc:
        if exc.reason == REASON_NOT_FOUND:
            return ()
        raise
    if len(names) > _FILES:
        raise BufferError("native evidence exceeds its artifact bound")
    return tuple(directory / name for name in names if name.endswith(".json"))


def _require_receipt(
    ownership: WorkspaceOwnership,
    receipt: ResourceReceipt,
    attempt_id: str,
    daemon_id: str,
) -> None:
    """Make sure that the receipt belongs to this owner, attempt, and daemon."""
    if (
        receipt.attempt_id != attempt_id
        or receipt.daemon_id != daemon_id
        or receipt.workspace_id != ownership.workspace_id
        or receipt.project_name != ownership.project_name
    ):
        raise OwnershipConflictError("native evidence has another owner or attempt")


def _receipt_artifacts(
    ownership: WorkspaceOwnership, attempt_id: str, daemon_id: str
) -> dict[str, bytes]:
    """Collect current and retained receipt bytes by their SHA-256 digest."""
    receipts: dict[str, bytes] = {}
    for kind in ("container", "network", "volume"):
        for receipt in ownership.receipts(kind):
            if receipt.attempt_id != attempt_id:
                continue
            _require_receipt(ownership, receipt, attempt_id, daemon_id)
            data = _read(
                ownership.root, ownership._receipt_path(kind, receipt.native_id)
            )
            if data != _receipt_bytes(receipt):
                raise OwnershipConflictError("native resource receipt changed")
            receipts[hashlib.sha256(data).hexdigest()] = data
    for path in _files(ownership.root, _directory(attempt_id) / "receipts"):
        data = _read(ownership.root, path)
        receipt = _decode_receipt(data)
        _require_receipt(ownership, receipt, attempt_id, daemon_id)
        if path.stem != hashlib.sha256(data).hexdigest():
            raise OwnershipConflictError("retained native receipt changed")
        receipts[path.stem] = data
    return receipts


def _valid_cleanup(
    payload: dict[str, object],
    receipt: ResourceReceipt,
    attempt_id: str,
    daemon_id: str,
) -> bool:
    """Return True when a cleanup witness matches its receipt and attempt."""
    expected = {
        "schema": "lilrae.native-cleanup/v1",
        "native_id": receipt.native_id,
        "kind": receipt.kind,
        "attempt_id": attempt_id,
        "daemon_id": daemon_id,
        "workspace_id": receipt.workspace_id,
        "project_name": receipt.project_name,
        "state": "absent",
    }
    return (
        all(payload[key] == value for key, value in expected.items())
        and payload["cause"] in _CLEANUP_CAUSES
    )


def _cleanup_artifacts(
    ownership: WorkspaceOwnership,
    attempt_id: str,
    daemon_id: str,
    receipts: dict[str, bytes],
) -> list[tuple[str, bytes]]:
    """Collect the cleanup witnesses that match retained receipts."""
    artifacts = []
    for path in _files(ownership.root, _directory(attempt_id) / "cleanup"):
        data = _read(ownership.root, path)
        payload = json.loads(data)
        receipt = _decode_receipt(receipts[payload["receipt_sha256"]])
        _require_receipt(ownership, receipt, attempt_id, daemon_id)
        if not _valid_cleanup(payload, receipt, attempt_id, daemon_id):
            raise OwnershipConflictError("native cleanup witness is invalid")
        artifacts.append(("native-cleanup/v1", data))
    return artifacts


def _creation_artifacts(store: RecordingStore) -> list[tuple[str, bytes]]:
    """Collect the verified creation proofs of recorded children."""
    artifacts = []
    for creation in store.records():
        store.verify(creation.receipt())
        data = _read(
            store.ownership.root,
            store.relative / "children" / f"{creation.native_id}.json",
        )
        if json.loads(data) != asdict(creation):
            raise OwnershipConflictError("native creation proof changed")
        artifacts.append(("native-creation/v1", data))
    return artifacts


def _readback_artifacts(
    store: RecordingStore, attempt_id: str, daemon_id: str
) -> list[tuple[str, bytes]]:
    """Collect the readbacks that match a verified recorded creation."""
    artifacts = []
    for path in _files(store.ownership.root, store.relative / "readbacks"):
        data = _read(store.ownership.root, path)
        payload = json.loads(data)
        creation = store.creation(payload["native_id"])
        store.verify(creation.receipt())
        if (
            payload["schema"] != "lilrae.native-readback/v1"
            or payload["attempt_id"] != attempt_id
            or payload["daemon_id"] != daemon_id
            or payload["creation_digest"] != creation.evidence_digest
            or set(payload["observation"]) != {"state", "platform", "image_id"}
        ):
            raise OwnershipConflictError("native readback identity is invalid")
        artifacts.append(("native-readback/v1", data))
    return artifacts


def _recording_artifacts(store: RecordingStore) -> list[tuple[str, bytes]]:
    """Collect the retained intents, responses, and recording gaps."""
    artifacts = []
    for category, role in (
        ("intents", "native-create-intent/v1"),
        ("responses", "native-create-response/v1"),
        ("gaps", "native-recording-gap/v1"),
    ):
        for path in _files(store.ownership.root, store.relative / category):
            artifacts.append((role, _read(store.ownership.root, path)))
    return artifacts


def native_evidence_artifacts(
    ownership: WorkspaceOwnership, attempt_id: str, daemon_id: str
) -> tuple[tuple[str, bytes], ...]:
    """Export only this owner's original retained bytes; perform no native action."""
    ownership.labels(attempt_id=attempt_id)
    receipts = _receipt_artifacts(ownership, attempt_id, daemon_id)
    artifacts = [("native-resource-receipt/v1", data) for data in receipts.values()]
    artifacts += _cleanup_artifacts(ownership, attempt_id, daemon_id, receipts)
    store = RecordingStore(ownership, daemon_id=daemon_id, attempt_id=attempt_id)
    artifacts += _creation_artifacts(store)
    artifacts += _readback_artifacts(store, attempt_id, daemon_id)
    artifacts += _recording_artifacts(store)
    if len(artifacts) > _FILES:
        raise BufferError("native evidence exceeds its artifact bound")
    return tuple(artifacts)
