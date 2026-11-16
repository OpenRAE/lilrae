"""Restricted, original-byte handoff from native owners to experiment collectors."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import stat
from typing import IO, TYPE_CHECKING, BinaryIO
from uuid import uuid4
import zipfile

from raes_contracts.contracts.plan_projection import runtime_plan_digest
from pydantic_core import to_jsonable_python
from raes_contracts.canonical import jsonable_fallback
from raes_contracts.runtime_state import RuntimeSnapshotEnvelope

from aptl.core.evidence.adapters.sources import CallableWindowedSource, SourceResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.spool import StreamedContent, new_spool
from aptl.core.experiment.capture_registry import CaptureVisibility
from aptl.core.deployment._compose_resource_ownership import OwnershipConflictError
from aptl.utils.pathsafe import (
    PathContainmentError,
    create_exclusive_nofollow,
    listdir_contained_nofollow,
    open_contained_nofollow,
)

if TYPE_CHECKING:
    from raes_contracts.runtime_state import OperationStatus, RuntimeSnapshot
    from raes_processor.models import ExecutionPlan

    from aptl.backends.lilrae_materialization_archive import (
        LilraeMaterializationArchive,
    )
    from aptl.core.experiment.capture_registry import CaptureBinding

_ROOT = Path("native-evidence")
_ZIP_MEDIA_TYPE = "application/zip"
_COPY_CHUNK = 1024 * 1024

_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CUT_NAME = re.compile(r"[0-9a-f]{32}\.json")
_CUT_SCHEMA = "lilrae.native-evidence-cut/v1"


def _json_bytes(value: object) -> bytes:
    """Encode a value as canonical UTF-8 JSON bytes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class LilraeRuntimeEvidence:
    """Retain native cuts; provide a narrow source only for protected bindings."""

    def __init__(
        self,
        archive: LilraeMaterializationArchive,
        backend: object,
        *,
        provisioner: object | None = None,
    ) -> None:
        self.archive = archive
        self.backend = backend
        self.provisioner = provisioner
        self.run_id = archive.run_id
        self.failed = False

    @property
    def _root(self) -> Path:
        """Return the base directory of the protected run store."""
        return self.archive.store.base_dir

    def _open(self, relative: Path | str) -> BinaryIO:
        """Open one protected native evidence file without following links."""
        path = Path(self.run_id) / _ROOT / relative
        handle = open_contained_nofollow(self._root, path)
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            handle.close()
            raise ValueError("native evidence requires protected regular files")
        return handle

    def _read(self, relative: Path | str) -> bytes:
        """Read one complete protected native evidence file."""
        with self._open(relative) as handle:
            return handle.read()

    def _publish(self, relative: Path, data: bytes) -> None:
        """Write one native evidence file once, or confirm identical bytes."""
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

    def _blob(self, role: str, data: bytes, **metadata: object) -> dict[str, object]:
        """Store bytes by digest and return the artifact entry."""
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

    def _native(self) -> tuple[tuple[str, bytes], ...]:
        """Read and validate the backend native evidence for this attempt."""
        reader = getattr(self.backend, "native_evidence_artifacts", None)
        if not callable(reader):
            raise ValueError("native evidence source is unsupported")
        artifacts = reader(self.run_id)
        if not isinstance(artifacts, tuple):
            raise ValueError("native evidence source is invalid")
        for role, data in artifacts:
            if not isinstance(role, str) or not isinstance(data, bytes):
                raise ValueError("native evidence source is invalid")
            payload = json.loads(data)
            if (
                not isinstance(payload, dict)
                or payload.get("attempt_id", self.run_id) != self.run_id
            ):
                raise ValueError("native evidence belongs to another attempt")
        return artifacts

    def capture(
        self,
        execution: ExecutionPlan,
        snapshot: RuntimeSnapshot,
        *,
        phase: str,
        success: bool | None = None,
        operation: OperationStatus | None = None,
    ) -> None:
        """Record already accepted public state without changing its provenance."""
        try:
            self._capture(
                execution, snapshot, phase=phase, success=success, operation=operation
            )
        except OSError, ValueError, TypeError, PathContainmentError:
            # Capture policy owns disposition; this never changes a committed
            # native result or makes its effects appear unknown to the runtime.
            self.failed = True

    def _capture(
        self,
        execution: ExecutionPlan,
        snapshot: RuntimeSnapshot,
        *,
        phase: str,
        success: bool | None,
        operation: OperationStatus | None,
    ) -> None:
        """Store the cut artifacts and the cut index for one runtime state."""
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
        images = getattr(self.provisioner, "last_source_image_evidence", {})
        if images:
            artifacts.append(
                self._blob("realization-source-image-evidence", _json_bytes(images))
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
            "schema": _CUT_SCHEMA,
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

    def source(self, binding: CaptureBinding) -> CallableWindowedSource:
        """Use the incumbent collector boundary without exposing protected data."""
        if (
            binding.visibility_class
            not in {
                CaptureVisibility.EVALUATOR_ONLY,
                CaptureVisibility.APPARATUS_ONLY,
            }
            or binding.redaction_required
            or binding.sensitivity != "restricted"
            or _ZIP_MEDIA_TYPE not in binding.expected_media_types
        ):
            raise ValueError("native evidence requires a protected exact-byte binding")
        return CallableWindowedSource(lambda _start, _end: self._fetch())

    def reference_source(self, binding: CaptureBinding) -> CallableWindowedSource:
        """Return JSON references to a retained native archive, without relabeling it."""
        if (
            binding.visibility_class
            not in {CaptureVisibility.EVALUATOR_ONLY, CaptureVisibility.APPARATUS_ONLY}
            or binding.redaction_required
            or binding.sensitivity != "restricted"
            or "application/json" not in binding.expected_media_types
        ):
            raise ValueError("native references require a protected binding")

        def fetch(_start: str, _end: str) -> SourceResult:
            """Retain references to the existing native archive bytes."""
            from aptl.core.evidence.content_store import create_content_addressed

            result = self._fetch()
            if result.status is not CollectorStatus.OK:
                return result
            try:
                content = create_content_addressed(
                    self.archive.store,
                    self.run_id,
                    result.chunks,
                    subdir="native-evidence/exports",
                )
            except OSError, ValueError, PathContainmentError:
                return SourceResult(status=CollectorStatus.SOURCE_UNAVAILABLE)
            return SourceResult(
                status=CollectorStatus.OK,
                records=[
                    {
                        "run_id": self.run_id,
                        "native_archive": {
                            "uri": content.relative_path,
                            "media_type": _ZIP_MEDIA_TYPE,
                            "sha256": content.digest,
                            "size_bytes": content.size,
                        },
                    }
                ],
            )

        return CallableWindowedSource(fetch)

    def _fetch(self) -> SourceResult:
        """Package the evidence and map failures to collector status."""
        try:
            if self.failed:
                raise ValueError("native evidence capture was incomplete")
            content = self._package()
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
            chunks=content,
            media_type=_ZIP_MEDIA_TYPE,
            source_pipeline={
                "contract": "lilrae.native-evidence-handoff/v1",
                "run_id": self.run_id,
                "attempt_id": self.run_id,
                "scope": "bound-native-attempt",
                "sensitivity": "restricted",
            },
        )

    @staticmethod
    def _verify_artifact(artifact: dict[str, object]) -> None:
        """Check one cut artifact's identity before its bytes are copied."""
        digest = artifact["sha256"]
        if not _HASH.fullmatch(digest) or artifact["path"] != f"objects/{digest}.bin":
            raise ValueError("native evidence artifact identity is invalid")
        if artifact["role"] == "materialized-sdl":
            original = artifact["archive_record"]["artifact"]
            if (
                original["size_bytes"] != artifact["size_bytes"]
                or original["checksum"]["value"] != digest
            ):
                raise ValueError("materialization archive record changed")

    def _read_cut(self, name: str) -> dict[str, object]:
        """Read one cut file and verify that it belongs to this run."""
        if not _CUT_NAME.fullmatch(name):
            raise ValueError("native evidence cut is invalid")
        cut = json.loads(self._read(Path("cuts") / name))
        if (
            cut["schema"] != _CUT_SCHEMA
            or cut["run_id"] != self.run_id
            or cut["attempt_id"] != self.run_id
        ):
            raise ValueError("native evidence cut has another identity")
        return cut

    def _collect_cuts(
        self, objects: dict[str, bytes | dict[str, object]]
    ) -> list[dict[str, object]]:
        """Read all cuts and add their artifacts to ``objects``."""
        names = listdir_contained_nofollow(
            self._root, Path(self.run_id) / _ROOT / "cuts"
        )
        if not names:
            raise ValueError("native evidence cuts are unavailable")
        cuts = []
        for name in names:
            cut = self._read_cut(name)
            for artifact in cut["artifacts"]:
                self._verify_artifact(artifact)
                objects.setdefault(artifact["path"], artifact)
            cuts.append(cut)
        return cuts

    def _collect_native(
        self, objects: dict[str, bytes | dict[str, object]]
    ) -> list[dict[str, object]]:
        """Add backend native artifacts to ``objects``."""
        native = []
        for role, data in self._native():
            digest = hashlib.sha256(data).hexdigest()
            path = f"objects/{digest}.bin"
            objects.setdefault(path, data)
            native.append(
                {"role": role, "sha256": digest, "size_bytes": len(data), "path": path}
            )
        return native

    def _copy_artifact(self, artifact: dict[str, object], target: IO[bytes]) -> None:
        """Stream one retained artifact and require its recorded digest and size."""
        hasher = hashlib.sha256()
        size = 0
        with self._open(artifact["path"]) as source:
            while chunk := source.read(_COPY_CHUNK):
                hasher.update(chunk)
                size += len(chunk)
                target.write(chunk)
        if size != artifact["size_bytes"] or hasher.hexdigest() != artifact["sha256"]:
            raise ValueError("native evidence original bytes changed")

    def _package(self) -> StreamedContent:
        """Stream the ZIP handoff of all cuts and native artifacts into a spool."""
        objects: dict[str, bytes | dict[str, object]] = {}
        cuts = self._collect_cuts(objects)
        native = self._collect_native(objects)
        index = {
            "schema": "lilrae.native-evidence-handoff/v1",
            "run_id": self.run_id,
            "attempt_id": self.run_id,
            "cuts": cuts,
            "native_artifacts": native,
        }
        members = {"index.json": _json_bytes(index), **objects}
        spool = new_spool()
        with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_STORED) as bundle:
            for path, member in sorted(members.items()):
                info = zipfile.ZipInfo(path)
                if isinstance(member, bytes):
                    bundle.writestr(info, member)
                    continue
                info.file_size = member["size_bytes"]
                large = info.file_size >= zipfile.ZIP64_LIMIT
                with bundle.open(info, "w", force_zip64=large) as target:
                    self._copy_artifact(member, target)
        spool.flush()
        return StreamedContent(spool, event_count=1)
