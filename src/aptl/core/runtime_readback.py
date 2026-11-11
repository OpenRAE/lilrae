"""One native runtime reading and the vantage that produced it."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.vocabulary import ObservationStrength


@dataclass(frozen=True)
class ConcernReading:
    """A realized concern value, separate from its compiler-owned authority."""

    kind: str
    value: object
    source: ObservationStrength

    def __post_init__(self) -> None:
        if (
            not self.kind
            or self.value is None
            or self.source
            not in {
                ObservationStrength.DAEMON_OBSERVED,
                ObservationStrength.GUEST_OBSERVED,
            }
        ):
            raise ValueError("runtime-reading-invalid")
