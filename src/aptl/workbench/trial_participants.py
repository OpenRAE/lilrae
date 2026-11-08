"""Trusted entry assembly for participant requests from one sealed RAE trial."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import MappingProxyType

from raes import canonical_instantiated_sdl_digest
from raes.scenario import InstantiatedScenario
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.addressing import render_compiled_address
from raes_contracts.contracts import ExperimentSpecModel
from raes_contracts.trial_unit import TrialUnitRequest
from raes_runtime.runtime_trial_decisions import TrialAttemptDecision
from raes_contracts.timestamps import utc_now

from aptl.core.config import ProcessEnvironmentCredentialSource
from aptl.core.trial_participants import TrialParticipantBounds
from aptl.core._credential_sources import AttachedServiceAccountSource
from aptl.core.opencode import OpenCodeTrialScope, OpenRouterRoute, ParticipantRoute, VertexRoute
from aptl.core.participant_requests import (
    ParticipantRequest,
    ParticipantRequestBinding,
    ParticipantRequestOwner,
)
from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor, OpenCodeOptions
from aptl.workbench.opencode_bootstrap import (
    OpenCodeParticipantRequest,
    managed_opencode_executor,
)
from aptl.backends.lilrae_participant_execution import LilraeParticipantExecution


@dataclass(frozen=True)
class PreparedParticipantTrial:
    """Validated requests with the original attempt bound and trusted bindings."""

    run_id: str
    attempt_id: str
    plan_entry_id: str
    started_at: datetime
    deadline: datetime
    logical_step_limit: int
    clock_steps: tuple[tuple[str, str, int], ...]
    requests: Mapping[str, ParticipantRequest]
    bindings: Mapping[str, ParticipantRequestBinding]
    trial_request: TrialUnitRequest = field(repr=False)

    def __post_init__(self) -> None:
        self.runtime_bounds()

    def runtime_bounds(
        self, clock: Callable[[], datetime] = utc_now
    ) -> TrialParticipantBounds:
        return TrialParticipantBounds(
            self.started_at,
            self.deadline,
            self.logical_step_limit,
            self.clock_steps,
            clock,
        )

    def remaining_seconds(self, now: datetime) -> float:
        """Use the retained bound rather than assigning another invocation budget."""
        remaining = (self.deadline - now).total_seconds()
        if now < self.started_at or remaining <= 0:
            raise ValueError("participant attempt deadline is unavailable")
        return remaining


def _validate_scope(
    request: TrialUnitRequest,
    attempt: TrialAttemptDecision,
    scenario: InstantiatedScenario,
    experiment: ExperimentSpecModel,
) -> None:
    """Join retained attempt and instantiated provenance to the pinned authoring input."""
    reference = request.plan.input_refs.authoring_input_ref
    provenance = scenario.instantiation_provenance.trial
    entry = request.plan.entries[request.plan_entry_id]
    if (
        reference.ref_id != experiment.spec_id
        or reference.ref_version != experiment.spec_version
        or reference.ref_digest != canonical_contract_digest(experiment)
        or canonical_instantiated_sdl_digest(scenario).value
        != request.instantiated_sdl_digest
        or provenance is None
        or (
            provenance.plan_id,
            provenance.plan_digest,
            provenance.plan_entry_id,
            provenance.entry_digest,
            provenance.run_id,
        )
        != (
            request.plan.plan_id,
            request.plan.plan_digest,
            request.plan_entry_id,
            entry.entry_digest,
            request.run_id,
        )
        or (attempt.plan_entry_id, attempt.run_id, attempt.execution_attempt_id)
        != (request.plan_entry_id, request.run_id, request.execution_attempt_id)
    ):
        raise ValueError("participant trial authority is inconsistent")


def prepare_trial_participants(
    *,
    request: TrialUnitRequest,
    attempt: TrialAttemptDecision,
    scenario: InstantiatedScenario,
    experiment: ExperimentSpecModel,
    owners: Mapping[str, ParticipantRequestOwner],
    contents: Mapping[str, Mapping[str, bytes]],
    now: datetime | None = None,
) -> PreparedParticipantTrial:
    """Verify all roles before credentials, native work or artifact disclosure.

    Content and the typed authoring input come from approved artifact owners.
    This function neither resolves locators nor allocates a trial or attempt.
    """
    request = replace(request)
    attempt = TrialAttemptDecision.model_validate_json(attempt.model_dump_json())
    experiment = ExperimentSpecModel.model_validate_json(experiment.model_dump_json())
    _validate_scope(request, attempt, scenario, experiment)
    configurations = {
        item.participant_address: item for item in request.participant_configurations
    }
    if (
        not configurations
        or len(configurations) != len(request.participant_configurations)
        or set(configurations) != set(owners)
        or set(configurations) != set(contents)
    ):
        raise ValueError("participant trial configuration set is incomplete")
    started, deadline, steps = _execution_controls(request, attempt, experiment)
    requests = {}
    bindings = {}
    for address, configuration in configurations.items():
        owner = owners[address].for_scenario(scenario)
        prepared = owner.prepare_request(
            configuration, participant_address=address, contents=contents[address]
        )
        if prepared.provider != "opencode":
            raise ValueError("participant trial requires managed OpenCode")
        if prepared.profile.assistant_turn_limit is None:
            raise ValueError("participant native assistant turn limit is unavailable")
        requests[address] = prepared
        bindings[address] = ParticipantRequestBinding(owner, address)
    result = PreparedParticipantTrial(
        request.run_id,
        request.execution_attempt_id,
        request.plan_entry_id,
        started,
        deadline,
        steps,
        _clock_steps(scenario),
        MappingProxyType(requests),
        MappingProxyType(bindings),
        request,
    )
    result.remaining_seconds(now or utc_now())
    return result


def _execution_controls(
    request: TrialUnitRequest,
    attempt: TrialAttemptDecision,
    experiment: ExperimentSpecModel,
) -> tuple[datetime, datetime, int]:
    """Validate the pinned logical horizon and the original attempt interval."""
    steps = experiment.run_plan.episode_control.max_steps
    started = datetime.fromisoformat(attempt.started_at)
    deadline = datetime.fromisoformat(attempt.deadline)
    duration = (deadline - started).total_seconds()
    if (
        steps is None
        or not 1 <= steps <= 10_000
        or not 0
        < duration
        <= min(3600, request.execution_controls.attempt_timeout_seconds)
    ):
        raise ValueError("participant trial execution controls are unsupported")
    return started, deadline, steps


def _clock_steps(scenario: InstantiatedScenario) -> tuple[tuple[str, str, int], ...]:
    """Project only explicit, non-resettable stepped progression policies."""
    return tuple(
        (
            render_compiled_address("time", "clock", policy.clock_ref),
            render_compiled_address("time", "policy", name),
            policy.step_ticks,
        )
        for name, policy in scenario.time_progression_policies.items()
        if policy.advancement_mode == "stepped"
        and policy.reset_behavior == "unsupported"
        and policy.replay_behavior == "unsupported"
    )


ParticipantCredentialSource = ProcessEnvironmentCredentialSource | AttachedServiceAccountSource


def participant_route(profile, source: ParticipantCredentialSource) -> ParticipantRoute:
    """Select the request profile's route; Vertex AI needs the attached identity."""
    if profile.gateway == VertexRoute.provider_id:
        if not isinstance(source, AttachedServiceAccountSource):
            raise ValueError("a Vertex AI participant requires the attached service account")
        return VertexRoute(source.project)
    if not isinstance(source, ProcessEnvironmentCredentialSource):
        raise ValueError("an OpenRouter participant requires a process environment credential")
    return OpenRouterRoute(
        endpoint=profile.gateway_endpoint, serving_provider=profile.serving_provider
    )


def _validate_installed_inputs(
    prepared: PreparedParticipantTrial,
    options: Mapping[str, OpenCodeOptions],
    credential_sources: Mapping[str, ParticipantCredentialSource],
    invocation_timeouts: Mapping[str, float],
) -> None:
    """Validate every role before placement, credentials or provider requests."""
    addresses = set(prepared.requests)
    if (
        addresses != set(options)
        or addresses != set(credential_sources)
        or addresses != set(invocation_timeouts)
    ):
        raise ValueError("participant installed input set is incomplete")
    for address in addresses:
        timeout = invocation_timeouts[address]
        if type(timeout) not in (int, float) or not 0 < timeout <= 3600:
            raise ValueError("participant invocation timeout is unsupported")
        prepared.bindings[address].validate(prepared.requests[address])
        if not callable(options[address].evidence_sink):
            raise ValueError("participant trial requires its configured evidence sink")
        if options[address].environment or options[address].request is not None:
            raise ValueError(
                "participant installed inputs contain ambient configuration"
            )


@contextmanager
def managed_trial_participants(
    prepared: PreparedParticipantTrial,
    *,
    invocation_timeouts: Mapping[str, float],
    options: Mapping[str, OpenCodeOptions],
    credential_sources: Mapping[str, ParticipantCredentialSource],
    source_environment: Mapping[str, str],
    stop_and_drain: Callable[[], None],
    clock: Callable[[], datetime] = utc_now,
) -> Iterator[Mapping[str, LilraeOpenCodeExecutor]]:
    """Acquire fresh per-role executors, then drain before destroying their leases."""
    invocation_timeouts = dict(invocation_timeouts)
    _validate_installed_inputs(
        prepared, options, credential_sources, invocation_timeouts
    )
    with ExitStack() as stack:
        executors = {}
        try:
            for address, request in prepared.requests.items():
                prepared.remaining_seconds(clock())
                selected = replace(
                    options[address],
                    request=request,
                    request_binding=prepared.bindings[address],
                    route=participant_route(request.profile, credential_sources[address]),
                    max_output_tokens=request.profile.output_limit.value,
                    max_steps=request.profile.assistant_turn_limit.value,
                    deadline=prepared.deadline,
                    clock=clock,
                    trial_scope=OpenCodeTrialScope(
                        prepared.run_id, prepared.attempt_id, prepared.plan_entry_id
                    ),
                    native_history_required=True,
                    request_observation_required=True,
                )
                active, _ = stack.enter_context(
                    managed_opencode_executor(
                        options=selected,
                        request=OpenCodeParticipantRequest(
                            request.configuration_result,
                            request.manifest,
                            request.prompt,
                            request.prompt_ref,
                            frozenset({request.profile.model}),
                        ),
                        run_id=prepared.run_id,
                        credential_source=credential_sources[address],
                        source_environment=source_environment,
                        timeout_seconds=invocation_timeouts[address],
                    )
                )
                executors[address] = active
            yield MappingProxyType(executors)
        finally:
            stop_and_drain()


@dataclass
class ManagedTrialParticipantApplication:
    """Install exact executors at LilraeTrialUnit's existing lifecycle boundary.

    The native runtime must already contain the admitted binding offers. Their
    executor placeholders carry the sealed configuration but cannot dispatch.
    This owner replaces only executors, retaining all admitted action authority.
    """

    prepared: PreparedParticipantTrial
    native: LilraeParticipantExecution
    options: Mapping[str, OpenCodeOptions]
    credential_sources: Mapping[str, ProcessEnvironmentCredentialSource]
    source_environment: Mapping[str, str] = field(repr=False)
    clock: Callable[[], datetime] = utc_now
    _stack: ExitStack = field(default_factory=ExitStack, init=False, repr=False)
    _state: str = field(default="new", init=False)

    def admit(self, request: TrialUnitRequest) -> None:
        """Refuse a different request before placement, credentials or processes."""
        prepared = self.prepared
        if replace(request) != prepared.trial_request or tuple(
            request.participant_configurations
        ) != tuple(r.configuration_result for r in prepared.requests.values()):
            raise ValueError("participant application differs from the sealed trial")
        configured = {}
        for binding in self.native.bindings:
            configuration = getattr(binding.executor, "configuration_result", None)
            if configuration is None:
                raise ValueError("participant binding has no sealed configuration")
            address = configuration.participant_address
            expected = prepared.requests.get(address)
            if expected is None or configuration != expected.configuration_result:
                raise ValueError("participant binding differs from the sealed trial")
            configured[address] = configuration
        if set(configured) != set(prepared.requests):
            raise ValueError("participant binding set is incomplete")
        _validate_installed_inputs(
            prepared, self.options, self.credential_sources, self._invocation_timeouts()
        )

    def _invocation_timeouts(self) -> Mapping[str, float]:
        """Retain installed action limits independently of a moving deadline."""
        timeouts = {}
        for binding in self.native.bindings:
            address = binding.executor.configuration_result.participant_address
            limit = binding.execution_binding.timeout_seconds
            timeouts[address] = min(timeouts.get(address, limit), limit)
        return timeouts

    def configure(self, request: TrialUnitRequest) -> None:
        """Configure once; a pending or terminal redelivery never restarts it."""
        self.admit(request)
        if self._state in {"active", "finished"}:
            return
        if self._state != "new":
            raise ValueError("participant application is unavailable")
        self._state = "configuring"
        try:
            executors = self._stack.enter_context(
                managed_trial_participants(
                    self.prepared,
                    invocation_timeouts=self._invocation_timeouts(),
                    options=self.options,
                    credential_sources=self.credential_sources,
                    source_environment=self.source_environment,
                    clock=self.clock,
                    stop_and_drain=self._stop_and_drain,
                )
            )
            self.native.install_before_dispatch(
                tuple(
                    replace(
                        binding,
                        executor=executors[
                            binding.executor.configuration_result.participant_address
                        ],
                    )
                    for binding in self.native.bindings
                ),
                trial_bounds=self.prepared.runtime_bounds(self.clock),
            )
            self._state = "active"
        except BaseException:
            self._state = "failed"
            self._stack.close()
            raise

    def _stop_and_drain(self) -> None:
        self.native.cancel()
        if not self.native.drain(30):
            raise RuntimeError("participant application cleanup did not complete")

    def finish(self, request: TrialUnitRequest) -> None:
        """Release leases only after the serving owner verifies terminal cleanup."""
        self.admit(request)
        if self._state == "active":
            self._stop_and_drain()
            self._stack.close()
            self._state = "finished"
