"""Trial participants that one concrete trial SDL declares.

A participant is an SDL agent whose interactive-access nodes carry exactly one
software component with a ``model``. The agent's role selects its tool
profile. Its selected control-context assets, in authored order, form its
prompt. This module reads declarations only. It starts nothing and reads no
asset bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

from raes import Scenario

__all__ = ["DeclaredParticipant", "TrialDeclarationError", "declared_participants"]


class TrialDeclarationError(ValueError):
    """The trial SDL does not declare a runnable participant set."""


@dataclass(frozen=True)
class DeclaredParticipant:
    """One participant, its declared model, and its ordered prompt assets."""

    agent: str
    role: str
    model: str
    context_assets: tuple[str, ...]

    @property
    def address(self) -> str:
        return f"agents.{self.agent}"


def declared_participants(scenario: Scenario) -> tuple[DeclaredParticipant, ...]:
    """Return every model-bearing agent, or refuse an ambiguous declaration."""
    return ()
