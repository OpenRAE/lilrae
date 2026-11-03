"""Manifest-owned OpenCode configuration and exact prompt delivery checks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from raes_contracts.contracts import (
    ConfigurationTargetRegistryModel,
    ParticipantConfigurationModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
)
from raes_contracts.canonical import canonical_contract_digest

from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor, OpenCodeOptions
from aptl.core.participant_requests.manifest import participant_manifest
from aptl.core.opencode import OpenCodeBuild, OpenRouterRoute, SUPPORTED_OPENCODE_BUILD

_TARGETS = {
    "model": "string",
    "prompt_ref": "string",
    "prompt_sha256": "string",
    "timeout_seconds": "integer",
    "gateway_endpoint": "string",
    "serving_provider": "string",
    "max_output_tokens": "integer",
}


def opencode_manifest(
    *,
    version: str,
    build: OpenCodeBuild = SUPPORTED_OPENCODE_BUILD,
) -> ParticipantImplementationManifestModel:
    """Describe the installed harness, without claiming a provider model identity."""
    registry = ConfigurationTargetRegistryModel.model_validate(
        {
            "owner": {
                "contract_id": "participant-implementation-manifest/v1",
                "contract_version": "1",
                "validator_id": "lilrae-opencode",
                "validator_version": "2",
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
        }
    )
    return participant_manifest(
        name="lilrae-opencode",
        version=version,
        decision_only=False,
        registry=registry,
        constraints={
            "opencode_version": build.version,
            "opencode_executable_sha256": build.executable_sha256,
            "model_identity": "requested provider/model identifier; provider resolution is not attested",
            "prompt_commitment": "sha256 of exact UTF-8 stdin bytes",
        },
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


def _validate_prompt_commitment(values: dict[str, object]) -> None:
    """Require a prompt artifact reference and an exact byte commitment."""
    if not isinstance(values["prompt_ref"], str) or not values["prompt_ref"].strip():
        raise ValueError("participant prompt reference is invalid")
    if not isinstance(values["prompt_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", values["prompt_sha256"]
    ):
        raise ValueError("participant prompt commitment is invalid")


def _validate_request_limits(values: dict[str, object]) -> None:
    """Bound integer request controls before native launch."""
    timeout = values["timeout_seconds"]
    tokens = values["max_output_tokens"]
    if type(tokens) is not int or not 1 <= tokens <= 32768:
        raise ValueError("participant output token limit is invalid")
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("participant timeout must be between 1 and 3600 seconds")


@dataclass(frozen=True)
class OpenCodeConfigurationValidator:
    """Validate against an operator-admitted model domain, never a study catalog."""

    supported_models: frozenset[str]

    def validate_and_normalize(
        self, configuration: ParticipantConfigurationModel
    ) -> ParticipantConfigurationModel:
        """Validate route, prompt commitment, model selection, and request bounds."""
        values = _values(configuration)
        if values["model"] not in self.supported_models:
            raise ValueError("participant model is not admitted")
        if not isinstance(values["model"], str) or not values["model"].startswith(
            "openrouter/"
        ):
            raise ValueError("participant model must select OpenRouter")
        OpenRouterRoute(
            endpoint=values["gateway_endpoint"],
            serving_provider=values["serving_provider"],
        )
        _validate_prompt_commitment(values)
        _validate_request_limits(values)
        return configuration


def _validate_configuration_result(
    configuration: ParticipantConfigurationResultModel,
    manifest: ParticipantImplementationManifestModel,
    build: OpenCodeBuild,
) -> None:
    """Verify the configuration's owner, target types, and committed identity."""
    if (
        configuration.manifest_digest != canonical_contract_digest(manifest)
        or configuration.configuration.implementation_identity != manifest.identity
        or configuration.configuration_digest
        != canonical_contract_digest(configuration.configuration)
        or manifest != opencode_manifest(version=manifest.identity.version, build=build)
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
    timeout_seconds: float | None = None,
) -> LilraeOpenCodeExecutor:
    """Verify the sealed result and artifact commitment before constructing a harness."""
    if options.request is not None:
        return _expanded_executor(
            configuration,
            manifest,
            prompt,
            prompt_ref,
            supported_models,
            options,
            timeout_seconds,
        )
    _validate_configuration_result(configuration, manifest, options.build)
    values = _values(configuration.configuration)
    if timeout_seconds is not None and timeout_seconds != values["timeout_seconds"]:
        raise ValueError("participant deadline differs from its admitted configuration")
    if options.route != OpenRouterRoute(
        endpoint=values["gateway_endpoint"], serving_provider=values["serving_provider"]
    ):
        raise ValueError("participant route differs from its admitted configuration")
    if options.max_output_tokens != values["max_output_tokens"]:
        raise ValueError(
            "participant token limit differs from its admitted configuration"
        )
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


def _expanded_executor(
    configuration: ParticipantConfigurationResultModel,
    manifest: ParticipantImplementationManifestModel,
    prompt: str,
    prompt_ref: str,
    supported_models: frozenset[str],
    options: OpenCodeOptions,
    timeout_seconds: float | None,
) -> LilraeOpenCodeExecutor:
    """Match the expanded request to the installed factory's exact trusted inputs."""
    request = options.request
    request.validate()
    if (
        manifest != request.manifest
        or configuration != request.configuration_result
        or prompt != request.prompt
        or prompt_ref != request.prompt_ref
        or request.profile.model not in supported_models
        or timeout_seconds is None
    ):
        raise ValueError(
            "participant request is incompatible with its installed configuration"
        )
    return LilraeOpenCodeExecutor(
        options=options,
        model=request.profile.model,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        configuration_result=configuration,
    )
