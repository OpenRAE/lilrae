"""Sealed trial selections and retained deadlines reach fresh native executors."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.participant_trial_fixture import compiled_participants
from aptl.core.trial_participants import PendingTrialParticipant


@pytest.fixture
def admitted_participants(tmp_path):
    from tests.participant_trial_fixture import realized_participants

    compiled, compilation, owner = compiled_participants(
        tmp_path, executable=Path("/bin/true")
    )
    return lambda index=0: realized_participants(
        compiled, compilation, owner, index=index
    )


def prepare(values, **changes):
    from aptl.workbench.trial_participants import prepare_trial_participants

    request, attempt, scenario, experiment, owner, contents, now = values
    args = dict(
        request=request,
        attempt=attempt,
        scenario=scenario,
        experiment=experiment,
        owners={address: owner for address in contents},
        contents=contents,
        now=now,
    )
    args.update(changes)
    return prepare_trial_participants(**args)


def test_preparation_uses_sealed_configuration_for_both_roles(admitted_participants):
    values = admitted_participants()
    prepared = prepare(values)
    assert set(prepared.requests) == {"agents.operator", "agents.reviewer"}
    for address, request in prepared.requests.items():
        assert request.configuration_result in values[0].participant_configurations
        assert request.prompt.encode() == values[5][address]["brief"]
    assert prepared.logical_step_limit == values[3].run_plan.episode_control.max_steps
    assert all(
        r.profile.assistant_turn_limit.value == 1 for r in prepared.requests.values()
    )
    assert prepared.deadline == datetime.fromisoformat(values[1].deadline)


def test_preparation_keeps_changed_consecutive_models_and_prompts_independent(
    admitted_participants,
):
    first = prepare(admitted_participants(0))
    variants = [prepare(admitted_participants(i)) for i in (1, 2, 4, 8, 16)]
    for address in first.requests:
        assert any(
            v.requests[address].profile.model != first.requests[address].profile.model
            for v in variants
        )
        assert any(
            v.requests[address].prompt != first.requests[address].prompt
            for v in variants
        )


@pytest.mark.parametrize(
    "change", ["owner", "content", "attempt", "experiment", "deadline"]
)
def test_preparation_refuses_missing_authority_or_stale_trial_inputs(
    admitted_participants, change
):
    values = admitted_participants()
    changes = {}
    if change == "owner":
        changes["owners"] = {}
    elif change == "content":
        changes["contents"] = {}
    elif change == "attempt":
        changes["attempt"] = values[1].model_copy(
            update={"execution_attempt_id": "peer-attempt"}
        )
    elif change == "experiment":
        changes["experiment"] = values[3].model_copy(update={"spec_version": "other"})
    else:
        changes["now"] = datetime.fromisoformat(values[1].deadline)
    with pytest.raises(ValueError):
        prepare(values, **changes)


def test_remaining_deadline_is_not_restarted_between_invocations(admitted_participants):
    values = admitted_participants()
    prepared = prepare(values, now=values[-1] + timedelta(seconds=7))
    assert (
        prepared.remaining_seconds(values[-1] + timedelta(seconds=11))
        == values[0].execution_controls.attempt_timeout_seconds - 11
    )
    with pytest.raises(ValueError):
        prepared.remaining_seconds(prepared.deadline)


def test_native_turn_limit_cannot_be_overridden(admitted_participants, tmp_path):
    from dataclasses import replace
    from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor
    from tests.opencode_fixture import synthetic_options
    from aptl.core.opencode import OpenRouterRoute

    prepared = prepare(admitted_participants())
    address, request = next(iter(prepared.requests.items()))
    options = synthetic_options(
        executable=Path("/bin/true"),
        work_root=tmp_path,
        request=request,
        request_binding=prepared.bindings[address],
        max_output_tokens=request.profile.output_limit.value,
    )
    options = replace(
        options,
        route=OpenRouterRoute(
            endpoint=request.profile.gateway_endpoint,
            serving_provider=request.profile.serving_provider,
        ),
    )
    for limit in (None, 2):
        with pytest.raises(ValueError, match="turn"):
            LilraeOpenCodeExecutor(
                options=replace(options, max_steps=limit),
                model=request.profile.model,
                prompt=request.prompt,
                timeout_seconds=30,
                configuration_result=request.configuration_result,
            )


def test_managed_trial_applies_models_prompts_turns_and_original_time_bound(
    tmp_path, admitted_participants
):
    from threading import Event
    from aptl.core.config import ProcessEnvironmentCredentialSource
    from aptl.workbench.trial_participants import managed_trial_participants
    from tests.opencode_fixture import synthetic_options
    from tests.test_lilrae_opencode import RecordingRunner
    from tests.test_opencode_native_history import native_database
    from aptl.workbench.process import AgentExecutionError

    values = admitted_participants()
    prepared = prepare(values)

    class Runner(RecordingRunner):
        def run(self, argv, **kwargs):
            native_database(
                kwargs["cwd"],
                prompt=kwargs["stdin"].decode(),
                model=argv[argv.index("--model") + 1].removeprefix("openrouter/"),
            )
            from tests.test_opencode_observation import synthetic_journal

            synthetic_journal(kwargs["cwd"])
            return super().run(argv, **kwargs)

    runners = {address: Runner() for address in prepared.requests}
    sources = {
        address: ProcessEnvironmentCredentialSource(
            kind="process-environment", variable="TEST_MODEL_SOURCE"
        )
        for address in runners
    }
    options = {
        address: synthetic_options(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            runner=runner,
            evidence_sink=lambda record: None,
        )
        for address, runner in runners.items()
    }
    current = [values[-1] + timedelta(seconds=7)]
    closed = []
    with managed_trial_participants(
        prepared,
        invocation_timeouts={address: 90 for address in prepared.requests},
        options=options,
        credential_sources=sources,
        source_environment={"TEST_MODEL_SOURCE": "synthetic-test-only"},
        clock=lambda: current[0],
        stop_and_drain=lambda: closed.append(True),
    ) as executors:
        current[0] += timedelta(seconds=4)
        for address, active in executors.items():
            assert active("action", Event()) == "done"
            argv, kwargs, config = runners[address].calls[0]
            assert prepared.requests[address].profile.model in argv
            assert kwargs["stdin"] == prepared.requests[address].prompt.encode()
            assert (
                kwargs["timeout_seconds"]
                == values[0].execution_controls.attempt_timeout_seconds - 11
            )
            assert config["agent"]["build"]["steps"] == 1
            assert prepared.logical_step_limit == 50
            assert active.last_evidence.participant_address == address
        current[0] = prepared.deadline
        for active in executors.values():
            with pytest.raises(AgentExecutionError, match="deadline"):
                active("expired", Event())
    assert closed == [True]
    for active in executors.values():
        with pytest.raises(AgentExecutionError, match="closed"):
            active("closed", Event())


@pytest.mark.parametrize("invocation_seconds", [90, 30, 3601])
def test_trial_application_reuses_pending_scope_and_closes_only_after_finish(
    admitted_participants, tmp_path, invocation_seconds
):
    from dataclasses import replace
    from aptl.workbench.trial_participants import ManagedTrialParticipantApplication
    from aptl.backends.lilrae_participant_execution import LilraeParticipantExecution
    from aptl.core.config import ProcessEnvironmentCredentialSource
    from tests.test_lilrae_concurrent_participants import bindings
    from tests.opencode_fixture import synthetic_options

    values = admitted_participants()
    prepared = prepare(values)
    templates = []

    for item, (address, request) in zip(
        bindings({"red": lambda *a: "", "blue": lambda *a: ""}),
        prepared.requests.items(),
        strict=True,
    ):
        name = address.removeprefix("agents.")
        selection = item.implementation_selection.model_copy(
            update={
                "participant_address": "participant.behavior." + name,
                "implementation_identity": request.manifest.identity,
                "manifest_ref": request.configuration_result.manifest_ref,
                "manifest_digest": request.configuration_result.manifest_digest,
                "configuration_digest": request.configuration_result.configuration_digest,
                "configuration_ref": "configuration:" + address,
            }
        )
        templates.append(
            replace(
                item,
                implementation_manifest=request.manifest,
                implementation_selection=selection,
                executor=PendingTrialParticipant(
                    request.configuration_result, invocation_seconds
                ),
                execution_binding=replace(
                    item.execution_binding,
                    participant_implementation_ref=selection.manifest_ref,
                    timeout_seconds=invocation_seconds,
                ),
            )
        )
    native = LilraeParticipantExecution(tuple(templates))
    application = ManagedTrialParticipantApplication(
        prepared=prepared,
        native=native,
        options={
            a: synthetic_options(
                executable=Path("/bin/true"),
                work_root=tmp_path,
                evidence_sink=lambda record: None,
            )
            for a in prepared.requests
        },
        credential_sources={
            a: ProcessEnvironmentCredentialSource(
                kind="process-environment", variable="TEST_MODEL_SOURCE"
            )
            for a in prepared.requests
        },
        source_environment={"TEST_MODEL_SOURCE": "synthetic-test-only"},
        clock=lambda: values[-1],
    )
    if invocation_seconds > 3600:
        with pytest.raises(ValueError, match="invocation timeout"):
            application.admit(values[0])
        assert application._state == "new"
        assert not list(tmp_path.glob("lilrae-participant-*"))
        return
    application.admit(values[0])
    application.configure(values[0])
    first = tuple(b.executor for b in native.bindings)
    assert all(
        e.timeout_seconds == pytest.approx(invocation_seconds, abs=1) for e in first
    )
    assert native.trial_bounds.deadline == prepared.deadline
    assert native.trial_bounds.logical_step_limit == prepared.logical_step_limit
    application.configure(values[0])
    assert tuple(b.executor for b in native.bindings) == first
    assert all(
        e.configuration_result in values[0].participant_configurations for e in first
    )
    application.finish(values[0])
    from threading import Event
    from aptl.workbench.process import AgentExecutionError

    for executor in first:
        with pytest.raises(AgentExecutionError, match="closed"):
            executor("closed", Event())
    application.configure(
        values[0]
    )  # Repeat terminal delivery must not reopen a lease.
    assert tuple(b.executor for b in native.bindings) == first


def test_trial_refuses_unavailable_native_turn_semantics(tmp_path):
    from tests.participant_trial_fixture import realized_participants

    compiled, compilation, owner = compiled_participants(
        tmp_path, fixed=True, executable=Path("/bin/true"), assistant_turn_limit=None
    )
    values = realized_participants(compiled, compilation, owner)
    with pytest.raises(ValueError, match="assistant turn limit is unavailable"):
        prepare(values)


def test_unconfigured_native_offer_cannot_dispatch(admitted_participants):
    from threading import Event
    from aptl.workbench.process import AgentExecutionError

    request = next(iter(prepare(admitted_participants()).requests.values()))
    executor = PendingTrialParticipant(request.configuration_result, 90)
    with pytest.raises(AgentExecutionError, match="not been configured"):
        executor("action", Event())


def test_native_configuration_cannot_change_admitted_action_authority():
    from dataclasses import replace
    from aptl.backends.lilrae_participant_execution import LilraeParticipantExecution
    from tests.test_lilrae_concurrent_participants import bindings

    installed = bindings({"red": lambda *args: "", "blue": lambda *args: ""})
    native = LilraeParticipantExecution(installed)
    changed = replace(
        installed[0],
        execution_binding=replace(installed[0].execution_binding, timeout_seconds=31),
    )
    with pytest.raises(ValueError, match="cannot be reconfigured"):
        native.install_before_dispatch((changed, installed[1]))
    native.cancel()
    with pytest.raises(ValueError, match="cannot be reconfigured"):
        native.install_before_dispatch(installed)


def test_published_trial_request_requires_installed_application(admitted_participants):
    from unittest.mock import Mock
    from aptl.backends.trial_serving import LilraeTrialUnit

    request = admitted_participants()[0]
    runtime, cleanup, placement, reporting = (Mock() for _ in range(4))
    unit = LilraeTrialUnit(runtime, cleanup, placement, "unused", reporting)
    with pytest.raises(ValueError, match="participant-application-required"):
        unit.execute_trial(request)
    runtime.execute_trial.assert_not_called()
    cleanup.admit.assert_not_called()


def test_compiler_manifest_reference_projection_refuses_arbitrary_aliases(
    admitted_participants,
):
    from dataclasses import replace
    from tests.participant_runtime_trial_fixture import native_bindings

    values = admitted_participants()
    installed = native_bindings(
        values[0].participant_configurations, values[4].manifest
    )
    item = installed[0]
    alias = "participant-implementation-manifests.peer"
    with pytest.raises(ValueError, match="manifest reference"):
        replace(
            item,
            implementation_selection=item.implementation_selection.model_copy(
                update={"manifest_ref": alias}
            ),
            execution_binding=replace(
                item.execution_binding, participant_implementation_ref=alias
            ),
        )


def test_trial_requires_evidence_owner_before_credential_acquisition(
    admitted_participants, tmp_path
):
    from aptl.core.config import ProcessEnvironmentCredentialSource
    from aptl.workbench.trial_participants import managed_trial_participants
    from tests.opencode_fixture import synthetic_options

    prepared = prepare(admitted_participants())
    with pytest.raises(ValueError, match="evidence sink"):
        with managed_trial_participants(
            prepared,
            invocation_timeouts={address: 90 for address in prepared.requests},
            options={
                a: synthetic_options(executable=Path("/bin/true"), work_root=tmp_path)
                for a in prepared.requests
            },
            credential_sources={
                a: ProcessEnvironmentCredentialSource(
                    kind="process-environment", variable="MISSING_SOURCE"
                )
                for a in prepared.requests
            },
            source_environment={},
            stop_and_drain=lambda: None,
            clock=lambda: prepared.started_at,
        ):
            pytest.fail("missing evidence owner was admitted")
