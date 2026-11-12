"""The caller-supplied identity and deadline of one trial attempt."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts import AdmittedTrialPlanModel

__all__ = ["TrialAttempt", "TrialUnit", "load_trial_unit", "parse_trial_attempt"]

#: The canonical instantiated snapshot limit that family trial admission applies.
MAX_TRIAL_UNIT_BYTES = 32 * 1024 * 1024

# The run store's identifier contract: a run ID names one run directory.
_IDENTIFIER = re.compile(r"^\w[\w.-]{0,127}$", re.ASCII)
_UTC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


@dataclass(frozen=True)
class TrialUnit:
    """One admitted RAES plan entry and its exact instantiated snapshot bytes."""

    plan: AdmittedTrialPlanModel = field(repr=False)
    plan_entry_id: str
    snapshot: bytes = field(repr=False)
    #: Original retained scientific contracts; executable code stays installed.
    material: dict[str, Any] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class TrialAttempt:
    """Run and attempt IDs and the UTC deadline that the caller owns.

    ``unit`` is the admitted plan entry to run. Without it, the trial runs the
    SDL that the project selects.
    """

    run_id: str
    attempt_id: str
    deadline: datetime
    unit: TrialUnit | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name, value in (("run ID", self.run_id), ("attempt ID", self.attempt_id)):
            if (
                not isinstance(value, str)
                or not _IDENTIFIER.fullmatch(value)
                or ".." in value
            ):
                raise ValueError(f"trial {name} is invalid")
        if self.deadline.tzinfo is None or self.deadline.utcoffset() != UTC.utcoffset(
            None
        ):
            raise ValueError("trial deadline must be a UTC time")


def parse_trial_attempt(
    run_id: str | None, attempt_id: str | None, deadline: str | None
) -> TrialAttempt | None:
    """Return ``None`` with no trial options, or one validated attempt.

    Raise ``ValueError`` for a partial option set, an unsafe ID, or a deadline
    that is not an RFC 3339 UTC time.
    """
    values = (run_id, attempt_id, deadline)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("--run-id, --attempt-id and --deadline are required together")
    assert deadline is not None
    if not _UTC_TIME.fullmatch(deadline):
        raise ValueError("--deadline must be an RFC 3339 UTC time ending in Z")
    parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00")).astimezone(UTC)
    return TrialAttempt(str(run_id), str(attempt_id), parsed)


def load_trial_unit(path: Path) -> TrialUnit:
    """Read one ``{plan, plan_entry_id, snapshot}`` trial input file.

    The plan passes the RAES plan ingress gate. Family trial admission later
    binds the plan entry, the installed family and the snapshot bytes.
    """
    from raes_contracts.canonical import canonical_json_bytes
    from raes_contracts.json_ingress import parse_bounded_json_object
    from raes_contracts.contracts.admitted_trial_plan_ingress import (
        parse_admitted_trial_plan_json,
    )

    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_TRIAL_UNIT_BYTES
    ):
        raise ValueError("--trial-input must be a regular file within the size limit")
    document = parse_bounded_json_object(
        path.read_bytes(), max_bytes=MAX_TRIAL_UNIT_BYTES, max_depth=128
    )
    keys = {"plan", "plan_entry_id", "snapshot"}
    if not isinstance(document, dict) or set(document) not in (
        keys,
        keys | {"material"},
    ):
        raise ValueError("--trial-input contains an unsupported trial input shape")
    material = document.get("material")
    if material is not None and (
        not isinstance(material, dict)
        or set(material) != {"experiment", "task", "capture_specs", "authority"}
    ):
        raise ValueError("--trial-input has incomplete retained scientific contracts")
    entry = document["plan_entry_id"]
    if not isinstance(entry, str) or not _IDENTIFIER.fullmatch(entry):
        raise ValueError("--trial-input plan entry ID is invalid")
    plan = parse_admitted_trial_plan_json(canonical_json_bytes(document["plan"]))
    if entry not in plan.entries:
        raise ValueError("--trial-input plan has no such entry")
    if material is not None:
        _validate_material(plan, material)
    return TrialUnit(plan, entry, canonical_json_bytes(document["snapshot"]), material)


def _validate_material(plan: AdmittedTrialPlanModel, material: dict[str, Any]) -> None:
    """Check scientific contracts against the exact references in the admitted plan."""
    from raes_contracts.canonical import canonical_contract_digest
    from raes_contracts.contracts import (
        ExperimentCaptureSpecModel,
        ExperimentSpecModel,
        ExperimentTaskModel,
    )

    experiment = ExperimentSpecModel.model_validate(material["experiment"])
    task = ExperimentTaskModel.model_validate(material["task"])
    specs = material["capture_specs"]
    if not isinstance(specs, dict):
        raise ValueError("trial capture specifications must be a map")
    captures = tuple(
        ExperimentCaptureSpecModel.model_validate(value) for value in specs.values()
    )
    inputs = plan.input_refs
    authoring = inputs.authoring_input_ref
    if (
        (authoring.ref_id, authoring.ref_version, authoring.ref_digest)
        != (
            experiment.spec_id,
            experiment.spec_version,
            canonical_contract_digest(experiment),
        )
        or (inputs.task_ref.ref_id, inputs.task_ref.ref_version, inputs.task_digest)
        != (task.task_id, task.task_version, canonical_contract_digest(task))
        or len(captures) != len(inputs.capture_spec_refs)
        or {
            (item.capture_spec_id, item.spec_version, canonical_contract_digest(item))
            for item in captures
        }
        != {
            (ref.ref_id, ref.ref_version, ref.ref_digest)
            for ref in inputs.capture_spec_refs
        }
    ):
        raise ValueError("trial scientific contracts differ from the admitted plan")
