"""Restricted, original-byte handoff from native owners to experiment collectors."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from importlib.metadata import version
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4
import zipfile

from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.realization_preparation import jsonable_fallback, to_jsonable_python
from raes_contracts.runtime_state import RuntimeSnapshotEnvelope

from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import CaptureVisibility
from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.utils.pathsafe import (
    PathContainmentError,
    create_exclusive_nofollow,
    listdir_contained_nofollow,
    open_contained_nofollow,
)

_ROOT = Path("native-evidence")
_MAX_MEMBER = 8 * 1024 * 1024
_MAX_BYTES = 64 * 1024 * 1024
_MAX_MEMBERS = 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _json_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class LilraeRuntimeEvidence:
    """Retain native cuts; provide a narrow source only for protected bindings."""

    def __init__(self, archive, backend):
        self.archive = archive
        self.backend = backend
        self.run_id = archive.run_id
        self.failed = False

    @property
    def _root(self):
        return self.archive.store.base_dir

    def _read(self, relative, *, limit=_MAX_MEMBER):
        path = Path(self.run_id) / _ROOT / relative
        with open_contained_nofollow(self._root, path) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("native evidence requires protected regular files")
            if info.st_size > limit:
                raise BufferError("native evidence exceeds the collection bound")
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise BufferError("native evidence exceeds the collection bound")
        return data

    def _publish(self, relative, data):
        if len(data) > _MAX_MEMBER:
            raise BufferError("native evidence member exceeds the bound")
        with self.archive.store.finalization_lock(self.run_id):
            if self.archive.store.is_sealed(self.run_id):
                raise ValueError("native evidence run is sealed")
            try:
                create_exclusive_nofollow(
                    self._root, Path(self.run_id) / _ROOT / relative, data
                )
            except FileExistsError:
                if self._read(relative) != data:
                    raise ValueError("native evidence identity conflicts") from None

    def _blob(self, role, data, **metadata):
        digest = hashlib.sha256(data).hexdigest()
        path = Path("objects") / f"{digest}.bin"
        self._publish(path, data)
        return {
            "role": role,
            "sha256": digest,
            "size_bytes": len(data),
            "path": path.as_posix(),
            **metadata,
        }

    def _native(self):
        reader = getattr(self.backend, "native_evidence_artifacts", None)
        if not callable(reader):
            raise ValueError("native evidence source is unsupported")
        artifacts = reader(self.run_id)
        if not isinstance(artifacts, tuple) or len(artifacts) > _MAX_MEMBERS:
            raise ValueError("native evidence source is invalid")
        for role, data in artifacts:
            if not isinstance(role, str) or not isinstance(data, bytes):
                raise ValueError("native evidence source is invalid")
            if len(data) > _MAX_MEMBER:
                raise BufferError("native evidence member exceeds the bound")
            payload = json.loads(data)
            if (
                not isinstance(payload, dict)
                or payload.get("attempt_id", self.run_id) != self.run_id
            ):
                raise ValueError("native evidence belongs to another attempt")
        return artifacts

    def capture(self, execution, snapshot, *, phase, success=None, operation=None):
        """Record already accepted public state without changing its provenance."""
        try:
            self._capture(
                execution, snapshot, phase=phase, success=success, operation=operation
            )
        except OSError, ValueError, TypeError, BufferError, PathContainmentError:
            # Capture policy owns disposition; this never changes a committed
            # native result or makes its effects appear unknown to the runtime.
            self.failed = True

    def _capture(self, execution, snapshot, *, phase, success, operation):
        source = execution.provisioning.materialization_source
        if source is None or source.run_id != self.run_id:
            raise ValueError("native evidence belongs to another run")
        payload = to_jsonable_python(snapshot, fallback=jsonable_fallback)
        artifacts = [
            self._blob(
                "runtime-snapshot",
                _json_bytes(
                    {
                        "schema_version": RuntimeSnapshotEnvelope().schema_version,
                        **payload,
                    }
                ),
            )
        ]
        artifacts.append(
            self._blob(
                "requested-constraints",
                _json_bytes(
                    to_jsonable_python(
                        execution.provisioning, fallback=jsonable_fallback
                    )
                ),
            )
        )
        for record in snapshot.materialization_attestations:
            original = self.archive.read(record).sdl.encode("utf-8")
            metadata = record.model_dump(mode="json")
            artifacts.append(
                self._blob("materialized-sdl", original, archive_record=metadata)
            )
            artifacts.append(
                self._blob("materialization-archive-record", _json_bytes(metadata))
            )
        cut = {
            "schema": "lilrae.native-evidence-cut/v1",
            "run_id": self.run_id,
            "attempt_id": self.run_id,
            "target_scope": execution.target_name,
            "phase": phase,
            "success": success,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "producer_versions": {
                name: version(name) for name in ("lilrae", "raes", "raes-env-packs")
            },
            "operation": to_jsonable_python(operation, fallback=jsonable_fallback),
            "plan_digest": runtime_plan_digest(execution.provisioning),
            "artifacts": artifacts,
        }
        self._publish(Path("cuts") / f"{uuid4().hex}.json", _json_bytes(cut))

    def source(self, binding):
        """Use the incumbent collector boundary without exposing protected data."""
        if (
            binding.visibility_class
            not in {
                CaptureVisibility.EVALUATOR_ONLY,
                CaptureVisibility.APPARATUS_ONLY,
            }
            or binding.redaction_required
            or binding.sensitivity != "restricted"
            or "application/zip" not in binding.expected_media_types
        ):
            raise ValueError("native evidence requires a protected exact-byte binding")
        limit = min(_MAX_BYTES, binding.limits.max_bytes)
        return CallableWindowedSource(lambda _start, _end: self._fetch(limit))

    def _fetch(self, limit):
        try:
            if self.failed:
                raise ValueError("native evidence capture was incomplete")
            content = self._package(limit)
        except BufferError:
            return SourceResult(status=CollectorStatus.TRUNCATION)
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            PathContainmentError,
            OwnershipConflictError,
        ):
            return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
        return SourceResult(
            status=CollectorStatus.OK,
            chunks=(content,),
            media_type="application/zip",
            source_pipeline={
                "contract": "lilrae.native-evidence-handoff/v1",
                "run_id": self.run_id,
                "attempt_id": self.run_id,
                "scope": "bound-native-attempt",
                "sensitivity": "restricted",
            },
        )

    def _artifact_bytes(self, artifact, objects, remaining):
        digest = artifact["sha256"]
        if not _HASH.fullmatch(digest) or artifact["path"] != f"objects/{digest}.bin":
            raise ValueError("native evidence artifact identity is invalid")
        data = objects.get(artifact["path"])
        if data is None:
            data = self._read(artifact["path"], limit=min(_MAX_MEMBER, remaining))
        if (
            len(data) != artifact["size_bytes"]
            or hashlib.sha256(data).hexdigest() != digest
        ):
            raise ValueError("native evidence original bytes changed")
        if artifact["role"] == "materialized-sdl":
            original = artifact["archive_record"]["artifact"]
            if (
                original["size_bytes"] != len(data)
                or original["checksum"]["value"] != digest
            ):
                raise ValueError("materialization archive record changed")
        return data

    def _package(self, limit):
        names = listdir_contained_nofollow(
            self._root, Path(self.run_id) / _ROOT / "cuts"
        )
        if not names or len(names) > _MAX_MEMBERS:
            raise ValueError("native evidence cuts are unavailable")
        cuts = []
        objects = {}
        remaining = limit
        for name in names:
            if not re.fullmatch(r"[0-9a-f]{32}\.json", name):
                raise ValueError("native evidence cut is invalid")
            cut = json.loads(
                self._read(Path("cuts") / name, limit=min(_MAX_MEMBER, remaining))
            )
            if (
                cut["schema"] != "lilrae.native-evidence-cut/v1"
                or cut["run_id"] != self.run_id
                or cut["attempt_id"] != self.run_id
            ):
                raise ValueError("native evidence cut has another identity")
            if len(cut["artifacts"]) > _MAX_MEMBERS:
                raise BufferError("native evidence cut exceeds its artifact bound")
            for artifact in cut["artifacts"]:
                data = self._artifact_bytes(artifact, objects, remaining)
                if artifact["path"] not in objects:
                    objects[artifact["path"]] = data
                    remaining -= len(data)
            cuts.append(cut)
        native = []
        for role, data in self._native():
            digest = hashlib.sha256(data).hexdigest()
            path = f"objects/{digest}.bin"
            if path not in objects:
                remaining -= len(data)
                objects[path] = data
            native.append(
                {"role": role, "sha256": digest, "size_bytes": len(data), "path": path}
            )
        if remaining < 0 or len(objects) > _MAX_MEMBERS:
            raise BufferError("native evidence collection exceeds its bound")
        index = {
            "schema": "lilrae.native-evidence-handoff/v1",
            "run_id": self.run_id,
            "attempt_id": self.run_id,
            "cuts": cuts,
            "native_artifacts": native,
        }
        stream = BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as bundle:
            for path, data in sorted(
                {"index.json": _json_bytes(index), **objects}.items()
            ):
                bundle.writestr(zipfile.ZipInfo(path), data)
                if stream.tell() > limit:
                    raise BufferError("native evidence collection exceeds its bound")
        if stream.tell() > limit:
            raise BufferError("native evidence collection exceeds its bound")
        return stream.getvalue()
