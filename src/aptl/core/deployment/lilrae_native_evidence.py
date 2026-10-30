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
from uuid import uuid4

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
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


def confirm_native_absence(backend, receipt):
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


def _read(root, path):
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


def _publish(root, path, data):
    try:
        create_exclusive_nofollow(root, path, data)
    except FileExistsError:
        if _read(root, path) != data:
            raise OwnershipConflictError("native evidence identity conflicts") from None


def _directory(attempt_id):
    return _ROOT / hashlib.sha256(attempt_id.encode()).hexdigest()


def record_cleanup(ownership, receipt, *, cause):
    """Retain a receipt and an already verified absence; grant no authority."""
    if cause not in {"after-remove", "already-absent"}:
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


def _files(root, directory):
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


def _require_receipt(ownership, receipt, attempt_id, daemon_id):
    if (
        receipt.attempt_id != attempt_id
        or receipt.daemon_id != daemon_id
        or receipt.workspace_id != ownership.workspace_id
        or receipt.project_name != ownership.project_name
    ):
        raise OwnershipConflictError("native evidence has another owner or attempt")


def _receipt_artifacts(ownership, attempt_id, daemon_id):
    receipts = {}
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


def native_evidence_artifacts(ownership, attempt_id, daemon_id):
    """Export only this owner's original retained bytes; perform no native action."""
    ownership.labels(attempt_id=attempt_id)
    receipts = _receipt_artifacts(ownership, attempt_id, daemon_id)
    artifacts = [("native-resource-receipt/v1", data) for data in receipts.values()]
    for path in _files(ownership.root, _directory(attempt_id) / "cleanup"):
        data = _read(ownership.root, path)
        payload = json.loads(data)
        receipt = _decode_receipt(receipts[payload["receipt_sha256"]])
        _require_receipt(ownership, receipt, attempt_id, daemon_id)
        if (
            payload["schema"] != "lilrae.native-cleanup/v1"
            or payload["native_id"] != receipt.native_id
            or payload["kind"] != receipt.kind
            or payload["attempt_id"] != attempt_id
            or payload["daemon_id"] != daemon_id
            or payload["workspace_id"] != receipt.workspace_id
            or payload["project_name"] != receipt.project_name
            or payload["state"] != "absent"
            or payload["cause"] not in {"after-remove", "already-absent"}
        ):
            raise OwnershipConflictError("native cleanup witness is invalid")
        artifacts.append(("native-cleanup/v1", data))
    store = RecordingStore(ownership, daemon_id=daemon_id, attempt_id=attempt_id)
    for creation in store.records():
        store.verify(creation.receipt())
        data = _read(
            ownership.root, store.relative / "children" / f"{creation.native_id}.json"
        )
        if json.loads(data) != asdict(creation):
            raise OwnershipConflictError("native creation proof changed")
        artifacts.append(("native-creation/v1", data))
    for path in _files(ownership.root, store.relative / "readbacks"):
        data = _read(ownership.root, path)
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
    for category, role in (
        ("intents", "native-create-intent/v1"),
        ("responses", "native-create-response/v1"),
        ("gaps", "native-recording-gap/v1"),
    ):
        for path in _files(ownership.root, store.relative / category):
            artifacts.append((role, _read(ownership.root, path)))
    if len(artifacts) > _FILES:
        raise BufferError("native evidence exceeds its artifact bound")
    return tuple(artifacts)
