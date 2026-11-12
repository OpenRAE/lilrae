"""The trial deadline replaces the 600-second cap on the agency runtime (#1700)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta


def test_trial_deadline_replaces_standalone_600_second_selection_cap(tmp_path):
    from aptl.backends.raes_participant_apparatus import project_participant_turn
    from aptl.backends.raes_participant_provider import (
        ParticipantDecisionSolicitation,
        candidate_payloads,
    )
    from aptl.core.trial_participants import TrialParticipantBounds
    from tests.techvault.test_bounded_participant_runtime import (
        _apparatus,
        _CountingProvider,
        _participant_for,
        _runtime,
    )

    control, model, _, _ = _runtime(tmp_path)
    behavior = "participant.behavior-specification.complete-normal-session"
    participant = _participant_for(model, behavior)
    control.initialize_participant_episode(participant, episode_id="trial-selection")
    runtime = control._target.participant_runtime
    started = datetime.now(UTC) - timedelta(seconds=601)
    current = [datetime.now(UTC)]
    runtime.autonomous_execution.install_before_dispatch(
        (),
        trial_bounds=TrialParticipantBounds(
            started, started + timedelta(seconds=900), 50, (), lambda: current[0]
        ),
    )
    episodes = dict(control.snapshot.participant_episode_results)
    episodes[participant] = {
        **episodes[participant],
        "initialized_at": started.isoformat(),
    }
    snapshot = replace(control.snapshot, participant_episode_results=episodes)
    turn = project_participant_turn(
        runtime_model=model,
        runtime_snapshot=snapshot,
        behavior_specification_address=behavior,
        apparatus=_apparatus(participant),
    )
    solicitation = ParticipantDecisionSolicitation(
        participant,
        "trial-selection",
        "participant-selection-solicitations.trial-1",
        turn.surface.participant_view.model_dump(mode="json"),
        turn.rendered_context,
        turn.observation_history,
        candidate_payloads(turn.candidates),
    )
    provider = _CountingProvider()
    runtime.bind_selection_provider(provider)
    assert runtime.solicit_selection(solicitation, snapshot).success
    current[0] = started + timedelta(seconds=900)
    next_turn = replace(
        solicitation, solicitation_id="participant-selection-solicitations.trial-2"
    )
    assert not runtime.solicit_selection(next_turn, snapshot).success
    assert provider.calls == 1
