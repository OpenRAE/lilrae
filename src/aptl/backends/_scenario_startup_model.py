"""Data contracts re-exported by the public scenario startup owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from aptl.backends._scenario_environment import (
    AccountCredentialFixture,
    EnvironmentAlias,
    ScenarioEnvironmentFixture,
)
from aptl.backends._scenario_startup_hooks import (
    StartupCapability,
    StartupHook,
    StartupHookContext,
)
from aptl.backends.scenario_family import AdmittedFamilyTrial
from aptl.backends.scenario_runtime_hooks import ScenarioRuntimeOperations
from aptl.core.scenario_bundle import PackIdentity, ScenarioBundle

if TYPE_CHECKING:
    from aptl.backends.scenario_startup_policy import ScenarioComposeStartupPolicy
    from aptl.backends.scenario_service_policy import ScenarioComposeServicePolicy
    from aptl.backends.raes_realization_model import NodeRealization


class ScenarioStartupProvider(Protocol):
    """Public family startup, fixed hooks, realization and observation surface."""

    def resolve(self, bundle: ScenarioBundle) -> ScenarioStartupPlan: ...
    def prepare_stack_environment(self, context: StartupHookContext) -> object: ...
    def before_backend_retry(self, context: StartupHookContext) -> object: ...
    def reset(self, context: StartupHookContext) -> object: ...
    def compose_startup_policy(self) -> ScenarioComposeStartupPolicy: ...
    def compose_service_policy(self) -> ScenarioComposeServicePolicy: ...
    def realize_runtime(
        self,
        operations: ScenarioRuntimeOperations,
        nodes: tuple[NodeRealization, ...],
        *,
        trial: AdmittedFamilyTrial,
    ) -> list[str]: ...
    def observe_runtime(
        self,
        operations: ScenarioRuntimeOperations,
        node: object,
        *,
        trial: AdmittedFamilyTrial,
    ) -> dict[tuple[str, ...], object]: ...


@dataclass(frozen=True, order=True)
class ContainerEnvironmentBinding:
    """Expose one receipt-resolved semantic container to a seed subprocess."""

    variable: str
    semantic_name: str


@dataclass(frozen=True)
class McpServerCredentials:
    """One client server's explicitly authorized dynamic environment keys."""

    server_id: str
    environment_keys: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioStartupPlan:
    """Validated scenario-specific work executed by the generic lifecycle."""

    seed_script: str
    required_profiles: tuple[str, ...]
    activation_profiles: tuple[str, ...]
    environment_aliases: tuple[EnvironmentAlias, ...] = ()
    # An adapter may name an SDL account credential instead of a value; core
    # resolves it against the admitted SDL, so a validated plan holds values.
    environment_fixtures: tuple[
        ScenarioEnvironmentFixture | AccountCredentialFixture, ...
    ] = ()
    container_environment: tuple[ContainerEnvironmentBinding, ...] = ()
    lifecycle_capabilities: frozenset[StartupCapability] = frozenset()
    startup_hooks: frozenset[StartupHook] = frozenset()
    seed_environment_keys: tuple[str, ...] = ()
    mcp_build_script: str | None = None
    mcp_server_keys: tuple[McpServerCredentials, ...] = ()
    native_mcp_ingress: bool = False
    minimum_max_map_count: int | None = None


@dataclass(frozen=True)
class ScenarioStartupSelection:
    """The exact provider and validated plan selected for one admission."""

    identity: PackIdentity | None
    provider: object | None = field(repr=False, compare=False)
    plan: ScenarioStartupPlan | None
    provenance: StartupProviderProvenance | None = None
    trial: AdmittedFamilyTrial | None = field(default=None, repr=False)


@dataclass(frozen=True)
class StartupProviderProvenance:
    """Installed distribution identity used to rediscover a reset hook."""

    distribution: str
    distribution_version: str
    entry_point: str
    family_target: str = ""
