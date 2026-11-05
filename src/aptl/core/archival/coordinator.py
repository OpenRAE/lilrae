"""Archive coordinator for owner-produced run records (EXP-009 / ADR-050).

:func:`finalize_terminal_attempt` is invoked exactly once when an execution
attempt reaches any terminal cause. It composes the validated public RAES run
record, publishes it as the canonical ``manifest.json`` create-once, reads and
checksums every already-written sealed artifact into a closed inventory, then
sequences the ADR-050 commit: a *prepared* discovery-index entry, the atomic
durable *seal marker*, and the *committed* index entry. A crash before the marker
leaves an unsealed recovery candidate — never a partially sealed run. Identical
finalization is idempotent; a differing record for the same attempt is a
conflict.

The coordinator does not rediscover facts from mutable state, calculate metrics,
reconstruct captures, or run another execution state machine — it consumes the
immutable terminal context or a validated producer record and seals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from raes_contracts.contracts import ExperimentRunModel
from raes_contracts.canonical import canonical_contract_digest

from aptl.core.archival.context import TerminalAttemptContext
from aptl.core.archival.discovery_index import DiscoveryIndex, IndexEntry
from aptl.core.archival.layout import (
    RUN_MANIFEST_RELPATH,
)
from aptl.core.archival.run_record import build_experiment_run_model
from aptl.core.archival.seal import (
    SealInventoryEntry,
    SealLimitation,
    SealMarkerInputs,
    SealedArtifactSpec,
    build_inventory_entry,
    build_seal_marker,
)
from aptl.core.archival.verify import verify_sealed_archive
from aptl.core.runstore import LocalRunStore, RunStoreConflictError
from aptl.utils.logging import get_logger

log = get_logger("archival.coordinator")

_MANIFEST_SPEC = SealedArtifactSpec(
    path=RUN_MANIFEST_RELPATH, media_type="application/json", role="manifest"
)


@dataclass(frozen=True)
class SealResult:
    """The outcome of sealing one immutable run record."""

    run: ExperimentRunModel
    run_record_digest: str
    manifest_path: Path
    seal_marker_path: Path
    inventory: tuple[SealInventoryEntry, ...]
    index_entry: IndexEntry
    idempotent: bool


def finalize_terminal_attempt(
    context: TerminalAttemptContext,
    *,
    store: LocalRunStore,
    index: DiscoveryIndex | None = None,
    completeness_statement: str | None = None,
) -> SealResult:
    """Compose, validate, and atomically seal one terminal attempt.

    Raises the RAES validators' errors when the record is not conformant (the
    seal gate) and :class:`RunStoreConflictError` when the attempt was already
    sealed with a different record.
    """
    run = build_experiment_run_model(context)
    return seal_produced_run(
        run,
        store=store,
        index=index,
        artifacts=context.sealed_artifacts,
        limitations=context.accepted_limitations,
        completeness_statement=completeness_statement,
    )


def seal_produced_run(
    run: ExperimentRunModel,
    *,
    store: LocalRunStore,
    artifacts: tuple[SealedArtifactSpec, ...] = (),
    limitations: tuple[SealLimitation, ...] = (),
    index: DiscoveryIndex | None = None,
    observed_at: str | None = None,
    completeness_statement: str | None = None,
) -> SealResult:
    """Commit an owner-produced record without changing its outcome or times.

    An unresolved record needs a retained observation time for local indexing.
    That routing time never becomes the run's end time. Each portable version
    uses its own store namespace; sealed working evidence is never reopened.
    """
    run = ExperimentRunModel.model_validate(run.model_dump(mode="json"))
    terminal_at = run.ended_at or observed_at
    if terminal_at is None:
        raise ValueError("partial archive requires its retained observation time")
    run_record_digest = canonical_contract_digest(run)
    index = index or DiscoveryIndex(store.base_dir)

    index_entry = IndexEntry(
        run_id=run.run_id,
        run_version=run.run_version,
        manifest_digest=run_record_digest,
        seal_state="sealed",
        terminal_at=terminal_at,
        location=RUN_MANIFEST_RELPATH,
    )

    # Hold the store-owned per-attempt finalization lock across compose
    # verification, manifest publication, inventory verification, and marker
    # commit so two finalizers of the same attempt cannot race (ADR-050).
    with store.finalization_lock(run.run_id):
        prior = verify_sealed_archive(store.base_dir, run.run_id)
        if prior is not None and prior.run_record_digest != run_record_digest:
            raise RunStoreConflictError("produced record conflicts with its sealed version")
        manifest_path = store.get_run_path(run.run_id) / RUN_MANIFEST_RELPATH
        if prior is None:
            store.create_run(run.run_id)
            manifest_path = store.create_run_json_once(
                run.run_id, RUN_MANIFEST_RELPATH, run.model_dump(mode="json")
            )
        inventory = _build_inventory(store, run.run_id, artifacts)
        accepted = _accepted_limitations(run, limitations)
        statement = completeness_statement or _default_completeness_statement(
            run, inventory, accepted
        )
        marker = build_seal_marker(
            SealMarkerInputs(
                run_id=run.run_id,
                run_version=run.run_version,
                run_status=run.run_status,
                outcome_status=run.outcome_status,
                run_record_digest=run_record_digest,
                inventory=inventory,
                contract_versions=_sealed_contract_versions(run, artifacts),
                limitations=accepted,
                completeness_statement=statement,
            )
        )
        if prior is not None and store.read_seal_marker(run.run_id) != marker:
            raise RunStoreConflictError("produced inventory conflicts with its sealed version")

        # ADR-050 commit sequence: prepared entry names the expected identity,
        # then the atomic seal marker is the archive commit point, then the
        # committed entry. Each step is idempotent on identical bytes.
        index.prepare(index_entry)
        seal_marker_path = store.commit_seal_marker(run.run_id, marker)
        index.commit(index_entry)

    log.info(
        "sealed run record %s (run_status=%s, outcome=%s, artifacts=%d)",
        run.run_id,
        run.run_status,
        run.outcome_status,
        len(inventory),
    )
    return SealResult(
        run=run,
        run_record_digest=run_record_digest,
        manifest_path=manifest_path,
        seal_marker_path=seal_marker_path,
        inventory=tuple(inventory),
        index_entry=index_entry,
        idempotent=prior is not None,
    )


def _accepted_limitations(
    run: ExperimentRunModel, limitations: tuple[SealLimitation, ...],
) -> list[SealLimitation]:
    """Disclose a partial record without changing its portable state."""
    accepted = list(limitations)
    if run.record_state == "partial":
        accepted.append(SealLimitation("partial-record", "RAES retained an incomplete trial record."))
    return accepted


def _build_inventory(
    store: LocalRunStore, run_id: str, artifacts: tuple[SealedArtifactSpec, ...]
) -> list[SealInventoryEntry]:
    """Read and checksum the manifest plus every sealed artifact into the inventory."""
    inventory = [build_inventory_entry(store, run_id, _MANIFEST_SPEC)]
    for spec in artifacts:
        inventory.append(build_inventory_entry(store, run_id, spec))
    return inventory


def _sealed_contract_versions(
    run: ExperimentRunModel, artifacts: tuple[SealedArtifactSpec, ...]
) -> list[str]:
    """Collect the contract versions the sealed byte graph spans."""
    versions = {run.schema_version}
    if run.apparatus_context is not None:
        versions.add(run.apparatus_context.schema_version)
    if any("evidence" in spec.role for spec in artifacts):
        versions.add("experiment-evidence-record/v1")
    return sorted(versions)


def _default_completeness_statement(
    run: ExperimentRunModel,
    inventory: list[SealInventoryEntry],
    limitations: list[SealLimitation],
) -> str:
    """Return a safe, bounded default completeness statement.

    It names only IDs, statuses, and counts — never captured content — so it
    cannot leak evidence or secrets into the marker.
    """
    if limitations:
        limitation_clause = f"{len(limitations)} accepted limitation(s)"
    else:
        limitation_clause = "no accepted limitations"
    return (
        f"Sealed run record {run.run_id} run_version {run.run_version}: "
        f"run_status={run.run_status}, outcome_status={run.outcome_status}, "
        f"{len(inventory)} bound artifact(s), {limitation_clause}."
    )
