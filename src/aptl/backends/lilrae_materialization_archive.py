"""Bind RAES protected bytes to the existing local run seal and write lock."""

from __future__ import annotations

import os
import hashlib
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from raes import parse_sdl
from raes_operations.run_artifacts import RunMaterializationArchive, is_valid_run_id_label
from raes_contracts.materialization import (
    MATERIALIZATION_MAX_BYTES,
    MaterializationSubmission,
    require_materialization_records,
)

from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import create_exclusive_nofollow, open_contained_nofollow

if TYPE_CHECKING:
    from raes_contracts.contracts.materialization_attestation import (
        MaterializationArchiveRecord,
    )


class LilraeMaterializationArchive:
    """RAES references are relative to the run's materialization directory."""

    def __init__(self, store: LocalRunStore, run_id: str) -> None:
        if not isinstance(store, LocalRunStore):
            raise ValueError("Materialization requires protected local run storage")
        self.store = store
        self.run_id = run_id
        expected = store.base_dir / run_id
        if store.get_run_path(run_id) != expected:
            raise ValueError("Materialization run directory is not an owned path")
        self.archive = RunMaterializationArchive(expected / "materialization")

    def publish(self, content: str) -> MaterializationArchiveRecord:
        """Publish one materialized SDL once into the protected run store."""
        if parse_sdl(content).materialization_provenance.run_id != self.run_id:
            raise ValueError("Materialization belongs to another run")
        with self.store.finalization_lock(self.run_id):
            if self.store.is_sealed(self.run_id):
                raise ValueError("Materialization run is sealed")
            # Reuse the public publisher's canonical bytes and validation, then
            # publish through the store's descriptor-relative containment.
            with TemporaryDirectory(prefix="lilrae-materialization-") as directory:
                temporary = RunMaterializationArchive(Path(directory))
                record = temporary.publish(content)
                data = temporary.read(record).sdl.encode("utf-8")
            try:
                create_exclusive_nofollow(self.store.base_dir, self._path(record), data)
            except FileExistsError:
                if self.read(record).sdl.encode("utf-8") != data:
                    raise ValueError("Materialization identity conflicts") from None
            self.read(record)
            return record

    def _path(self, record: MaterializationArchiveRecord) -> Path:
        """Return the contained store path for a valid archive record."""
        require_materialization_records((record,))
        if record.run_id != self.run_id:
            raise ValueError("Materialization belongs to another run")
        if not is_valid_run_id_label(record.reference.ref_id):
            raise ValueError("Materialization reference has an unsafe identity")
        expected = (
            Path("runs")
            / self.run_id
            / "attestations"
            / f"{record.reference.ref_id}.sdl"
        )
        if record.reference.ref_path != expected.as_posix():
            raise ValueError("Materialization reference has an invalid path")
        return Path(self.run_id) / "materialization" / expected

    def read(self, record: MaterializationArchiveRecord) -> MaterializationSubmission:
        """Read the protected SDL bytes and verify them against the record."""
        with open_contained_nofollow(self.store.base_dir, self._path(record)) as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > MATERIALIZATION_MAX_BYTES
            ):
                raise ValueError("Materialization is not a bounded protected file")
            data = handle.read(MATERIALIZATION_MAX_BYTES + 1)
        if (
            len(data) != record.artifact.size_bytes
            or hashlib.sha256(data).hexdigest() != record.artifact.checksum.value
        ):
            raise ValueError("Materialization bytes differ from the retained record")
        return MaterializationSubmission(sdl=data.decode("utf-8"))
