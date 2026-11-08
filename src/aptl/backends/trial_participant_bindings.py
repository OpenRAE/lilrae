"""Installed participant bindings for one admitted family trial.

A pack's installed adapter publishes, under the ``aptl.trial_participants``
entry point named by its pack id, a callable that returns the RAES autonomous
participant bindings for the trial's sealed configurations. LilRAE installs
them in the trial's runtime target, so RAES governs each participant action.
"""

from __future__ import annotations

from importlib import metadata

from aptl.backends.lilrae_participant_execution import LilraeParticipantBinding
from aptl.core.scenario_bundle import ScenarioBundle

ENTRY_POINT_GROUP = "aptl.trial_participants"


def installed_participant_bindings(bundle: ScenarioBundle) -> tuple[LilraeParticipantBinding, ...]:
    """Return the pack's bindings for the bundle's trial, or none without a provider."""
    trial, identity = bundle.trial, bundle.pack_identity
    if trial is None or identity is None:
        return ()
    selected = [
        item for item in metadata.entry_points(group=ENTRY_POINT_GROUP) if item.name == identity.pack_id
    ]
    if not selected:
        return ()
    if len(selected) != 1:
        raise ValueError("trial-participant-provider-ambiguous")
    provider = selected[0].load()
    bindings = tuple(provider(bundle.root, trial.scenario, trial.participant_configuration_results))
    if not all(isinstance(item, LilraeParticipantBinding) for item in bindings):
        raise ValueError("trial-participant-provider-invalid")
    return bindings


__all__ = ["ENTRY_POINT_GROUP", "installed_participant_bindings"]
