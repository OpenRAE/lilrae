"""Small real RAE runtime for the trial supervisor's focused tests."""

from dataclasses import replace
import json
import yaml

from raes import parse_sdl
from aptl.backends.raes_runtime import AptlRuntimeManager
from aptl.workbench.trial_run import NativeTrialRelease, run_declared_trial
from tests.lilrae_concurrent_fixture import scenario
from tests.test_lilrae_concurrent_participants import bindings, target_for


def run_native_trial(trial, **options):
    participants = trial.participants
    names = {item.role: item.agent for item in participants}
    text = json.dumps(scenario().model_dump(mode="json", exclude_unset=True))
    for role, name in names.items():
        text = text.replace(json.dumps(role), json.dumps(name))
    payload = json.loads(text)
    for role, name in names.items():
        payload["entities"][name]["role"] = role
    payload["behavior_specifications"]["duel"]["participant_role_refs"] = []
    payload["behavior_specifications"]["duel"]["autonomous_execution"][
        "failure_policy"
    ] = "stop"
    payload["temporal_constraints"]["turn"]["start"]["tick"] = 1
    authored = parse_sdl(yaml.safe_dump(payload))
    red = names["red"]
    installed = tuple(
        replace(
            binding,
            observation_boundary_address="participant.observation-boundary." + red,
            execution_binding=replace(
                binding.execution_binding,
                action_contract_address="participant.action-contract." + red,
            ),
        )
        for binding in bindings(
            {item.agent: lambda *args: "unreleased" for item in participants}
        )
    )
    target, participant_runtime = target_for(installed)
    native = participant_runtime.autonomous_execution
    with AptlRuntimeManager(target, run_scope="run:" + trial.attempt.run_id) as runtime:
        plan = runtime.plan(authored)
        applied = runtime.apply(plan)
        assert applied.success, applied.diagnostics
        policy = plan.model.behavior_specifications[
            "participant.behavior-specification.duel"
        ].autonomous_execution
        return run_declared_trial(
            replace(trial, episode_seconds=trial.episode_seconds or 60),
            release=NativeTrialRelease(runtime, native, policy),
            **options,
        )
