"""Provider-neutral capture contribution selected for one admitted pack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Callable
from collections.abc import Mapping
from types import MappingProxyType
from copy import deepcopy

from aptl.backends.identity import BackendIdentity
from aptl.core.experiment.capture_registry import (
    CollectorRegistration,
    CollectorRegistry,
)
from aptl.core.scenario_bundle import PackIdentity
from aptl.backends.scenario_family import AdmittedFamilyTrial, QualifiedFamilyTarget
from aptl.backends.scenario_runtime_hooks import (
    AdmittedRuntimeOperations,
    ScenarioRuntimeOperations,
)
from aptl.core.evidence.adapters.sources import WindowedSource
from aptl.core.experiment.capture_registry import CaptureBinding
from aptl.core.evidence.protocol import Collector, RunScope

ENTRY_POINT_GROUP = "aptl.scenario_capture"
EXTENSION_API_VERSION = "1"


@dataclass(frozen=True)
class CaptureSourceContext:
    """Declared native-source inputs without archive or host-path authority."""

    operations: ScenarioRuntimeOperations = field(repr=False)
    realization: object = field(repr=False)
    environment: Mapping[str, str] = field(repr=False)
    trial: AdmittedFamilyTrial | None = field(default=None, repr=False)
    read_generated_output: Callable[[str, str], bytes] | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True)
class GeneratedOutputReference:
    """One generated output explicitly granted to a native capture source."""

    artifact: str
    output: str


class ScenarioCaptureRuntimeAdapter(Protocol):
    """Source construction and restart-safe transcript operations."""

    def native_sources(
        self, context: CaptureSourceContext
    ) -> Mapping[str, WindowedSource]: ...
    def binding_from_projection(
        self, value: Mapping[str, object]
    ) -> CaptureBinding: ...
    def finalized_transcript_collector(
        self, binding: CaptureBinding, payload: bytes, activated_at: str
    ) -> Collector: ...
    def validate_retained_transcript(
        self,
        payload: bytes,
        *,
        expected_entries: int | None = None,
        expected_frames: int | None = None,
    ) -> None: ...


class ScenarioPropositionInterpreter(Protocol):
    """Interpret retained records for one exact proposition and polarity."""

    capability_ids: frozenset[str]

    def __call__(
        self,
        assertion_address: str,
        proposition_address: str,
        polarity: str,
        payload: Mapping[str, object],
        evidence_records: tuple[object, ...],
    ) -> Mapping[str, object] | None: ...


def capture_source_context(request: object) -> CaptureSourceContext:
    """Detach source inputs and expose only explicitly granted credential keys."""

    from aptl.backends.scenario_service_policy import artifact_source_path
    from aptl.utils.pathsafe import open_contained_nofollow

    realization = deepcopy(request.realization)
    keys = request.capture_selection.contribution.runtime_environment_keys
    environment = MappingProxyType(
        {key: request.environment[key] for key in keys if key in request.environment}
    )

    def read_output(artifact_name: str, output_name: str) -> bytes:
        """Read one bounded generated output explicitly granted by the adapter."""

        allowed = request.capture_selection.contribution.generated_output_refs
        if GeneratedOutputReference(artifact_name, output_name) not in allowed:
            raise ValueError("capture-output-not-granted")
        artifacts = [
            item
            for item in realization.generated_artifacts
            if item.name == artifact_name
        ]
        if len(artifacts) != 1:
            raise ValueError("capture-output-not-admitted")
        outputs = [item for item in artifacts[0].outputs if item.name == output_name]
        if len(outputs) != 1:
            raise ValueError("capture-output-not-admitted")
        try:
            root = artifact_source_path(request.project_dir, artifacts[0])
            with open_contained_nofollow(root, outputs[0].path) as handle:
                data = handle.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError
            return data
        except Exception:
            raise ValueError("capture-output-unavailable") from None

    return CaptureSourceContext(
        AdmittedRuntimeOperations(request.backend, realization.nodes),
        realization,
        environment,
        request.capture_selection.context.trial,
        read_output,
    )


def family_capture_sources(request: object) -> Mapping[str, WindowedSource]:
    """Contain native-source callbacks and reject undeclared source identities."""

    try:
        contribution = request.capture_selection.contribution
        sources = contribution.runtime_adapter.native_sources(
            capture_source_context(request)
        )
        if (
            not isinstance(sources, Mapping)
            or len(sources) > 256
            or not set(sources).issubset(contribution.native_registration_ids)
            or any(
                not isinstance(source, WindowedSource) for source in sources.values()
            )
        ):
            raise ValueError
        return dict(sources)
    except Exception:
        raise ValueError("family-capture-sources-invalid") from None


@dataclass(frozen=True)
class ScenarioCaptureContext:
    """Exact pack/backend identity visible during capture selection."""

    pack: PackIdentity
    backend: BackendIdentity
    trial: AdmittedFamilyTrial | None = None


@dataclass(frozen=True)
class ScenarioCaptureResumeContext:
    """Safe retained identity for finalization; no snapshot or credential values."""

    target: QualifiedFamilyTarget
    trial_identity: Mapping[str, str]

    def __post_init__(self) -> None:
        import re

        values = self.trial_identity
        digests = {"family_digest", "snapshot_digest", "plan_digest", "entry_digest"}
        identifiers = {"family_id", "plan_id", "plan_entry_id", "run_id"}
        if (
            set(values) != digests | identifiers
            or any(
                not isinstance(values[key], str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", values[key]) is None
                for key in digests
            )
            or any(
                not isinstance(values[key], str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", values[key])
                is None
                for key in identifiers
            )
            or values["family_id"] != self.target.family_id
            or values["family_digest"] != self.target.family_digest
        ):
            raise ValueError("family-trial-identity-invalid")
        object.__setattr__(
            self, "trial_identity", MappingProxyType(dict(self.trial_identity))
        )

    @property
    def pack(self) -> PackIdentity:
        return self.target.pack

    @property
    def backend(self) -> BackendIdentity:
        return self.target.backend

    @property
    def trial(self) -> None:
        return None


def capture_run_scope(
    context: ScenarioCaptureContext | ScenarioCaptureResumeContext,
    run_id: str,
    capture_plan_id: str,
    attempt_id: str,
) -> RunScope:
    """Keep admitted trial identity separate from the capture-plan identity."""

    trial = getattr(context, "trial", None)
    lineage = None
    if trial is not None:
        lineage = trial.identity()
    elif isinstance(context, ScenarioCaptureResumeContext):
        lineage = context.trial_identity
    if lineage is not None:
        if run_id != lineage["run_id"]:
            raise ValueError("family-run-identity-mismatch")
        return RunScope(run_id, lineage["plan_entry_id"], attempt_id)
    return RunScope(run_id, capture_plan_id, attempt_id)


@dataclass(frozen=True)
class ScenarioCaptureContribution:
    """Validated declarations and narrow executable capture adapter."""

    registrations: tuple[CollectorRegistration, ...]
    native_registration_ids: frozenset[str] = frozenset()
    runtime_environment_keys: tuple[str, ...] = ()
    transcript_registration_id: str | None = None
    runtime_adapter: ScenarioCaptureRuntimeAdapter | None = field(
        default=None, repr=False, compare=False
    )
    proposition_interpreter: ScenarioPropositionInterpreter | None = field(
        default=None, repr=False, compare=False
    )
    generated_output_refs: tuple[GeneratedOutputReference, ...] = ()


class ScenarioCaptureProvider(Protocol):
    """Installed provider contract; installation grants normal Python authority."""

    provider_id: str
    extension_api_version: str
    supported_pack_id: str
    supported_pack_versions: tuple[str, ...]
    supported_pack_set_digests: tuple[str, ...]
    backend_target_name: str
    backend_target_versions: tuple[str, ...]
    backend_profiles: tuple[str, ...]
    backend_transports: tuple[str, ...]

    def resolve(
        self, context: ScenarioCaptureContext
    ) -> ScenarioCaptureContribution: ...

    def resume_capture(
        self, context: ScenarioCaptureResumeContext
    ) -> ScenarioCaptureContribution: ...


@dataclass(frozen=True)
class ResolvedScenarioCapture:
    """Core-owned copy of one exact installed capture contribution."""

    registry: CollectorRegistry
    contribution: ScenarioCaptureContribution
    context: ScenarioCaptureContext | ScenarioCaptureResumeContext
    provider_id: str
    extension_api_version: str
    distribution: str = ""
    distribution_version: str = ""
    entry_point: str = ""


__all__ = [
    "ENTRY_POINT_GROUP",
    "EXTENSION_API_VERSION",
    "ResolvedScenarioCapture",
    "ScenarioCaptureContext",
    "ScenarioCaptureContribution",
    "ScenarioCaptureProvider",
    "CaptureSourceContext",
    "ScenarioCaptureRuntimeAdapter",
    "ScenarioPropositionInterpreter",
    "capture_source_context",
    "family_capture_sources",
    "ScenarioCaptureResumeContext",
    "GeneratedOutputReference",
    "capture_run_scope",
]
