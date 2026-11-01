"""Native cleanup authority and checked readback shared by adapters."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
import re

type CleanupAction = Literal["destroy", "verify"]
type NativeCleanupState = Literal["absent", "present", "unverified"]


@dataclass(frozen=True)
class CleanupBinding:
    """Trusted whole-attempt binding, never constructed from authored intent."""

    plan_entry_id: str
    run_id: str
    execution_attempt_id: str
    native_attempt_id: str
    boundary_id: str
    owner_ref: str
    resource_refs: tuple[str, ...]
    project_dir: Path

    def __post_init__(self) -> None:
        identifiers = (
            self.plan_entry_id,
            self.run_id,
            self.execution_attempt_id,
            self.native_attempt_id,
            self.boundary_id,
            self.owner_ref,
            *self.resource_refs,
        )
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}", value)
            for value in identifiers
        ):
            raise ValueError("cleanup binding identity is invalid")
        if self.execution_attempt_id in {self.run_id, self.plan_entry_id}:
            raise ValueError("cleanup execution attempt must remain distinct")
        if not self.resource_refs or len(self.resource_refs) != len(
            set(self.resource_refs)
        ):
            raise ValueError("cleanup binding resources must be nonempty and unique")


@dataclass(frozen=True)
class CleanupResourceState:
    """Bounded native fact; inspect payloads never cross this boundary."""

    kind: Literal["container", "network", "volume"]
    native_id: str
    state: NativeCleanupState

    def __post_init__(self) -> None:
        if self.kind not in {"container", "network", "volume"} or self.state not in {
            "absent",
            "present",
            "unverified",
        }:
            raise ValueError("invalid cleanup resource state")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,255}", self.native_id):
            raise ValueError("invalid cleanup native identity")


@dataclass(frozen=True)
class CleanupReadback:
    """Checked resources and stable diagnostic codes from their native owner."""

    resources: tuple[CleanupResourceState, ...]
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.resources) > 4096 or len(self.reasons) > 32:
            raise ValueError("cleanup readback exceeds its item bound")
        if any(
            not re.fullmatch(r"[a-z][a-z-]{0,63}", reason) for reason in self.reasons
        ):
            raise ValueError("cleanup diagnostics must be stable reason codes")

    @property
    def absent(self) -> bool:
        """An empty or failed inventory cannot certify native absence."""
        return (
            bool(self.resources)
            and not self.reasons
            and all(resource.state == "absent" for resource in self.resources)
        )


class CleanupOwner(Protocol):
    """Native effects stay behind an explicitly installed authority owner."""

    binding: CleanupBinding

    def execute(self, action: CleanupAction, timeout_seconds: int) -> CleanupReadback:
        """Perform a supported action with one total authored time budget."""
        ...
