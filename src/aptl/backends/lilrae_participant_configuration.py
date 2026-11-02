"""Manifest-owned OpenCode configuration and exact prompt delivery checks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from raes_contracts.contracts import (
    ParticipantConfigurationModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
)
from raes_contracts.canonical import canonical_contract_digest

from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor, OpenCodeOptions

_TARGETS = {
    "model": "string",
    "prompt_ref": "string",
    "prompt_sha256": "string",
    "timeout_seconds": "integer",
}


def opencode_manifest(*, version: str) -> ParticipantImplementationManifestModel:
    """Describe the installed harness, without claiming a provider model identity."""
    contracts = [
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
    ]
    return ParticipantImplementationManifestModel.model_validate(
        {
            "identity": {"name": "lilrae-opencode", "version": version},
            "implementation_kind": "agent",
            "supported_contract_versions": [
                "participant-implementation-manifest-v1",
                "participant-implementation-provenance-v1",
                "experiment-binding-descriptors-v1",
                "participant-configuration-result-v1",
                *contracts,
            ],
            "compatibility": {
                "participant_runtimes": ["aptl"],
                "processors": ["raes-reference-processor"],
                "backends": ["aptl"],
            },
            "concept_bindings": [
                {"scope": scope, "family": family}
                for scope, family in (
                    ("implementation_kind", "apparatus-declarations"),
                    (
                        "capabilities.supported_participant_contracts",
                        "apparatus-declarations",
                    ),
                    (
                        "capabilities.supported_decision_surface_modes",
                        "apparatus-declarations",
                    ),
                    (
                        "capabilities.tool_affordance_expectations",
                        "tools-and-artifacts",
                    ),
                    ("capabilities.exposure_policy_kinds", "provenance-and-evidence"),
                )
            ],
            "capabilities": {
                "supported_participant_contracts": contracts,
                "supported_decision_surface_modes": ["autonomous"],
                "tool_affordance_expectations": ["x-lilrae:verified-workbench-profile"],
                "exposure_policy_kinds": ["task-statement", "observation-stream"],
            },
            "constraints": {
                "model_identity": "requested provider/model identifier; provider resolution is not attested",
                "prompt_commitment": "sha256 of exact UTF-8 stdin bytes",
            },
            "configuration_registry": {
                "owner": {
                    "contract_id": "participant-implementation-manifest/v1",
                    "contract_version": "1",
                    "validator_id": "lilrae-opencode",
                    "validator_version": "1",
                },
                "targets": {
                    name: {
                        "target_id": name,
                        "value_type": kind,
                        "allowed_value_kinds": ["literal"],
                        "sensitivity": "internal",
                    }
                    for name, kind in _TARGETS.items()
                },
            },
        }
    )


def _values(configuration: ParticipantConfigurationModel) -> dict[str, object]:
    """Require exactly the manifest's literal configuration targets."""
    values = {
        entry.target_id: entry.value.value
        for entry in configuration.values
        if entry.value.kind == "literal"
    }
    if set(values) != set(_TARGETS) or len(configuration.values) != len(_TARGETS):
        raise ValueError("incomplete OpenCode participant configuration")
    return values


@dataclass(frozen=True)
class OpenCodeConfigurationValidator:
    """Validate against an operator-admitted model domain, never a study catalog."""

    supported_models: frozenset[str]

    def validate_and_normalize(
        self, configuration: ParticipantConfigurationModel
    ) -> ParticipantConfigurationModel:
        values = _values(configuration)
        if values["model"] not in self.supported_models:
            raise ValueError("participant model is not admitted")
        if (
            not isinstance(values["prompt_ref"], str)
            or not values["prompt_ref"].strip()
        ):
            raise ValueError("participant prompt reference is invalid")
        if not isinstance(values["prompt_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", values["prompt_sha256"]
        ):
            raise ValueError("participant prompt commitment is invalid")
        timeout = values["timeout_seconds"]
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError("participant timeout must be between 1 and 3600 seconds")
        return configuration


def _validate_configuration_result(
    configuration: ParticipantConfigurationResultModel,
    manifest: ParticipantImplementationManifestModel,
) -> None:
    """Verify the configuration's owner, target types, and committed identity."""
    if (
        configuration.manifest_digest != canonical_contract_digest(manifest)
        or configuration.configuration.implementation_identity != manifest.identity
        or configuration.configuration_digest
        != canonical_contract_digest(configuration.configuration)
        or manifest != opencode_manifest(version=manifest.identity.version)
        or configuration.configuration.owner != manifest.configuration_registry.owner
        or configuration.configuration.manifest_version != manifest.schema_version
    ):
        raise ValueError("participant configuration manifest or digest is inconsistent")
    for entry in configuration.configuration.values:
        declaration = manifest.configuration_registry.resolve(entry.target_id)
        if entry.value_type != declaration.value_type:
            raise ValueError("participant configuration target type is inconsistent")
        declaration.validate_value(entry.value)


def configured_opencode_executor(
    *,
    configuration: ParticipantConfigurationResultModel,
    manifest: ParticipantImplementationManifestModel,
    prompt: str,
    prompt_ref: str,
    supported_models: frozenset[str],
    options: OpenCodeOptions,
) -> LilraeOpenCodeExecutor:
    """Verify the sealed result and artifact commitment before constructing a harness."""
    _validate_configuration_result(configuration, manifest)
    values = _values(configuration.configuration)
    if (
        prompt_ref != values["prompt_ref"]
        or hashlib.sha256(prompt.encode("utf-8")).hexdigest() != values["prompt_sha256"]
    ):
        raise ValueError("participant prompt does not match its committed artifact")
    OpenCodeConfigurationValidator(supported_models).validate_and_normalize(
        configuration.configuration
    )
    return LilraeOpenCodeExecutor(
        model=values["model"],
        prompt=prompt,
        timeout_seconds=values["timeout_seconds"],
        configuration_result=configuration,
        options=options,
    )
