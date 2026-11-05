"""Sealed configurations execute through the existing production trial unit."""

import pytest

from aptl.workbench.lilrae_opencode import OpenCodeOptions
from tests.test_opencode_transport import opencode_binary as opencode_binary, provider

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("fixed", [True, False])
def test_trial_serving_executes_sealed_roles_through_shared_runtime(
    tmp_path, opencode_binary, fixed
):
    from aptl.backends.trial_serving import (
        LilraeTrialUnit,
        DockerTrialPlacement,
        TrialOutcomeReporting,
    )
    from aptl.core.config import ProcessEnvironmentCredentialSource
    from aptl.workbench.trial_participants import (
        prepare_trial_participants,
        ManagedTrialParticipantApplication,
    )
    from raes_runtime import RuntimeControlPlane
    from raes_processor.trial_realization import (
        TrialRealizationInputs,
        realize_admitted_trial_entry,
    )
    from tests.participant_trial_fixture import (
        compiled_participants,
        realized_participants,
    )
    from tests.participant_runtime_trial_fixture import native_bindings
    from tests.cleanup_runtime_fixture import Services, target_for
    from tests.test_trial_serving import SchedulerDelivery, PlacementBackend, finish
    from tests.trial_readiness_fixture import readiness_for
    from aptl.backends.trial_services import ReadinessTrialServices
    from aptl.core.runstore import LocalRunStore
    from aptl.core.correlation.clock import FixedClockProvider

    with provider() as (endpoint, requests):
        compiled, compilation, owner = compiled_participants(
            tmp_path,
            fixed=fixed,
            executable=opencode_binary,
            endpoint=endpoint,
            native=True,
        )
        inputs = TrialRealizationInputs(
            plan=compiled.plan,
            family=compilation.family,
            experiment=compilation.experiment,
            task=compilation.task,
            capture_specs=dict(compilation.capture_specs),
            apparatus_manifests=dict(compilation.apparatus_manifests),
            realization_envelope=compilation.realization_envelope,
            backend_key=next(
                k for k in compilation.apparatus_manifests if k[0] == "backend"
            ),
            participant_manifests=dict(compilation.participant_manifests),
        )
        entries = list(compiled.plan.entries.values())

        def selections(entry):
            return {
                r.participant_address: tuple(
                    v.value.value
                    for v in r.configuration.values
                    if v.target_id in {"model", "context.brief"}
                )
                for r in entry.participant_configurations
            }

        indices = [0]
        if not fixed:
            baseline = selections(entries[0])
            indices.append(
                next(
                    i
                    for i, e in enumerate(entries)
                    if all(
                        all(x != y for x, y in zip(baseline[a], values))
                        for a, values in selections(e).items()
                    )
                )
            )
        previous = None
        for index in indices:
            values = realized_participants(compiled, compilation, owner, index=index)
            entry = list(compiled.plan.entries.values())[index]
            installed = native_bindings(
                entry.participant_configurations,
                owner.manifest,
                timeout_seconds=30 if fixed else 90,
            )
            target = target_for(
                realize_admitted_trial_entry(
                    inputs=inputs, plan_entry_id=entry.plan_entry_id
                ).execution_plan.manifest,
                native_bindings=installed,
            )
            root = tmp_path / str(index)
            root.mkdir(mode=0o700)
            services = Services(root)
            records = []
            readiness = readiness_for(
                inputs,
                target,
                LocalRunStore(root / "runs"),
                FixedClockProvider(measurement_time="2026-11-01T10:00:00Z"),
                root,
                entry_index=index,
            )
            with RuntimeControlPlane(target) as runtime:
                experiment_id = runtime.admit_experiment(
                    inputs, services=ReadinessTrialServices(services, readiness)
                )
                delivery = SchedulerDelivery(runtime, experiment_id, index)
                unit, request = delivery.unit, delivery.request
                prepared = prepare_trial_participants(
                    request=request,
                    attempt=unit.attempt,
                    scenario=unit.realization.instantiated,
                    experiment=compilation.experiment,
                    owners={a: owner for a in values[5]},
                    contents=values[5],
                )
                sources = {
                    a: ProcessEnvironmentCredentialSource(
                        kind="process-environment", variable="TEST_MODEL_SOURCE"
                    )
                    for a in prepared.requests
                }
                application = ManagedTrialParticipantApplication(
                    prepared=prepared,
                    native=target.participant_runtime.autonomous_execution,
                    options={
                        a: OpenCodeOptions(
                            executable=opencode_binary,
                            work_root=root,
                            evidence_sink=records.append,
                        )
                        for a in sources
                    },
                    credential_sources=sources,
                    source_environment={"TEST_MODEL_SOURCE": "private-test-credential"},
                )
                state = root / "placement"
                state.mkdir()
                placement = DockerTrialPlacement(PlacementBackend(root), state)
                handler = LilraeTrialUnit(
                    unit,
                    services.cleanups[request.execution_attempt_id],
                    placement,
                    unit.run._target_scope,
                    TrialOutcomeReporting(
                        runtime, experiment_id, lambda request, result: {}
                    ),
                    participants=application,
                    readiness=readiness,
                )
                try:
                    finish(handler, request)
                except Exception as error:
                    for reference in readiness.references:
                        observation = readiness.store.read_run_json(
                            request.run_id, reference
                        )
                        error.add_note(
                            "Readiness checks: "
                            + ", ".join(
                                check["code"] for check in observation["checks"]
                            )
                        )
                    raise
            assert len(records) == 2
            assert {r.participant_address for r in records} == set(prepared.requests)
            for record in records:
                assert record.status == "succeeded"
                record.request_observation.require_fields(
                    frozenset(
                        {
                            "outgoing_controls",
                            "provider_generation_id",
                            "input_tokens",
                            "output_tokens",
                        }
                    )
                )
                assert record.trial_scope.run_id == request.run_id
                assert (
                    record.trial_scope.execution_attempt_id
                    == request.execution_attempt_id
                )
            current = {
                (r.participant_address, r.requested_model, r.prompt_sha256)
                for r in records
            }
            if previous is not None:
                assert all(
                    not any(a == b and (m == n or p == q) for b, n, q in previous)
                    for a, m, p in current
                )
            previous = current
            assert application._state == "finished"
            assert "private-test-credential" not in repr(records)
            assert not list(root.glob("lilrae-participant-*"))
