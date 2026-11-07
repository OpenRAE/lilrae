"""Lazy, content-identified startup adapters for scenario enrichment."""

from __future__ import annotations

from dataclasses import replace
from importlib import metadata
from pathlib import Path, PurePosixPath

from aptl.core.scenario_bundle import PackIdentity, ScenarioBundle
from aptl.utils.logging import get_logger
from aptl.backends._scenario_environment import (
    AccountCredentialFixture,
    EnvironmentAlias,
    ScenarioEnvironmentFixture,
    ScenarioStartupProviderError,
)

from aptl.backends._scenario_startup_hooks import (
    StartupCapability,
    StartupHook,
    StartupHookContext,
    StartupPreparationPhase,
)

from aptl.backends._scenario_startup_model import (
    ContainerEnvironmentBinding,
    McpServerCredentials,
    ScenarioStartupPlan,
    ScenarioStartupProvider,
    ScenarioStartupSelection,
    StartupProviderProvenance,
)
from aptl.backends._scenario_startup_plan import (
    DOCKER_TRANSPORT_KEYS,
    _validated_plan,
)

log = get_logger("scenario-startup")

ENTRY_POINT_GROUP = "aptl.scenario_startup"
EXTENSION_API_VERSION = "1"


def _entry_points() -> list[metadata.EntryPoint]:
    """Find installed startup providers without importing them eagerly."""

    return list(metadata.entry_points(group=ENTRY_POINT_GROUP))


def _load(entry_point: metadata.EntryPoint) -> object:
    """Load one provider and redact implementation failures."""

    try:
        provider = entry_point.load()
        if isinstance(provider, type):
            provider = provider()
    except Exception as exc:
        log.warning(
            "scenario startup provider load failed: selector=%s exception=%s",
            entry_point.name,
            type(exc).__name__,
        )
        raise ScenarioStartupProviderError("provider-load-failed") from None
    return provider


def _provenance(entry_point: metadata.EntryPoint) -> StartupProviderProvenance:
    """Capture host-observed provenance for restart-safe hook dispatch."""

    dist = getattr(entry_point, "dist", None)
    return StartupProviderProvenance(
        distribution=str(getattr(dist, "name", "") or ""),
        distribution_version=str(getattr(dist, "version", "") or ""),
        entry_point=entry_point.name,
    )


def _string_tuple(provider: object, name: str) -> tuple[str, ...]:
    """Require a provider identity field to be a nonempty-string tuple."""

    value = getattr(provider, name, None)
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ScenarioStartupProviderError("provider-malformed")
    return value


def _compatible_identity(provider: object, identity: PackIdentity) -> bool:
    """Check the extension contract and immutable pack identity."""

    if (
        getattr(provider, "extension_api_version", None) != EXTENSION_API_VERSION
        or getattr(provider, "supported_pack_id", None) != identity.pack_id
        or not callable(getattr(provider, "resolve", None))
    ):
        raise ScenarioStartupProviderError("provider-malformed")
    return identity.pack_version in _string_tuple(
        provider, "supported_pack_versions"
    ) and identity.set_digest in _string_tuple(provider, "supported_pack_set_digests")


def _compatible(provider: object, bundle: ScenarioBundle) -> bool:
    """Match an adapter only when the bundle carries a qualified pack."""

    identity = bundle.pack_identity
    return identity is not None and _compatible_identity(provider, identity)


def select_scenario_startup(bundle: ScenarioBundle) -> ScenarioStartupSelection:
    """Select one exact adapter once for all stages of an admitted start."""

    identity = bundle.pack_identity
    if bundle.trial is not None:
        from aptl.backends.scenario_family import (
            resolve_family_contribution,
            encode_family_target,
        )

        try:
            selected, plan = resolve_family_contribution(
                ENTRY_POINT_GROUP,
                bundle.trial,
                bundle,
                lambda value: _validated_plan(value, bundle),
            )
            _validate_hook_methods(selected.provider, plan)
        except ValueError as exc:
            raise ScenarioStartupProviderError(str(exc)) from None
        return ScenarioStartupSelection(
            identity,
            selected.provider,
            plan,
            StartupProviderProvenance(
                selected.distribution,
                selected.distribution_version,
                selected.entry_point,
                encode_family_target(bundle.trial.target),
            ),
            bundle.trial,
        )
    return _select_installed_startup(bundle)


def _select_installed_startup(bundle: ScenarioBundle) -> ScenarioStartupSelection:
    """Select a content-qualified legacy startup plan without family input."""

    identity = bundle.pack_identity
    if identity is None:
        return ScenarioStartupSelection(identity, None, None)
    candidates = [
        entry_point
        for entry_point in _entry_points()
        if entry_point.name == identity.pack_id
    ]
    compatible: list[tuple[metadata.EntryPoint, object]] = []
    for entry_point in candidates:
        provider = _load(entry_point)
        if _compatible(provider, bundle):
            compatible.append((entry_point, provider))
    if len(compatible) > 1:
        raise ScenarioStartupProviderError("provider-ambiguous")
    if not compatible:
        return ScenarioStartupSelection(identity, None, None)
    try:
        entry_point, provider = compatible[0]
        plan = _validated_plan(provider.resolve(bundle), bundle)
        _validate_hook_methods(provider, plan)
        return ScenarioStartupSelection(
            identity,
            provider,
            plan,
            _provenance(entry_point),
        )
    except ScenarioStartupProviderError:
        raise
    except Exception as exc:
        log.warning(
            "scenario startup provider resolve failed: selector=%s exception=%s",
            identity.pack_id,
            type(exc).__name__,
        )
        raise ScenarioStartupProviderError("provider-resolve-failed") from None


def _validate_hook_methods(provider: object, plan: ScenarioStartupPlan) -> None:
    """Require a callable implementation for every declared hook slot."""

    methods = {
        StartupHook.STACK_ENVIRONMENT: "prepare_stack_environment",
        StartupHook.RESET: "reset",
    }
    if any(
        hook in plan.startup_hooks and not callable(getattr(provider, method, None))
        for hook, method in methods.items()
    ):
        raise ScenarioStartupProviderError("provider-malformed")


def run_startup_hook(
    selection: ScenarioStartupSelection | None,
    hook: StartupHook,
    context: StartupHookContext,
) -> object | None:
    """Invoke one admitted fixed hook, normalizing adapter failures."""

    if (
        selection is None
        or selection.plan is None
        or hook not in selection.plan.startup_hooks
    ):
        return None
    method = {
        StartupHook.STACK_ENVIRONMENT: "prepare_stack_environment",
        StartupHook.RESET: "reset",
    }.get(hook)
    if method is None:
        return None
    if selection.trial is not None:
        from types import SimpleNamespace
        from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations

        nodes = tuple(
            SimpleNamespace(name=name) for name in selection.trial.scenario.nodes
        )
        context = replace(
            context,
            backend=AdmittedRuntimeOperations(context.backend, nodes),
            project_dir=None,
            trial=selection.trial,
        )
    try:
        return getattr(selection.provider, method)(context)
    except Exception as exc:
        log.warning(
            "scenario startup hook failed: hook=%s exception=%s",
            hook.value,
            type(exc).__name__,
        )
        raise ScenarioStartupProviderError("provider-hook-failed") from None


def resolve_scenario_startup(bundle: ScenarioBundle) -> ScenarioStartupPlan | None:
    """Resolve a plan for independent callers outside a lab admission."""

    return select_scenario_startup(bundle).plan


from aptl.backends._scenario_startup_runtime import (
    observe_scenario_runtime_concerns,
    run_persisted_startup_reset,
    run_scenario_runtime,
    selected_runtime_provider,
)
from aptl.backends.scenario_runtime_selection import (
    ScenarioRuntimeSelection,
    scenario_runtime_selection_details,
)


def seed_script_path(project_dir: Path, plan: ScenarioStartupPlan) -> Path:
    """Resolve a validated plan script beneath the materialized project root."""
    if plan.seed_script is None:
        raise ScenarioStartupProviderError("provider-seed-unconfigured")
    root = project_dir.resolve()
    candidate = root.joinpath(*PurePosixPath(plan.seed_script).parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ScenarioStartupProviderError("provider-result-invalid") from exc
    return candidate


__all__ = [
    "ENTRY_POINT_GROUP",
    "EXTENSION_API_VERSION",
    "ContainerEnvironmentBinding",
    "AccountCredentialFixture",
    "EnvironmentAlias",
    "ScenarioEnvironmentFixture",
    "McpServerCredentials",
    "ScenarioRuntimeSelection",
    "ScenarioStartupPlan",
    "ScenarioStartupSelection",
    "ScenarioStartupProvider",
    "StartupProviderProvenance",
    "ScenarioStartupProviderError",
    "StartupCapability",
    "StartupHook",
    "StartupHookContext",
    "StartupPreparationPhase",
    "resolve_scenario_startup",
    "select_scenario_startup",
    "run_scenario_runtime",
    "scenario_runtime_selection_details",
    "selected_runtime_provider",
    "run_persisted_startup_reset",
    "observe_scenario_runtime_concerns",
    "run_startup_hook",
    "seed_script_path",
]
