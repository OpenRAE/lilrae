"""Required-resource observations for one exact public RAES trial request."""

import hashlib
import os
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock

from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import ParticipantConfigurationResultModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult
from raes_contracts.trial_unit import TrialUnitRequest
from raes_processor.trial_realization import (
    TrialRealizationInputs,
)
from raes_runtime.operation_execution_adapter import LocalExecutionAdapter
from raes_runtime.registry import RuntimeTarget

from aptl.backends.readiness_apparatus import ReadinessApparatus
from aptl.core.correlation.clock import ClockProvider
from aptl.core.experiment.capture_plan import CapturePlan, admit_capture_demands
from aptl.core.experiment.capture_registry import (
    DEFAULT_COLLECTOR_REGISTRY,
    CollectorRegistry,
)
from aptl.core.experiment.errors import AdmissionRejection
from aptl.core.readiness_observer import ReadinessObserver
from aptl.core.readiness_record import (
    MAX_READINESS_RECORD_BYTES,
    readiness_request_digest,
    retain_readiness_observation,
)
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_ownership import trial_fence_owner
from aptl.core.trial_readiness import (
    EffectReadinessPort,
    ProvisionerReadinessPort,
    ReadinessOwners,
    observe_capture_readiness,
)
from aptl.utils.pathsafe import open_private_dir_contained_nofollow
from aptl.utils.probe_execution import ProbeProcessRunner


@dataclass(frozen=True)
class ReadinessEnvironment:
    """Approved installed collaborators; no experiment-authored executable inputs."""

    target: RuntimeTarget
    artifact_probe: object | None
    scenario_root: Path
    store: LocalRunStore
    clock: ClockProvider
    owners: ReadinessOwners
    registry: CollectorRegistry = DEFAULT_COLLECTOR_REGISTRY
    probe_timeout_ms: int = 900000
    execution_adapter: LocalExecutionAdapter | None = None
    process_runner: ProbeProcessRunner | None = None


class TrialReadiness:
    """Read-only preparation and live checks shared with the exact native target.

    Construct before admitting the experiment to RAES. Keep this object and
    the target alive for the entire trial delivery and reconciliation. Native
    owners never receive a scheduler or authority to mutate the target here.
    """

    def __init__(
        self, inputs: TrialRealizationInputs, environment: ReadinessEnvironment
    ) -> None:
        target, artifact_probe = environment.target, environment.artifact_probe
        probe_timeout_ms = environment.probe_timeout_ms
        if type(probe_timeout_ms) is not int or not 1 <= probe_timeout_ms <= 2147483647:
            raise ValueError("trial-readiness-budget-invalid")
        self._apparatus = ReadinessApparatus(
            deepcopy(inputs), target, artifact_probe, environment.scenario_root
        )
        self.target = target
        self.store, self.clock = environment.store, environment.clock
        self.owners = replace(
            environment.owners, captures=dict(environment.owners.captures)
        )
        if self.owners.services is None and isinstance(
            target.provisioner, ProvisionerReadinessPort
        ):
            self.owners = replace(self.owners, services=self._native_services)
        self.registry = environment.registry
        self._manifest = deepcopy(target.manifest)
        self._observer = ReadinessObserver(
            probe_timeout_ms,
            environment.execution_adapter,
            environment.process_runner,
            require_runner=getattr(
                target.provisioner, "readiness_requires_runner", True
            )
            is not False,
        )
        self._lock = RLock()
        self._request: TrialUnitRequest | None = None
        self._request_digest = ""
        self._scenario = None
        self._capture: CapturePlan | None = None
        self._prepared = False
        self._clean_verified = False
        self._delivery_complete = False
        self._live = False
        self._target_digest = ""
        self._delivery: tuple[Path, Path, bytes] | None = None
        self._expected_target_digest = ""
        self._references: list[str] = []
        self._bind_target()

    def _bind_target(self) -> None:
        provisioner = self.target.provisioner
        if (
            not isinstance(provisioner, ProvisionerReadinessPort)
            or provisioner.readiness is not None
        ):
            raise ValueError("trial-readiness-provisioner-unavailable")
        components = (
            self.target.orchestrator,
            self.target.evaluator,
            self.target.participant_runtime,
        )
        for component in components:
            if component is not None:
                if (
                    not isinstance(component, EffectReadinessPort)
                    or component.readiness is not None
                ):
                    raise ValueError("trial-readiness-effect-owner-unavailable")
        provisioner.readiness = self
        for component in components:
            if component is not None:
                component.readiness = self

    def _bind_request(self, request: TrialUnitRequest) -> None:
        digest = readiness_request_digest(request)
        if self._request_digest and digest != self._request_digest:
            if not self._delivery_complete:
                raise ValueError("trial-readiness-request-changed")
            self._prepared = self._clean_verified = self._live = False
            self._delivery_complete = False
            self._scenario = self._realization = self._capture = self._delivery = None
            self._references = []
            self._target_digest = self._expected_target_digest = ""
        self._request, self._request_digest = request, digest

    def complete_delivery(self, request: TrialUnitRequest) -> None:
        """Permit a fresh observation set only after verified resource reuse."""
        with self._lock:
            self._bind_request(replace(request))
            if self._delivery is None or self.has_pending_probes:
                raise ValueError("trial-readiness-delivery-incomplete")
            if any(trial_fence_owner(root) is not None for root in self._delivery[:2]):
                raise ValueError("trial-readiness-delivery-incomplete")
            self._delivery_complete = True

    def release_preparation(self, request: TrialUnitRequest) -> None:
        """Discard authority after a fully ceased refusal released its fences."""
        with self._lock:
            self.complete_delivery(request)
            self._prepared = self._clean_verified = self._live = False
            self._delivery = None
            self._target_digest = self._expected_target_digest = ""

    @property
    def references(self) -> tuple[str, ...]:
        """Run-relative immutable observations for the ordinary archive inventory."""
        return tuple(self._references)

    def close(self) -> None:
        self._observer.close()

    def _identity(self) -> str:
        if self.owners.target_identity is None:
            raise ValueError
        identity = self._observer.call(self.owners.target_identity)
        if not isinstance(identity, str) or not 1 <= len(identity) <= 1024:
            raise ValueError
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def observe_placement(self, operation: Callable[[], str]) -> str:
        """Bound the placement lookup before a target can acquire its fences."""
        try:
            identity = self._observer.call(operation)
            if not isinstance(identity, str) or not 1 <= len(identity) <= 1024:
                raise ValueError
            return identity
        except Exception:
            raise ValueError("trial-daemon-unverified") from None

    def prepare(self, request: TrialUnitRequest) -> None:
        """Derive the exact entry without materialization, downloads, or execution."""
        with self._lock:
            request = replace(request)
            self._bind_request(request)
            if self._prepared and not self.has_pending_probes:
                return
            checks: list[Diagnostic] = []
            derived = self._observer.check(
                checks, "artifacts-and-contract", self._derive
            )
            self._observer.check(checks, "target", self._prepare_identity)
            self._observer.check(checks, "containment", self.owners.containment)
            if derived:
                self._observer.check(
                    checks, "participant-configuration", self._participants
                )
                self._observer.check(checks, "capture-capability", self._admit_capture)
                self._observer.check(checks, "installed-backend", self._native_contract)
                self._check_resources(checks)
                self._observer.check(checks, "storage", self._storage)
            self._check_cessation(checks)
            self._record("prepared", checks)
            self._prepared = not any(check.is_error for check in checks)
            if not self._prepared:
                raise ValueError("trial-readiness-blocked")

    def _prepare_identity(self) -> bool:
        self._target_digest = self._identity()
        return self.target.manifest == self._manifest and (
            not self._expected_target_digest
            or self._target_digest == self._expected_target_digest
        )

    def bind_delivery(
        self,
        request: TrialUnitRequest,
        project: Path,
        daemon_root: Path,
        owner: bytes,
        daemon: str,
    ) -> None:
        """Bind the wrapper's held placement to this exact readiness authority."""
        with self._lock:
            self._bind_request(replace(request))
            scope = (project, daemon_root, owner)
            if self._delivery is not None and self._delivery != scope:
                raise ValueError("trial-readiness-placement-changed")
            self._delivery = scope
            self._delivery_complete = False
            self._expected_target_digest = hashlib.sha256(daemon.encode()).hexdigest()
            if (
                self._target_digest
                and self._target_digest != self._expected_target_digest
            ):
                raise ValueError("trial-readiness-target-changed")

    def _require_owned(self) -> None:
        if self._delivery is None:
            raise ValueError("trial-readiness-placement-unowned")
        project, daemon_root, owner = self._delivery
        if any(trial_fence_owner(root) != owner for root in (project, daemon_root)):
            raise ValueError("trial-readiness-placement-unowned")

    def _derive(self) -> bool:
        realized = self._apparatus.derive(self._require_request())
        if realized is None:
            return False
        self._scenario, self._realization = realized.instantiated, realized
        return True

    def _admit_capture(self) -> bool:
        try:
            self._capture = admit_capture_demands(
                self._realization.execution_plan.model.capture_demands,
                source_identity=self._realization.snapshot_digest,
                registry=self.registry,
            )
        except AdmissionRejection:
            return False
        return all(
            type(value) is int and value > 0
            for item in self._capture.bindings
            for value in (
                item.limits.max_bytes,
                item.limits.max_artifact_count,
                item.limits.max_duration_s,
            )
        )

    def _native_contract(self) -> bool:
        return self._apparatus.native_contract(self._realization)

    def _native_services(self, scenario: object) -> bool:
        del scenario
        return self._apparatus.native_services(self._realization)

    def _participants(self) -> bool:
        request = self._require_request()
        installed = {}
        for owner in self.owners.participants:
            current = self._observer.call(owner.configuration)
            if not isinstance(current, ParticipantConfigurationResultModel):
                return False
            current = ParticipantConfigurationResultModel.model_validate(
                current.model_dump(mode="json")
            )
            if (
                current.participant_address in installed
                or canonical_contract_digest(current.configuration)
                != current.configuration_digest
            ):
                return False
            installed[current.participant_address] = (owner, current)
        for configuration in request.participant_configurations:
            selected = installed.get(configuration.participant_address)
            if selected is None:
                return False
            owner, current = selected
            if (
                current.model_dump(mode="json") != configuration.model_dump(mode="json")
                or canonical_contract_digest(owner.manifest)
                != configuration.manifest_digest
                or self._observer.call(owner.check) is not True
            ):
                return False
        return True

    def _storage(self) -> bool:
        request = self._require_request()
        capture = self._capture
        if capture is None:
            return False
        required = MAX_READINESS_RECORD_BYTES + sum(
            item.limits.max_bytes for item in capture.bindings
        )
        fd = open_private_dir_contained_nofollow(
            self.store.base_dir, Path(request.run_id)
        )
        try:
            info = os.fstatvfs(fd)
            return info.f_bavail * info.f_frsize >= required
        finally:
            os.close(fd)

    def require_live(self) -> None:
        """Refuse effects until required live observations have been retained."""
        self._require_owned()
        self.check_live()

    def after_provisioning(
        self, plan: ProvisioningPlan, result: ApplyResult
    ) -> ApplyResult:
        """Gate a complete realization while preserving native partial effects."""
        if plan.operations and all(
            operation.action is ChangeAction.DELETE for operation in plan.operations
        ):
            return result
        self._live = False
        request = self._require_request()
        expected = {
            operation.address
            for operation in request.provisioning_plan.operations
            if operation.action != "delete"
        }
        if result.success and expected.issubset(result.snapshot.entries):
            try:
                self.require_live()
            except Exception:
                # Native provisioning really succeeded and its effects must be
                # committed. Effect adapters still refuse, and the trial-services
                # owner projects the readiness refusal to the trial outcome.
                # Turning this into a failed native apply would discard its
                # accepted effect boundary and obstruct RAES cleanup.
                self._live = False
        return result

    @property
    def has_pending_probes(self) -> bool:
        return self._observer.has_pending

    @property
    def execution_ready(self) -> bool:
        return self._prepared and self._live

    def require_prepared(self, request: TrialUnitRequest) -> None:
        with self._lock:
            self._bind_request(replace(request))
            self._require_owned()
            if not self._prepared or self.has_pending_probes:
                raise ValueError("trial-readiness-not-prepared")

    def require_provisioning(self) -> None:
        """Require preparation and owned placement before native apply effects."""
        self.require_prepared(self._require_request())

    def check_live(self) -> None:
        """Check a realized target without granting independent effect authority."""
        with self._lock:
            self._live = False
            if not self._prepared or self._scenario is None or self._capture is None:
                raise ValueError("trial-readiness-not-prepared")
            checks: list[Diagnostic] = []
            self._observer.check(
                checks,
                "target",
                lambda: (
                    self._identity() == self._target_digest
                    and self.target.manifest == self._manifest
                ),
            )
            self._observer.check(checks, "containment", self.owners.containment)
            self._observer.check(checks, "clean-state", lambda: self._clean_verified)
            self._observer.check(checks, "storage", self._storage)
            self._observer.check(
                checks,
                "services",
                None
                if self.owners.services is None
                else lambda: self.owners.services(deepcopy(self._scenario)),
            )
            self._check_resources(checks)
            observe_capture_readiness(
                self._capture, self.owners.captures, self._observer, checks
            )
            self._observer.check(
                checks, "participant-configuration", self._participants
            )
            self._check_cessation(checks)
            self._record("live", checks)
            self._live = not any(check.is_error for check in checks)
            if not self._live:
                raise ValueError("trial-readiness-blocked")

    def _check_cessation(self, checks: list[Diagnostic]) -> None:
        # Observe outside the adapter call: its own active worker must not
        # appear as a previously unresolved operation.
        ceased = not self.has_pending_probes
        self._observer.check(checks, "probe-cessation", lambda: ceased)

    def _check_resources(self, checks: list[Diagnostic]) -> None:
        try:
            minimum = self._observer.call(
                self._apparatus.required_resource_minimum,
                self._require_request().plan_entry_id,
            )
        except Exception:
            self._observer.check(checks, "resource-selection", lambda: False)
            return
        if minimum is not None:
            operation = (
                None
                if self.owners.resources is None
                else lambda: self.owners.resources(deepcopy(self._scenario), minimum)
            )
            self._observer.check(checks, "resources", operation)

    def record_clean(
        self, request: TrialUnitRequest, check: Callable[[], None]
    ) -> None:
        """Retain the ordinary placement owner's result without replacing it."""
        with self._lock:
            self._bind_request(replace(request))
            if self._clean_verified:
                return
            checks: list[Diagnostic] = []

            def clean() -> bool:
                check()
                return True

            passed = self._observer.check(checks, "clean-state", clean)
            self._record("clean", checks)
            self._clean_verified = passed
            if not passed:
                raise ValueError("trial-placement-contaminated")

    def _require_request(self) -> TrialUnitRequest:
        if self._request is None:
            raise ValueError("trial-readiness-not-prepared")
        return self._request

    def _record(self, stage: str, checks: list[Diagnostic]) -> None:
        if len(self._references) >= 4096:
            raise ValueError("trial-readiness-observation-limit")
        relative = retain_readiness_observation(
            self._require_request(),
            self.store,
            self.clock,
            stage,
            checks,
            self._target_digest or self._expected_target_digest,
            self._capture,
        )
        if relative not in self._references:
            self._references.append(relative)
