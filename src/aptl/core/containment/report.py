"""Version 1 of the shared containment execution report."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from aptl.core.containment._encoding import Base64Payload
from aptl.core.containment.request import RequiredProperty

REPORT_SCHEMA = "lilrae.containment.report/v1"


class RunStatus(StrEnum):
    """How one run ended."""

    COMPLETED = "completed"
    REFUSED = "refused"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    SUPERVISOR_FAILED = "supervisor_failed"


class FailureOrigin(StrEnum):
    """Where a failure occurred: before the target, in the target, or around it."""

    NONE = "none"
    SETUP = "setup"
    TARGET = "target"
    SUPERVISOR = "supervisor"


class PropertyState(StrEnum):
    """What the worker observed for one required property."""

    DELIVERED = "delivered"
    REFUSED = "refused"
    UNKNOWN = "unknown"


class ReasonCode(StrEnum):
    """A stable reason for a status other than a clean completion."""

    PROPERTY_UNAVAILABLE = "property_unavailable"
    ENVIRONMENT_NAME_DENIED = "environment_name_denied"
    INPUT_UNAVAILABLE = "input_unavailable"
    ENGINE_SETUP_FAILED = "engine_setup_failed"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    CANCELLED = "cancelled"
    CLEANUP_UNCONFIRMED = "cleanup_unconfirmed"
    SUPERVISOR_FAILED = "supervisor_failed"
    CONTAINMENT_UNCONFIRMED = "containment_unconfirmed"


type Detail = Annotated[str, StringConstraints(max_length=512)]


class _Closed(BaseModel):
    """A frozen model that refuses unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PropertyObservation(_Closed):
    """The observed state of one required property and its evidence basis."""

    property: RequiredProperty
    state: PropertyState
    basis: Annotated[str, StringConstraints(max_length=256)]


class TargetOutcome(_Closed):
    """The target's exit and its bounded output; null means not observed.

    ``exit_code`` uses shell encoding: 128 + n means signal n or exit status 128 + n.
    """

    exit_code: int | None
    stdout: Base64Payload = Field(repr=False)
    stderr: Base64Payload = Field(repr=False)
    stdout_bytes: int = Field(ge=0)
    stderr_bytes: int = Field(ge=0)
    truncated: bool


type Version = Annotated[str, StringConstraints(max_length=32)]


class EngineIdentity(_Closed):
    """The engine implementation and the host components that this run used."""

    implementation: Literal["lilrae.containment.bubblewrap/v1"]
    bubblewrap_version: Version | None
    landlock_abi: int | None
    libseccomp_version: Version | None


class HostIdentity(_Closed):
    """The kernel that ran the target."""

    kernel_release: Annotated[str, StringConstraints(max_length=128)]


class AppliedBounds(_Closed):
    """The bounds in force; ``peak_memory`` states that none is enforced."""

    deadline_seconds: float
    max_output_bytes: int
    cpu_seconds: int | None
    max_file_mb: int | None
    address_space_mb: int | None
    peak_memory: Literal["not-enforced"] = "not-enforced"


class CleanupObservation(_Closed):
    """What cleanup of the worker process group could still observe."""

    residual: tuple[str, ...]
    seconds: float


class ExecutionReport(_Closed):
    """The trusted result of one run."""

    schema_version: Literal["lilrae.containment.report/v1"]
    run_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
    label: str
    status: RunStatus
    failure_origin: FailureOrigin
    reason: ReasonCode | None
    detail: Detail | None
    contained: bool
    properties: tuple[PropertyObservation, ...]
    target: TargetOutcome | None
    engine: EngineIdentity
    host: HostIdentity
    bounds: AppliedBounds
    cleanup: CleanupObservation | None
    run_dir: Path | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        observed = [item.property for item in self.properties]
        if sorted(observed) != sorted(RequiredProperty):
            raise ValueError("properties must list each required property once")
        delivered = all(item.state is PropertyState.DELIVERED for item in self.properties)
        if self.contained and (self.target is None or not delivered):
            raise ValueError(
                "contained requires a started target and every property delivered"
            )
        return self
