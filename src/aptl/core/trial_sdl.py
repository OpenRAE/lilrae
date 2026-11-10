"""Trial participants that one concrete trial SDL declares.

A participant is an SDL agent whose interactive-access nodes carry exactly one
software component with a ``model``. The agent's role selects its tool
profile. Its selected control-context assets, in authored order, form its
prompt. This module reads declarations only. It starts nothing and reads no
asset bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

from raes import Scenario, build_declaration_index
from raes.participant_control_context import resolve_authored_control_context

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
    selections, errors = resolve_authored_control_context(
        scenario, build_declaration_index(scenario)
    )
    if errors:
        raise TrialDeclarationError(
            "trial SDL control context is invalid: " + ", ".join(errors)
        )
    participants = []
    for name in scenario.agents:
        model = _declared_model(scenario, name)
        if model is None:
            continue
        address = f"agents.{name}"
        assets = tuple(
            selection.declaration_address.removeprefix("control_context_assets.")
            for selection in selections
            if selection.participant_address == address
            and selection.disposition == "selected"
        )
        if not assets:
            raise TrialDeclarationError(f"trial participant {address} selects no prompt")
        participants.append(
            DeclaredParticipant(
                agent=name,
                role=_declared_role(scenario, name),
                model=model,
                context_assets=assets,
            )
        )
    return tuple(participants)


def admitted_participants(scenario: Scenario, configurations) -> tuple[DeclaredParticipant, ...]:
    """Return each admitted participant with its configured model and prompt selections.

    An admitted family trial owns participant configuration, so its owner-validated
    configurations, not authored control context, select the model and prompt assets.
    """
    participants = []
    for configuration in configurations:
        address = configuration.participant_address
        name = address.removeprefix("agents.")
        if address != f"agents.{name}" or name not in scenario.agents:
            raise TrialDeclarationError(f"trial participant {address} is not a scenario agent")
        values = configuration.configuration.values
        model = next(
            (getattr(item.value, "value", None) for item in values if item.target_id == "model"), None
        )
        assets = tuple(
            item.control_context_selection.declaration_ref.removeprefix("control_context_assets.")
            for item in values
            if item.control_context_selection is not None
        )
        if not isinstance(model, str) or not model or not assets:
            raise TrialDeclarationError(f"trial participant {address} has no configured model or prompt")
        participants.append(
            DeclaredParticipant(
                agent=name, role=_declared_role(scenario, name), model=model, context_assets=assets
            )
        )
    return tuple(participants)


def _declared_model(scenario: Scenario, agent_name: str) -> str | None:
    """Read the one model on the agent's interactive-access nodes."""
    agent = scenario.agents[agent_name]
    nodes = dict.fromkeys(access.target_ref for access in agent.interactive_access.values())
    models = []
    for node_name in nodes:
        node = scenario.nodes.get(node_name)
        runtime = getattr(node, "runtime", None)
        for component in getattr(runtime, "software_components", None) or ():
            if component.model is not None:
                models.append(component.model)
    if not models:
        return None
    if len(models) != 1:
        raise TrialDeclarationError(
            f"trial participant agents.{agent_name} has more than one declared model"
        )
    if "${" in models[0]:
        raise TrialDeclarationError(
            f"trial participant agents.{agent_name} model is not concrete"
        )
    return models[0]


def _declared_role(scenario: Scenario, agent_name: str) -> str:
    """Require one concrete exercise role for the tool profile."""
    from raes.entities import flatten_entities

    role = scenario.agents[agent_name].effective_role(flatten_entities(scenario.entities))
    if not isinstance(role, str) or not role or "${" in role:
        raise TrialDeclarationError(
            f"trial participant agents.{agent_name} has no concrete role"
        )
    return role
