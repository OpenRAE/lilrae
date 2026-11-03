"""Selected trial horizons stop actual native dispatch through the RAE scheduler."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tests.lilrae_concurrent_fixture import scenario
from tests.test_lilrae_concurrent_participants import bindings, manager_for


def test_consecutive_trial_horizons_stop_each_role_at_its_selected_step():
    from aptl.core.trial_participants import TrialParticipantBounds

    now = datetime.now(UTC)
    for steps in (1, 2):
        calls = {"red": [], "blue": []}

        def executor(role):
            def invoke(action, cancellation):
                calls[role].append(action)
                return role + " observation"

            return invoke

        installed = tuple(
            replace(
                item,
                execution_binding=replace(
                    item.execution_binding, max_action_attempts=3
                ),
            )
            for item in bindings({r: executor(r) for r in calls})
        )
        manager, runtime = manager_for(installed)
        runtime.autonomous_execution.install_before_dispatch(
            installed,
            trial_bounds=TrialParticipantBounds(
                started_at=now,
                deadline=now + timedelta(seconds=30),
                logical_step_limit=steps,
                clock_steps=(("time.clock.trial", "time.policy.trial", 1),),
                clock=lambda: now,
            ),
        )
        with manager:
            result = manager.apply(manager.plan(scenario(attempts=3)))
            assert result.success, result.diagnostics
            for _ in range(2):
                advanced = manager.advance_time("time.clock.trial", ticks=1)
                assert advanced.success, advanced.diagnostics
            assert {role: len(actions) for role, actions in calls.items()} == {
                "red": steps,
                "blue": steps,
            }
            assert "logical step budget" in str(
                {
                    k: list(v)
                    for k, v in manager.snapshot.participant_behavior_history.items()
                }
            )


def test_consecutive_trial_deadlines_stop_dispatch_at_the_original_bound():
    from aptl.core.trial_participants import TrialParticipantBounds

    for seconds in (2, 4):
        started = datetime.now(UTC)
        current = [started]
        calls = []

        def invoke(action, cancellation):
            calls.append(action)
            current[0] += timedelta(seconds=1)
            return "observation"

        installed = tuple(
            replace(
                item,
                execution_binding=replace(
                    item.execution_binding, max_action_attempts=6
                ),
            )
            for item in bindings({"red": invoke})
        )
        # The scenario has two roles. The peer completes without moving the test clock.
        installed += tuple(
            replace(
                item,
                execution_binding=replace(
                    item.execution_binding, max_action_attempts=6
                ),
            )
            for item in bindings({"blue": lambda *args: "peer observation"})
        )
        manager, runtime = manager_for(installed)
        runtime.autonomous_execution.install_before_dispatch(
            installed,
            trial_bounds=TrialParticipantBounds(
                started,
                started + timedelta(seconds=seconds),
                50,
                (("time.clock.trial", "time.policy.trial", 1),),
                lambda: current[0],
            ),
        )
        with manager:
            result = manager.apply(manager.plan(scenario(attempts=6)))
            assert result.success, result.diagnostics
            for _ in range(5):
                advanced = manager.advance_time("time.clock.trial", ticks=1)
                assert advanced.success, advanced.diagnostics
            assert len(calls) == seconds
            assert "attempt deadline" in str(
                {
                    k: list(v)
                    for k, v in manager.snapshot.participant_behavior_history.items()
                }
            )


@pytest.mark.parametrize(
    "clock_steps", [(), (("time.clock.other", "time.policy.other", 1),)]
)
def test_unqualified_logical_clock_refuses_native_work(clock_steps):
    from aptl.core.trial_participants import TrialParticipantBounds

    now = datetime.now(UTC)
    calls = []
    installed = bindings(
        {r: lambda *args: calls.append(args) or "unexpected" for r in ("red", "blue")}
    )
    manager, runtime = manager_for(installed)
    runtime.autonomous_execution.install_before_dispatch(
        installed,
        trial_bounds=TrialParticipantBounds(
            now, now + timedelta(seconds=30), 50, clock_steps, lambda: now
        ),
    )
    with manager:
        result = manager.apply(manager.plan(scenario()))
        assert result.success, result.diagnostics
        assert calls == []


def test_running_process_uses_remaining_trial_time_and_is_reaped(tmp_path):
    from pathlib import Path
    from threading import Event
    from time import monotonic
    import sys

    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from aptl.workbench.process import BoundedProcessError, REASON_TIMEOUT
    from tests.opencode_fixture import synthetic_options

    executable = tmp_path / "participant"
    started_file = tmp_path / "started"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import pathlib,time\n"
        f"pathlib.Path({str(started_file)!r}).write_text('started')\n"
        "time.sleep(30)\n"
    )
    executable.chmod(0o700)
    for remaining in (0.5, 1.0):
        started_file.unlink(missing_ok=True)
        deadline = datetime.now(UTC) + timedelta(seconds=remaining)
        executor = LilraeOpenCodeExecutor(
            options=synthetic_options(
                executable=Path(executable), work_root=tmp_path, deadline=deadline
            ),
            model="openrouter/model",
            prompt="bounded trial",
            timeout_seconds=30,
        )
        started = monotonic()
        failure_cancellation = Event()
        with pytest.raises(BoundedProcessError) as failure:
            executor("bounded-action", failure_cancellation)
        elapsed = monotonic() - started
        assert started_file.exists()
        assert remaining * 0.8 <= elapsed < remaining + 3
        assert failure.value.reason == REASON_TIMEOUT
        assert failure.value.cleanup.residual == ()
        assert not list(tmp_path.glob("lilrae-participant-*"))


def test_trial_deadline_replaces_standalone_600_second_selection_cap(tmp_path):
    from aptl.core.trial_participants import TrialParticipantBounds
    from aptl.backends.raes_participant_apparatus import project_participant_turn
    from aptl.backends.raes_participant_provider import (
        ParticipantDecisionSolicitation,
        candidate_payloads,
    )
    from tests.test_bounded_participant_runtime import (
        _runtime,
        _participant_for,
        _apparatus,
        _CountingProvider,
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
