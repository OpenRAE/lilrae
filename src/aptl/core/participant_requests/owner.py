"""Implementation-owned request admission composed with public SDL pin validation."""

from __future__ import annotations

from collections.abc import Mapping

import rfc8785
import hashlib
from raes_contracts.artifact_checksums import checksum_hasher
from raes import build_declaration_index
from raes.scenario import ScenarioContent
from raes.participant_control_context import SDLControlContextConfigurationValidator
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import (
    ConfigurationTargetRegistryModel,
    ConfigurationTargetDeclarationModel,
    RealizedConfigurationValueModel,
    ParticipantConfigurationModel,
    ParticipantConfigurationResultModel,
    ParticipantControlContextAssetReferenceModel,
    ParticipantControlContextAssetModel,
    ParticipantControlContextConfigurationSelectionModel,
    ParticipantImplementationManifestModel,
)

from aptl.core.participant_requests.manifest import participant_manifest
from aptl.core.participant_requests.profiles import RequestCatalog, RequestProfile
from aptl.core.participant_requests.request import ParticipantRequest

ContextDomains = Mapping[
    str, Mapping[str, ParticipantControlContextAssetReferenceModel]
]


def decode_context_asset(asset: ParticipantControlContextAssetModel, data: bytes) -> str:
    """Check bounded pinned bytes before decoding an authored context slot."""
    if (
        not isinstance(data, bytes)
        or len(data) > 128_000
        or len(data) != asset.content.size_bytes
    ):
        raise ValueError("participant content size is invalid")
    hasher = checksum_hasher(asset.content.checksum.algorithm)
    hasher.update(data)
    if hasher.hexdigest().casefold() != asset.content.checksum.value.casefold():
        raise ValueError("participant content checksum is inconsistent")
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError("participant content must be UTF-8") from None


class ParticipantRequestOwner:
    """Trusted assembly supplies the catalog; author selections cannot extend it."""

    def __init__(
        self,
        *,
        catalog: RequestCatalog,
        context_domains: ContextDomains,
        scenario: ScenarioContent,
    ) -> None:
        self._catalog = RequestCatalog.model_validate_json(catalog.model_dump_json())
        if not 1 <= len(context_domains) <= 16 or any(
            set(p.context_order) != set(context_domains) for p in self._catalog.profiles
        ):
            raise ValueError(
                "request profiles must order exactly the declared context slots"
            )
        self._scenario = type(scenario).model_validate(
            scenario.model_dump(mode="python")
        )
        self._context_validator = SDLControlContextConfigurationValidator(
            self._scenario
        )
        self._manifest_json = self._manifest(context_domains).model_dump_json()

    @property
    def catalog(self) -> RequestCatalog:
        return self._catalog

    @property
    def model_target(self) -> str:
        return "model" if self.catalog.provider == "opencode" else "model.identifier"

    @property
    def manifest(self) -> ParticipantImplementationManifestModel:
        return ParticipantImplementationManifestModel.model_validate_json(
            self._manifest_json
        )

    def _manifest(
        self, context_domains: ContextDomains
    ) -> ParticipantImplementationManifestModel:
        targets = {
            name: {
                "target_id": name,
                "value_type": "string",
                "allowed_value_kinds": ["literal"],
                "sensitivity": "internal",
            }
            for name in (self.model_target, "request.profile", "request.profile_digest")
        }
        for slot, references in context_domains.items():
            name = f"context.{slot}"
            targets[name] = {
                "target_id": name,
                "value_type": "string",
                "allowed_value_kinds": ["literal"],
                "sensitivity": "internal",
                "control_context": {"slot_id": slot, "references": dict(references)},
            }
        registry = ConfigurationTargetRegistryModel.model_validate(
            {
                "owner": {
                    "contract_id": "participant-implementation-manifest/v1",
                    "contract_version": "1",
                    "validator_id": f"lilrae-{self.catalog.provider}-request",
                    "validator_version": "1",
                },
                "targets": targets,
            }
        )
        constraints = {
            "build_version": self.catalog.build_version,
            "executable_sha256": self.catalog.executable_sha256,
            "request_profiles": rfc8785.dumps(
                self.catalog.model_dump(mode="json")
            ).decode(),
            "served_identity": "unattested",
            "model_identity": "requested identifier; aliases and date suffixes do not attest immutable snapshots",
            "seed_determinism": "not-guaranteed",
            "usage": "provider-reported when available; missing is unknown, never zero",
            "reasoning_support": {
                "claude": "reviewed effort; disabled reasoning and budgets unsupported",
                "codex": "reviewed effort or disabled; budgets unsupported",
                "opencode": "reviewed model-specific effort, budget or disabled",
            }[self.catalog.provider],
            "effective_context": (
                "authored assets only; native harness, tools and effective request are not attested"
            ),
            "request_application": (
                "requires a compatible sealed-configuration executor; admission is not execution evidence"
            ),
            "retry_policy": "no adapter fallback; native internal retries are not an exactly-once guarantee",
        }
        if self.catalog.provider != "opencode":
            constraints["action_execution"] = "none; decision source only"
        return participant_manifest(
            name=f"lilrae-{self.catalog.provider}",
            version=self.catalog.implementation_version,
            decision_only=self.catalog.provider != "opencode",
            registry=registry,
            constraints=constraints,
        )

    def for_scenario(self, scenario: ScenarioContent) -> ParticipantRequestOwner:
        domains = {
            entry.control_context.slot_id: entry.control_context.references
            for entry in self.manifest.configuration_registry.targets.values()
            if entry.control_context is not None
        }
        return type(self)(
            catalog=self.catalog, context_domains=domains, scenario=scenario
        )

    def validate_control_context_reference(
        self,
        participant_address: str,
        selection: ParticipantControlContextConfigurationSelectionModel,
    ) -> None:
        self._context_validator.validate_control_context_reference(
            participant_address, selection
        )

    def validate_and_normalize(
        self, configuration: ParticipantConfigurationModel
    ) -> ParticipantConfigurationModel:
        manifest = self.manifest
        registry = manifest.configuration_registry
        if (
            configuration.implementation_identity != manifest.identity
            or configuration.manifest_version != manifest.schema_version
            or configuration.owner != registry.owner
        ):
            raise ValueError(
                "participant configuration owner or identity is inconsistent"
            )
        values = {
            entry.target_id: entry.value.value
            for entry in configuration.values
            if entry.value.kind == "literal"
        }
        if set(values) != set(registry.targets) or len(values) != len(
            configuration.values
        ):
            raise ValueError("participant request configuration is incomplete")
        for entry in configuration.values:
            self._validate_target(entry, registry.resolve(entry.target_id))
        self._profile(values)
        return configuration

    @staticmethod
    def _validate_target(
        entry: RealizedConfigurationValueModel,
        declaration: ConfigurationTargetDeclarationModel,
    ) -> None:
        """Validate one declared value and its exact optional context commitment."""
        if entry.value_type != declaration.value_type:
            raise ValueError("participant request type is inconsistent")
        declaration.validate_value(entry.value)
        if (
            declaration.control_context is None
            and entry.control_context_selection is not None
        ):
            raise ValueError(
                "participant context metadata is not declared for this target"
            )
        if declaration.control_context is not None:
            selected = entry.control_context_selection
            if (
                selected is None
                or selected.slot_id != declaration.control_context.slot_id
                or selected.declaration_ref != entry.value.value
                or selected.asset_ref
                != declaration.control_context.references[entry.value.value]
            ):
                raise ValueError("participant context commitment is inconsistent")

    def _profile(self, values: Mapping[str, object]) -> RequestProfile:
        for profile in self.catalog.profiles:
            if profile.reference == values["request.profile"]:
                if (
                    profile.model != values[self.model_target]
                    or profile.digest != values["request.profile_digest"]
                ):
                    raise ValueError(
                        "participant model or request profile commitment is incompatible"
                    )
                return profile
        raise ValueError("participant request profile is not admitted")

    def verify_content(
        self,
        result: ParticipantConfigurationResultModel,
        *,
        participant_address: str,
        contents: Mapping[str, bytes],
    ) -> tuple[str, ...]:
        """Verify already resolved bytes without acquiring or disclosing an asset."""
        result = ParticipantConfigurationResultModel.model_validate_json(
            result.model_dump_json()
        )
        if (
            result.participant_address != participant_address
            or result.manifest_digest != canonical_contract_digest(self.manifest)
        ):
            raise ValueError(
                "participant configuration does not match the selected manifest or participant"
            )
        self.validate_and_normalize(result.configuration)
        selected = {
            entry.control_context_selection.slot_id: entry.control_context_selection
            for entry in result.configuration.values
            if entry.control_context_selection is not None
        }
        values = {
            entry.target_id: entry.value.value for entry in result.configuration.values
        }
        profile = self._profile(values)
        if set(contents) != set(profile.context_order):
            raise ValueError("participant content slots are incomplete")
        index = build_declaration_index(self._scenario)
        output = []
        for slot in profile.context_order:
            selection = selected[slot]
            self.validate_control_context_reference(participant_address, selection)
            declaration = index.declaration_for(selection.declaration_ref)
            asset = self._scenario.control_context_assets[declaration.model_tokens[1]]
            output.append(decode_context_asset(asset, contents[slot]))
        if any(token in "".join(output) for token in profile.unresolved_placeholders):
            raise ValueError("participant content contains an unresolved placeholder")
        return tuple(output)

    def prepare_request(
        self,
        result: ParticipantConfigurationResultModel,
        *,
        participant_address: str,
        contents: Mapping[str, bytes],
    ) -> ParticipantRequest:
        """Seal verified, ordered content for an existing native adapter."""
        result = ParticipantConfigurationResultModel.model_validate_json(
            result.model_dump_json()
        )
        content = self.verify_content(
            result, participant_address=participant_address, contents=contents
        )
        prompt = "".join(content)
        values = {
            entry.target_id: entry.value.value for entry in result.configuration.values
        }
        profile = self._profile(values)
        selected = {
            entry.control_context_selection.slot_id: entry.control_context_selection
            for entry in result.configuration.values
            if entry.control_context_selection is not None
        }
        index = build_declaration_index(self._scenario)
        descriptors = tuple(
            self._scenario.control_context_assets[
                index.declaration_for(selected[slot].declaration_ref).model_tokens[1]
            ].model_dump_json()
            for slot in profile.context_order
        )
        return ParticipantRequest(
            provider=self.catalog.provider,
            profile=profile,
            build_version=self.catalog.build_version,
            executable_sha256=self.catalog.executable_sha256,
            prompt=prompt,
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            configuration_json=result.model_dump_json(),
            manifest_json=self._manifest_json,
            context_descriptors=descriptors,
            context_contents=content,
        )
