"""Detached family trial values and installed-provider identities."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING

from aptl.backends.identity import BackendIdentity
from aptl.core.scenario_bundle import PackIdentity

if TYPE_CHECKING:
    from raes.scenario import ExpandedScenario, InstantiatedScenario
    from raes.phase_contracts import TrialInstantiationProvenance
    from raes_contracts.contracts import (
        AdmittedTrialPlanModel,
        ParticipantConfigurationResultModel,
    )


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
    snapshot: bytes | None = field(default=None, repr=False)


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
            "selections": [
                {
                    "variation_point_id": item.variation_point_id,
                    "record_digest": item.record_digest,
                }
                for item in self.provenance.selections
            ],
            "participant_configurations": [
                {
                    "participant_address": item.participant_address,
                    "manifest_digest": item.manifest_digest,
                    "configuration_digest": item.configuration_digest,
                }
                for item in self.participant_configuration_results
            ],
        }
