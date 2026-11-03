"""Immutable owner-verified native request, separate from an execution grant."""

from dataclasses import dataclass, field
import hashlib

from raes_contracts.contracts import (
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
)
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.artifact_checksums import checksum_hasher
from raes_contracts.contracts import ParticipantControlContextAssetModel
from raes_contracts.participant_control_context import control_context_asset_reference

from aptl.core.participant_requests.profiles import RequestProfile, RequestCatalog


@dataclass(frozen=True)
class ParticipantRequest:
    """Bind native settings and exact prefix bytes to the sealed configuration."""

    provider: str
    profile: RequestProfile
    build_version: str
    executable_sha256: str
    prompt: str = field(repr=False)
    prompt_sha256: str
    configuration_json: str = field(repr=False)
    manifest_json: str = field(repr=False)
    context_descriptors: tuple[str, ...] = field(repr=False)
    context_contents: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_descriptors", tuple(self.context_descriptors))
        object.__setattr__(self, "context_contents", tuple(self.context_contents))
        self.validate()

    def validate(self) -> None:
        result = self.configuration_result
        manifest = self.manifest
        if (
            manifest.configuration_registry is None
            or result.manifest_digest != canonical_contract_digest(manifest)
            or result.configuration.implementation_identity != manifest.identity
            or result.configuration.owner != manifest.configuration_registry.owner
        ):
            raise ValueError("participant request manifest is inconsistent")
        catalog = RequestCatalog.model_validate_json(
            manifest.constraints["request_profiles"]
        )
        if (
            self.provider != catalog.provider
            or self.profile not in catalog.profiles
            or self.build_version != catalog.build_version
            or self.executable_sha256 != catalog.executable_sha256
        ):
            raise ValueError(
                "participant request profile or build differs from its manifest"
            )
        self._validate_content(result, manifest)
        values = {
            entry.target_id: entry.value.value
            for entry in result.configuration.values
            if entry.value.kind == "literal"
        }
        model_target = "model" if self.provider == "opencode" else "model.identifier"
        if (
            values.get(model_target) != self.profile.model
            or values.get("request.profile") != self.profile.reference
            or values.get("request.profile_digest") != self.profile.digest
            or hashlib.sha256(self.prompt.encode()).hexdigest() != self.prompt_sha256
            or result.configuration.owner.validator_id
            != f"lilrae-{self.provider}-request"
        ):
            raise ValueError(
                "participant request differs from its sealed configuration"
            )

    def _validate_content(
        self,
        result: ParticipantConfigurationResultModel,
        manifest: ParticipantImplementationManifestModel,
    ) -> None:
        selected = {
            entry.control_context_selection.slot_id: entry
            for entry in result.configuration.values
            if entry.control_context_selection is not None
        }
        if (
            set(selected) != set(self.profile.context_order)
            or len(self.context_descriptors) != len(selected)
            or len(self.context_contents) != len(selected)
            or self.prompt != "".join(self.context_contents)
        ):
            raise ValueError(
                "participant content slots or composition are inconsistent"
            )
        for slot, descriptor, content in zip(
            self.profile.context_order,
            self.context_descriptors,
            self.context_contents,
            strict=True,
        ):
            entry = selected[slot]
            selection = entry.control_context_selection
            asset = ParticipantControlContextAssetModel.model_validate_json(descriptor)
            pin = control_context_asset_reference(asset)
            domain = manifest.configuration_registry.resolve(
                entry.target_id
            ).control_context
            if (
                pin != selection.asset_ref
                or domain is None
                or domain.references.get(selection.declaration_ref) != pin
                or entry.value.value != selection.declaration_ref
            ):
                raise ValueError(
                    "participant content descriptor differs from its selected asset"
                )
            data = content.encode("utf-8")
            hasher = checksum_hasher(asset.content.checksum.algorithm)
            hasher.update(data)
            if (
                len(data) != asset.content.size_bytes
                or hasher.hexdigest().casefold()
                != asset.content.checksum.value.casefold()
            ):
                raise ValueError(
                    "participant content differs from its selected commitment"
                )

    @property
    def configuration_result(self) -> ParticipantConfigurationResultModel:
        return ParticipantConfigurationResultModel.model_validate_json(
            self.configuration_json
        )

    @property
    def manifest(self) -> ParticipantImplementationManifestModel:
        return ParticipantImplementationManifestModel.model_validate_json(
            self.manifest_json
        )

    @property
    def prompt_ref(self) -> str:
        return (
            "participant-configuration:"
            + self.configuration_result.configuration_digest
        )
