"""Public atomic family qualification for existing installed adapter seams."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from importlib import metadata
import json
import re
from typing import TYPE_CHECKING
from collections.abc import Callable

from aptl.backends._lilrae_family_release_set import require_consistent_release_set
from aptl.backends.identity import BackendIdentity
from aptl.core.scenario_bundle import PackIdentity

if TYPE_CHECKING:
    from raes.scenario import ExpandedScenario, InstantiatedScenario
    from raes.phase_contracts import TrialInstantiationProvenance
    from raes_contracts.contracts import (
        AdmittedTrialPlanModel,
        ParticipantConfigurationResultModel,
    )
    from aptl.core.scenario_bundle import ScenarioBundle

FAMILY_API_VERSION = "1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MAX_QUALIFIED_FAMILIES = 64


@dataclass(frozen=True)
class QualifiedFamilyTarget:
    """One release, authored family and backend qualified together."""

    pack: PackIdentity
    family_id: str
    family_digest: str
    backend: BackendIdentity


@dataclass(frozen=True)
class FamilyTrialInput:
    """Sealed owner inputs; core reconstructs them before adapter admission."""

    plan: AdmittedTrialPlanModel = field(repr=False)
    plan_entry_id: str
    family: ExpandedScenario = field(repr=False)


@dataclass(frozen=True)
class FamilyProviderIdentity:
    """Safe installed identity retained for one selected capability."""

    group: str
    entry_point: str
    provider_id: str
    distribution: str
    distribution_version: str
    extension_api_version: str


@dataclass(frozen=True)
class FamilyProviderSelection:
    """Host-observed installation identity and the selected trusted provider."""

    group: str
    entry_point: str
    distribution: str
    distribution_version: str
    provider_id: str
    provider: object = field(repr=False, compare=False)
    requires: tuple[str, ...] = field(default=(), repr=False, compare=False)

    def identity(self) -> FamilyProviderIdentity:
        version = "2" if self.group == "aptl.scenario_verifiers" else "1"
        return FamilyProviderIdentity(
            self.group,
            self.entry_point,
            self.provider_id,
            self.distribution,
            self.distribution_version,
            version,
        )


@dataclass(frozen=True)
class AdmittedFamilyTrial:
    """Immutable canonical bytes; each scenario access returns a detached model."""

    target: QualifiedFamilyTarget
    snapshot_digest: str
    snapshot: bytes = field(repr=False)
    installation: tuple[str, str] | None = None
    providers: tuple[FamilyProviderIdentity, ...] = ()
    participant_configurations: bytes = field(default=b"[]", repr=False)

    @property
    def scenario(self) -> InstantiatedScenario:
        from raes import InstantiatedScenarioSnapshot, admit_instantiated_scenario

        envelope = InstantiatedScenarioSnapshot.model_validate_json(self.snapshot)
        return admit_instantiated_scenario(envelope.scenario)

    @property
    def provenance(self) -> TrialInstantiationProvenance:
        return self.scenario.instantiation_provenance.trial

    @property
    def participant_configuration_results(
        self,
    ) -> tuple[ParticipantConfigurationResultModel, ...]:
        """Return detached copies of the sealed entry's participant configurations."""

        from pydantic import TypeAdapter
        from raes_contracts.contracts import ParticipantConfigurationResultModel

        adapter = TypeAdapter(tuple[ParticipantConfigurationResultModel, ...])
        return adapter.validate_json(self.participant_configurations)

    def identity(self) -> dict[str, str]:
        """Return safe lineage identifiers without binding or selection values."""

        trial = self.provenance
        return {
            "family_id": self.target.family_id,
            "family_digest": self.target.family_digest,
            "snapshot_digest": self.snapshot_digest,
            "plan_id": trial.plan_id,
            "plan_digest": trial.plan_digest,
            "plan_entry_id": trial.plan_entry_id,
            "entry_digest": trial.entry_digest,
            "run_id": trial.run_id,
        }

    def evidence(self) -> dict[str, object]:
        """Project qualification, lineage and installations without runtime values."""

        return {
            "target": asdict(self.target),
            "trial": self.identity(),
            "providers": [asdict(item) for item in self.providers],
            "participant_configurations": [
                {
                    "participant_address": item.participant_address,
                    "manifest_digest": item.manifest_digest,
                    "configuration_digest": item.configuration_digest,
                }
                for item in self.participant_configuration_results
            ],
        }


def admit_family_trial(
    bundle: ScenarioBundle, backend: BackendIdentity, request: FamilyTrialInput
) -> AdmittedFamilyTrial:
    """Bind a sealed trial to this acquired source through public RAES gates."""

    from raes import canonical_instantiated_sdl_bytes, canonical_instantiated_sdl_digest
    from raes import canonical_sdl_digest, parse_sdl_file
    from raes_processor.trial_realization import instantiate_admitted_trial_entry

    try:
        family = request.family.model_copy(deep=True)
        plan = request.plan.model_copy(deep=True)
        source = parse_sdl_file(bundle.sdl_path)
        family_digest = canonical_sdl_digest(family).value
        if (
            bundle.pack_identity is None
            or canonical_sdl_digest(source).value != family_digest
        ):
            raise ValueError
        scenario = instantiate_admitted_trial_entry(
            plan=plan, plan_entry_id=request.plan_entry_id, family=family
        )
        provenance = scenario.instantiation_provenance.trial
        if provenance is None or any(
            not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None
            for value in (
                provenance.plan_id,
                provenance.plan_entry_id,
                provenance.run_id,
            )
        ):
            raise ValueError
        snapshot = canonical_instantiated_sdl_bytes(scenario)
        if len(snapshot) > 16 * 1024 * 1024:
            raise ValueError
        return AdmittedFamilyTrial(
            QualifiedFamilyTarget(
                bundle.pack_identity, family.name, family_digest, backend
            ),
            canonical_instantiated_sdl_digest(scenario).value,
            snapshot,
            participant_configurations=_sealed_participant_configurations(
                plan, provenance
            ),
        )
    except Exception:
        raise ValueError("family-trial-invalid") from None


def _sealed_participant_configurations(
    plan: AdmittedTrialPlanModel, provenance: TrialInstantiationProvenance
) -> bytes:
    """Return the instantiated entry's sealed configurations as canonical JSON.

    RAES verified this plan copy when it instantiated the entry. The entry
    digest binds the configurations to the trial provenance.
    """

    from raes_contracts.canonical import canonical_json_bytes

    entry = plan.entries[provenance.plan_entry_id]
    if entry.entry_digest != provenance.entry_digest:
        raise ValueError
    return canonical_json_bytes(
        [item.model_dump(mode="json") for item in entry.participant_configurations]
    )


def _valid_target(target: object) -> bool:
    """Check the atomic target shape before validating its identity fields."""

    if not isinstance(target, QualifiedFamilyTarget):
        return False
    pack, backend = target.pack, target.backend
    if not isinstance(pack, PackIdentity) or not isinstance(backend, BackendIdentity):
        return False
    return _valid_target_fields(target, pack, backend)


def _valid_target_fields(
    target: QualifiedFamilyTarget, pack: PackIdentity, backend: BackendIdentity
) -> bool:
    """Validate bounded release, family and backend identity values."""

    identifiers = (pack.pack_id, target.family_id, backend.target_name, backend.profile)
    versions = (pack.pack_version, backend.target_version)
    digests = (pack.set_digest, target.family_digest)
    return (
        all(
            isinstance(value, str) and _IDENTIFIER.fullmatch(value)
            for value in identifiers
        )
        and all(isinstance(value, str) and 0 < len(value) <= 256 for value in versions)
        and all(
            isinstance(value, str) and _DIGEST.fullmatch(value) for value in digests
        )
        and all(
            isinstance(value, str) and len(value) <= 128
            for value in (backend.provider, backend.transport)
        )
    )


def encode_family_target(target: QualifiedFamilyTarget) -> str:
    """Encode only validated qualification identity for a restart receipt."""

    if not _valid_target(target):
        raise ValueError("family-target-invalid")
    return json.dumps(
        {"family_api_version": FAMILY_API_VERSION, **asdict(target)},
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_family_target(value: str) -> QualifiedFamilyTarget:
    """Reconstruct a bounded exact target without importing provider code."""

    try:
        if not isinstance(value, str) or len(value) > 4096:
            raise ValueError
        payload = json.loads(value)
        if (
            set(payload)
            != {"family_api_version", "pack", "family_id", "family_digest", "backend"}
            or payload.pop("family_api_version") != FAMILY_API_VERSION
        ):
            raise ValueError
        target = QualifiedFamilyTarget(
            PackIdentity(**payload["pack"]),
            payload["family_id"],
            payload["family_digest"],
            BackendIdentity(**payload["backend"]),
        )
        if not _valid_target(target):
            raise ValueError
        return target
    except Exception:
        raise ValueError("family-target-invalid") from None


def family_provider_matches(provider: object, target: QualifiedFamilyTarget) -> bool:
    """Match exact atomic targets; contain all provider metadata failures."""

    try:
        version = getattr(provider, "family_api_version", None)
        targets = getattr(provider, "qualified_family_targets", None)
        if (
            version != FAMILY_API_VERSION
            or not isinstance(targets, tuple)
            or not 1 <= len(targets) <= MAX_QUALIFIED_FAMILIES
            or not all(_valid_target(item) for item in targets)
            or len(set(targets)) != len(targets)
            or not _valid_target(target)
        ):
            raise ValueError
        return target in targets
    except Exception:
        raise ValueError("family-provider-metadata-invalid") from None


def family_capabilities(
    target: QualifiedFamilyTarget,
) -> tuple[tuple[str, str, str, str], ...]:
    """Return existing group, exact selector, callable version and method."""

    pack = target.pack.pack_id
    serving = f"{pack}.{target.backend.target_name}"
    verifier = f"{target.family_id}.{target.backend.target_name}"
    return (
        ("aptl.pack_backend_interactions", serving, "1", "resolve"),
        ("aptl.scenario_runtime_parameters", pack, "1", "resolve"),
        ("aptl.scenario_startup", pack, "1", "resolve"),
        ("aptl.scenario_capture", serving, "1", "resolve"),
        ("aptl.scenario_planning_compatibility", serving, "1", "resolve"),
        ("aptl.scenario_verifiers", verifier, "2", "run"),
    )


def _family_entry_selection(
    entry: metadata.EntryPoint,
    group: str,
    selector: str,
    api_version: str,
    method: str,
    target: QualifiedFamilyTarget,
) -> FamilyProviderSelection | None:
    """Load one candidate and contain its executable metadata failures."""

    try:
        provider = entry.load()
        if isinstance(provider, type):
            provider = provider()
    except Exception:
        raise ValueError("family-provider-load-failed") from None
    try:
        if getattr(provider, "family_api_version", None) is None:
            return None
        if not family_provider_matches(provider, target):
            return None
        identifier = _family_entry_identity(entry, provider, api_version, method)
        return FamilyProviderSelection(
            group,
            selector,
            entry.dist.name,
            entry.dist.version,
            identifier,
            provider,
            tuple(entry.dist.requires or ()),
        )
    except Exception:
        raise ValueError("family-provider-metadata-invalid") from None


def _family_entry_identity(
    entry: metadata.EntryPoint, provider: object, api_version: str, method: str
) -> str:
    """Check the callable contract and host-observed installation identity."""

    identifier = getattr(
        provider, "plugin_id" if method == "run" else "provider_id", None
    )
    if (
        getattr(provider, "extension_api_version", None) != api_version
        or not callable(getattr(provider, method, None))
        or not isinstance(identifier, str)
        or _IDENTIFIER.fullmatch(identifier) is None
        or _IDENTIFIER.fullmatch(entry.dist.name) is None
        or not isinstance(entry.dist.version, str)
        or not 1 <= len(entry.dist.version) <= 256
    ):
        raise ValueError("family-provider-metadata-invalid")
    return identifier


def select_family_provider(
    group: str,
    selector: str,
    api_version: str,
    method: str,
    target: QualifiedFamilyTarget,
) -> FamilyProviderSelection:
    """Select one required family capability using its existing entry point."""

    try:
        entries = [
            entry
            for entry in metadata.entry_points(group=group)
            if entry.name == selector
        ]
        if len(entries) > MAX_QUALIFIED_FAMILIES:
            raise ValueError
    except Exception:
        raise ValueError("family-provider-discovery-failed") from None
    compatible = []
    for entry in entries:
        selected = _family_entry_selection(
            entry, group, selector, api_version, method, target
        )
        if selected is not None:
            compatible.append(selected)
    if len(compatible) != 1:
        code = "ambiguous" if compatible else "missing"
        raise ValueError(f"family-provider-{code}")
    return compatible[0]


def require_family_capabilities(
    trial: AdmittedFamilyTrial,
) -> tuple[FamilyProviderSelection, ...]:
    """Require one coherent installation before any preparation or effects."""

    selections = tuple(
        select_family_provider(group, selector, version, method, trial.target)
        for group, selector, version, method in family_capabilities(trial.target)
    )
    if (
        len({(item.distribution, item.distribution_version) for item in selections})
        != 1
    ):
        raise ValueError("family-provider-installation-mismatch")
    require_consistent_release_set(selections[0].requires)
    return selections


def resolve_family_provider(
    group: str, trial: AdmittedFamilyTrial
) -> FamilyProviderSelection:
    """Resolve an existing capability without losing the pinned installation."""

    for capability, selector, version, method in family_capabilities(trial.target):
        if capability == group:
            selected = select_family_provider(
                group, selector, version, method, trial.target
            )
            if trial.installation is not None and trial.installation != (
                selected.distribution,
                selected.distribution_version,
            ):
                raise ValueError("family-provider-installation-mismatch")
            if trial.providers and selected.identity() not in trial.providers:
                raise ValueError("family-provider-installation-mismatch")
            return selected
    raise ValueError("family-capability-invalid")


def resolve_family_contribution[_Result](
    group: str,
    trial: AdmittedFamilyTrial,
    context: object,
    validate: Callable[[object], _Result],
) -> tuple[FamilyProviderSelection, _Result]:
    """Contain one family callback and pass its result through its owner validator."""

    pack = getattr(context, "pack", getattr(context, "pack_identity", None))
    backend = getattr(context, "backend", trial.target.backend)
    if pack != trial.target.pack or backend != trial.target.backend:
        raise ValueError("family-context-mismatch")
    selected = resolve_family_provider(group, trial)
    try:
        return selected, validate(selected.provider.resolve(context))
    except Exception:
        raise ValueError("family-provider-result-invalid") from None


__all__ = [
    "FAMILY_API_VERSION",
    "QualifiedFamilyTarget",
    "family_provider_matches",
    "FamilyTrialInput",
    "AdmittedFamilyTrial",
    "admit_family_trial",
    "FamilyProviderSelection",
    "FamilyProviderIdentity",
    "family_capabilities",
    "select_family_provider",
    "require_family_capabilities",
    "resolve_family_provider",
    "resolve_family_contribution",
    "encode_family_target",
    "decode_family_target",
]
