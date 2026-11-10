"""Version 1 of the shared containment execution request."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from aptl.core.containment._encoding import Base64Payload

REQUEST_SCHEMA = "lilrae.containment.request/v1"
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_STDIN_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024

type Profile = Literal["linux-full"]


class RequiredProperty(StrEnum):
    """One independently checked protection of the Linux profile."""

    NAMESPACES = "namespaces"
    FILESYSTEM_POLICY = "filesystem_policy"
    SYSCALL_SOCKET_FILTER = "syscall_socket_filter"
    DESCRIPTOR_ENVIRONMENT_HYGIENE = "descriptor_environment_hygiene"
    SUPERVISION = "supervision"


_PROFILE_PROPERTIES: dict[str, tuple[RequiredProperty, ...]] = {
    "linux-full": tuple(RequiredProperty),
}


def profile_properties(profile: Profile) -> tuple[RequiredProperty, ...]:
    """Return every property that ``profile`` requires."""
    return _PROFILE_PROPERTIES[profile]


def _without_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("value contains a NUL character")
    return value


def _absolute(value: str) -> str:
    if not value.startswith("/"):
        raise ValueError("the executable must be an absolute path")
    return value


def _absolute_path(value: Path | None) -> Path | None:
    if value is not None and not value.is_absolute():
        raise ValueError("input_dir must be an absolute path")
    return value


def _bounded_stdin(value: bytes) -> bytes:
    if len(value) > MAX_STDIN_BYTES:
        raise ValueError(f"stdin exceeds {MAX_STDIN_BYTES} bytes")
    return value


def _absolute_executable(argv: tuple[str, ...]) -> tuple[str, ...]:
    _absolute(argv[0])
    return argv


type Argument = Annotated[
    str, StringConstraints(min_length=1, max_length=4096), AfterValidator(_without_nul)
]
type EnvironmentName = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
]
type EnvironmentValue = Annotated[
    str, StringConstraints(max_length=8192), AfterValidator(_without_nul)
]


class ExecutionLimits(BaseModel):
    """Finite bounds for one run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    deadline_seconds: float = Field(gt=0, le=3600, allow_inf_nan=False)
    max_output_bytes: int = Field(ge=1, le=MAX_OUTPUT_BYTES)
    cpu_seconds: int | None = Field(default=None, ge=1, le=86400)
    max_file_mb: int | None = Field(default=None, ge=1, le=1048576)
    address_space_mb: int | None = Field(default=None, ge=1, le=1048576)


class ExecutionRequest(BaseModel):
    """One command, its inputs, and its bounds; no shell and no engine options."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["lilrae.containment.request/v1"]
    profile: Profile
    label: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
    argv: Annotated[
        tuple[Argument, ...],
        Field(min_length=1, max_length=256),
        AfterValidator(_absolute_executable),
    ]
    env: dict[EnvironmentName, EnvironmentValue] = Field(max_length=64)
    stdin: Annotated[Base64Payload, AfterValidator(_bounded_stdin)] = Field(repr=False)
    input_dir: Annotated[Path | None, AfterValidator(_absolute_path)]
    limits: ExecutionLimits
    network: Literal["none"]
