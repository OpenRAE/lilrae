"""Validation of the startup plan that an adapter returns."""

from __future__ import annotations

from pathlib import PurePosixPath
import re

from aptl.core.deployment.realization import valid_environment_variable_name
from aptl.core.scenario_bundle import ScenarioBundle
from aptl.backends._scenario_environment import (
    ScenarioEnvironmentFixture,
    ScenarioStartupProviderError,
    references_accounts,
    resolved_environment_fixtures,
    validated_aliases as _validated_aliases,
    validated_environment_fixtures,
    validated_adapter_grants,
)
from aptl.backends._scenario_startup_hooks import StartupCapability, StartupHook
from aptl.backends._scenario_startup_model import (
    ContainerEnvironmentBinding,
    McpServerCredentials,
    ScenarioStartupPlan,
)

DOCKER_TRANSPORT_KEYS = frozenset(
    ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_SSH_IDENTITY")
)


def _safe_relative_script(value: object) -> str:
    """Reject absolute or escaping seed script paths from an adapter."""

    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ScenarioStartupProviderError("provider-result-invalid")
    return str(path)


def _account_resolved_fixtures(value: object, bundle: ScenarioBundle | None) -> object:
    """Resolve account-referenced fixtures against the admitted SDL once."""

    if not references_accounts(value):
        return value
    if bundle is None:
        raise ScenarioStartupProviderError("provider-result-invalid")
    from aptl.backends.raes_declared_credentials import scenario_accounts

    accounts = (
        bundle.trial.scenario.accounts
        if bundle.trial
        else scenario_accounts(bundle.sdl_path)
    )
    return resolved_environment_fixtures(value, accounts)


def _validated_environment_fixtures(
    value: object,
) -> tuple[ScenarioEnvironmentFixture, ...]:
    """Validate fixed values without copying their bytes into diagnostics."""

    return validated_environment_fixtures(value, DOCKER_TRANSPORT_KEYS)


def _validated_container_environment(
    value: object,
) -> tuple[ContainerEnvironmentBinding, ...]:
    """Validate semantic container bindings before exposing them to seed."""

    if not isinstance(value, tuple) or any(
        not isinstance(item, ContainerEnvironmentBinding) for item in value
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    if any(
        not valid_environment_variable_name(item.variable)
        or item.variable in DOCKER_TRANSPORT_KEYS
        or not item.semantic_name
        or len(item.semantic_name) > 255
        or any(char.isspace() for char in item.semantic_name)
        for item in value
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    if len({item.variable for item in value}) != len(value):
        raise ScenarioStartupProviderError("provider-result-invalid")
    return tuple(value)


def _validated_profile_groups(
    profiles: object, activation: object
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Validate required and activated Compose profiles as one contract."""

    if any(
        not isinstance(group, tuple)
        or not group
        or any(not isinstance(item, str) or not item for item in group)
        or len(set(group)) != len(group)
        for group in (profiles, activation)
    ) or not set(activation).issubset(profiles):
        raise ScenarioStartupProviderError("provider-result-invalid")
    return profiles, activation


def _validated_seed(
    value: ScenarioStartupPlan,
) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """Validate the seed script and profiles, or require no seed fields."""

    if value.seed_script is None:
        if (
            value.required_profiles != ()
            or value.activation_profiles != ()
            or value.seed_environment_keys != ()
            or value.container_environment != ()
        ):
            raise ScenarioStartupProviderError("provider-result-invalid")
        return None, (), ()
    profiles, activation = _validated_profile_groups(
        value.required_profiles, value.activation_profiles
    )
    return _safe_relative_script(value.seed_script), profiles, activation


def _validated_seed_keys(value: object) -> tuple[str, ...]:
    """Allow declared seed values without Docker transport overrides."""

    if (
        not isinstance(value, tuple)
        or any(
            not isinstance(key, str)
            or not valid_environment_variable_name(key)
            or key in DOCKER_TRANSPORT_KEYS
            for key in value
        )
        or len(set(value)) != len(value)
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    return value


def _valid_mcp_credential(item: object) -> bool:
    """Check one bounded MCP client's declared credential names."""

    return (
        isinstance(item, McpServerCredentials)
        and bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", item.server_id))
        and isinstance(item.environment_keys, tuple)
        and bool(item.environment_keys)
        and all(
            isinstance(key, str) and valid_environment_variable_name(key)
            for key in item.environment_keys
        )
        and len(set(item.environment_keys)) == len(item.environment_keys)
    )


def _validated_mcp_keys(value: object) -> tuple[McpServerCredentials, ...]:
    """Require unique, well-formed client credential declarations."""

    if (
        not isinstance(value, tuple)
        or any(not _valid_mcp_credential(item) for item in value)
        or len({item.server_id for item in value}) != len(value)
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    return value


def _validated_minimum_max_map_count(value: object) -> int | None:
    """Accept an omitted demand or a bounded positive kernel setting."""
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= 2**31 - 1:
        raise ScenarioStartupProviderError("provider-result-invalid")
    return value


def _validated_plan(
    value: object, bundle: ScenarioBundle | None = None
) -> ScenarioStartupPlan:
    """Normalize one adapter plan and reject malformed profile sets."""

    if not isinstance(value, ScenarioStartupPlan):
        raise ScenarioStartupProviderError("provider-result-invalid")
    seed_script, profiles, activation = _validated_seed(value)
    if not isinstance(value.lifecycle_capabilities, frozenset) or any(
        not isinstance(item, StartupCapability) for item in value.lifecycle_capabilities
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    if not isinstance(value.startup_hooks, frozenset) or any(
        not isinstance(item, StartupHook) for item in value.startup_hooks
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    seed_keys = _validated_seed_keys(value.seed_environment_keys)
    mcp_keys = _validated_mcp_keys(value.mcp_server_keys)
    if not isinstance(value.native_mcp_ingress, bool) or (
        value.mcp_build_script is not None
        and not isinstance(value.mcp_build_script, str)
    ):
        raise ScenarioStartupProviderError("provider-result-invalid")
    minimum = _validated_minimum_max_map_count(value.minimum_max_map_count)
    aliases = _validated_aliases(value.environment_aliases)
    fixtures = _validated_environment_fixtures(
        _account_resolved_fixtures(value.environment_fixtures, bundle)
    )
    supplied = {item.name for item in fixtures} | {item.target for item in aliases}
    identity = getattr(bundle, "pack_identity", None)
    grants = validated_adapter_grants(
        value.environment_grants, supplied, getattr(identity, "pack_id", None)
    )
    return ScenarioStartupPlan(
        seed_script=seed_script,
        required_profiles=tuple(profiles),
        activation_profiles=tuple(activation),
        environment_aliases=aliases,
        environment_fixtures=fixtures,
        container_environment=_validated_container_environment(
            value.container_environment
        ),
        lifecycle_capabilities=frozenset(value.lifecycle_capabilities),
        startup_hooks=frozenset(value.startup_hooks),
        seed_environment_keys=seed_keys,
        mcp_build_script=(
            _safe_relative_script(value.mcp_build_script)
            if value.mcp_build_script is not None
            else None
        ),
        mcp_server_keys=tuple(mcp_keys),
        native_mcp_ingress=value.native_mcp_ingress,
        minimum_max_map_count=minimum,
        environment_grants=grants,
    )
