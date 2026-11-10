"""The closed model of the report that the per-run worker prints."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from aptl.core.containment import (
    FailureOrigin,
    PropertyObservation,
    ReasonCode,
    RequiredProperty,
    RunStatus,
    TargetOutcome,
)

WORKER_REPORT_SCHEMA = "lilrae.containment.worker-report/v1"

# The worker never observes cancellation or its own failure; the adapter does.
_WORKER_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.REFUSED,
        RunStatus.TIMED_OUT,
        RunStatus.OUTPUT_LIMIT_EXCEEDED,
    }
)


class WorkerReport(BaseModel):
    """What the worker observed; the adapter adds identity, bounds and cleanup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["lilrae.containment.worker-report/v1"]
    status: RunStatus
    failure_origin: FailureOrigin
    reason: ReasonCode | None
    detail: Annotated[str, StringConstraints(max_length=512)] | None
    properties: tuple[PropertyObservation, ...]
    target: TargetOutcome | None
    containment_tier: Annotated[str, StringConstraints(max_length=32)] | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status not in _WORKER_STATUSES:
            raise ValueError("the worker cannot report this status")
        if sorted(item.property for item in self.properties) != sorted(RequiredProperty):
            raise ValueError("properties must list each required property once")
        if (self.status is RunStatus.REFUSED) != (self.target is None):
            raise ValueError("a target outcome exists exactly when the run was not refused")
        return self
