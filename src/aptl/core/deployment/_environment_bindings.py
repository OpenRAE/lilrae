"""Explicit sources for declared runtime environment variables (issue #965).

A matching name grants no access. Each declared variable has an explicit source:

- ``generated``: the node-bound artifact output named by ``value_from``;
- ``authored``: the exact scenario value, or empty for a value-less setting;
- ``grant:<kind>:<variable>``: the configured pack/node/variable source;
- ``startup-adapter:project-env-file:<variable>``: the identity-bound adapter's
  explicit grant to this consumer.

Only value-less ``operator_secret``, ``redacted`` and ``secret_fixture`` entries
take external values. Preflight snapshots selected sources once and refuses
missing, empty or unrepresentable values before mutation. Diagnostics identify
the consumer and source, never the value. See ``docs/deployment.md`` for details.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from raes_contracts.planning import RealizationAuthorityMode

from aptl.core.config import EnvironmentGrant
from aptl.core.deployment._generated_environment_bindings import (
    generated_environment_names,
)
from aptl.core.deployment._realization_primitives import (
    EnvironmentDeliveryRefused,
    environment_file_line,
    valid_environment_variable_name,
)
from aptl.core.env import load_dotenv
from aptl.utils.logging import get_logger

if TYPE_CHECKING:
    from aptl.backends.raes_base_substrate import BaseContainerSpec
    from aptl.core.deployment.realization import DeploymentRealizationSpec

log = get_logger("deployment.environment_bindings")

#: Classifications whose value-less declaration is supplied from outside.
OUT_OF_BAND_CLASSIFICATIONS = frozenset(
    {"operator_secret", "redacted", "secret_fixture"}
)
#: Container label naming the variables APTL bound, so a container that still
#: carries a variable no longer bound is recreated rather than reused.
ENVIRONMENT_NAMES_LABEL = "aptl.environment.names"
AUTHORED_SOURCE = "authored"
GENERATED_SOURCE = "generated"
_ADAPTER_SOURCE = "startup-adapter:project-env-file:"


class EnvironmentBindingError(ValueError):
    """A declared variable has no source, or its source holds no value."""


@dataclass(frozen=True)
class EnvironmentBinding:
    """One delivered variable and the identity of its source."""

    name: str
    source: str
    value: str = field(repr=False)


@dataclass(frozen=True)
class DeclaredEnvironment:
    """What a node declares: names in order, authored values, and value origins.

    ``sourced`` names take a grant or adapter value; ``generated`` names take a
    generated-artifact output. Every other name without an authored value is
    delivered empty.
    """

    names: tuple[str, ...] = ()
    authored: Mapping[str, str] = field(default_factory=dict, repr=False)
    sourced: frozenset[str] = frozenset()
    generated: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EnvironmentBindingContext:
    """The run-scoped facts every binding decision is made from.

    ``pack_id`` is the admitted pack's identity; a project-tree scenario has
    none, so no grant can apply to it. ``adapter_grants`` explicitly bind the
    admitted pack's startup values to individual consumers through ``.env``.
    ``project_environment`` is ``None`` when ``.env`` cannot be read, which
    matters only to a variable that needs it. ``process_environment`` holds
    just the grant sources, read once when the start is checked.
    """

    pack_id: str | None = None
    adapter_grants: tuple[EnvironmentGrant, ...] = ()
    grants: tuple[EnvironmentGrant, ...] = ()
    project_environment: Mapping[str, str] | None = field(
        default_factory=dict, repr=False
    )
    process_environment: Mapping[str, str] = field(default_factory=dict, repr=False)

    def grant_for(self, consumer: str, name: str) -> EnvironmentGrant | None:
        """Return the grant for this pack, consumer and variable, if any."""

        if self.pack_id is None:
            return None
        return next(
            (g for g in self.grants if g.key == (self.pack_id, consumer, name)),
            None,
        )


def declared_environment(runtime: object) -> DeclaredEnvironment:
    """Read a node's declared environment from its RAES runtime configuration."""

    variables = [
        variable
        for variable in getattr(runtime, "environment", None) or ()
        if getattr(variable, "name", "")
    ]
    authored = {v.name: v.value for v in variables if getattr(v, "value", "")}
    generated = {
        v.name for v in variables if getattr(v, "value_from", None) is not None
    }
    sourced = {
        v.name
        for v in variables
        if v.name not in authored
        and v.name not in generated
        and _classification(v) in OUT_OF_BAND_CLASSIFICATIONS
    }
    return DeclaredEnvironment(
        names=tuple(v.name for v in variables),
        authored=authored,
        sourced=frozenset(sourced),
        generated=frozenset(generated),
    )


def _classification(variable: object) -> str:
    """Return a variable's value classification as a plain string."""

    value = getattr(variable, "value_classification", "")
    return str(getattr(value, "value", value) or "")


def bind_environment(
    context: EnvironmentBindingContext,
    *,
    consumer: str,
    declared: DeclaredEnvironment,
    generated: Mapping[str, str],
) -> tuple[EnvironmentBinding, ...]:
    """Return one binding per declared variable, in declared order.

    ``generated`` holds the values generated artifacts produced for this node;
    one is used only for a variable the node declares with ``value_from``.
    Raises :class:`EnvironmentBindingError` for the first variable whose
    source is missing or empty.
    """

    return tuple(
        _bind_one(context, consumer, name, declared, generated)
        for name in dict.fromkeys(declared.names)
    )


def _bind_one(
    context: EnvironmentBindingContext,
    consumer: str,
    name: str,
    declared: DeclaredEnvironment,
    generated: Mapping[str, str],
) -> EnvironmentBinding:
    """Bind one declared variable from the source its declaration names."""

    if name in declared.generated:
        if name not in generated:
            raise EnvironmentBindingError(
                f"{name} has no generated output for this node"
            )
        binding = EnvironmentBinding(name, GENERATED_SOURCE, generated[name])
    elif name in declared.sourced:
        binding = out_of_band_binding(context, consumer, name)
    else:
        binding = EnvironmentBinding(
            name, AUTHORED_SOURCE, declared.authored.get(name, "")
        )
    return binding


def out_of_band_binding(
    context: EnvironmentBindingContext, consumer: str, name: str
) -> EnvironmentBinding:
    """Bind a value that lives outside the scenario: a grant, then the adapter."""

    grant = context.grant_for(consumer, name)
    if grant is not None:
        value = _source_value(context, grant.source.kind, grant.source.variable)
        return _sourced(name, f"grant:{grant.source_identity}", value)
    adapter = next(
        (
            g
            for g in context.adapter_grants
            if g.key == (context.pack_id, consumer, name)
        ),
        None,
    )
    if adapter is not None:
        value = _source_value(context, adapter.source.kind, adapter.source.variable)
        return _sourced(name, _ADAPTER_SOURCE + adapter.source.variable, value)
    pack = context.pack_id or "this scenario (it has no pack identity)"
    raise EnvironmentBindingError(f"{name} has no environment grant for pack {pack}")


def _source_value(context: EnvironmentBindingContext, kind: str, variable: str) -> str:
    """Read one named source; an unreadable ``.env`` fails only when needed."""

    if kind == "process-environment":
        return context.process_environment.get(variable, "")
    if context.project_environment is None:
        raise EnvironmentBindingError(
            f"the project .env is unreadable, so {variable} has no value"
        )
    return context.project_environment.get(variable, "")


def _sourced(name: str, source: str, value: str) -> EnvironmentBinding:
    """Return a binding, or refuse a source that holds no value."""

    if not value:
        raise EnvironmentBindingError(f"{name} source {source} has no value")
    return EnvironmentBinding(name, source, value)


def bind_spec_environment(
    context: EnvironmentBindingContext | None,
    spec: "BaseContainerSpec",
    *,
    consumer: str,
    generated: Mapping[str, str],
) -> tuple[EnvironmentBinding, ...]:
    """Bind a base-container spec's declared environment.

    Without a context the start skipped the backend preflight, so an
    out-of-band variable has nothing it could have been checked against.
    """

    if any(not valid_environment_variable_name(n) for n in spec.environment_names):
        raise EnvironmentBindingError(
            "invalid base-container environment variable name"
        )
    if context is None and spec.environment_sourced:
        raise EnvironmentBindingError(
            "the environment grants were not checked before this start"
        )
    return bind_environment(
        context or EnvironmentBindingContext(),
        consumer=consumer,
        declared=DeclaredEnvironment(
            names=spec.environment_names,
            authored=dict(spec.environment_defaults),
            sourced=frozenset(spec.environment_sourced),
            generated=frozenset(spec.environment_generated),
        ),
        generated=generated,
    )


def describe_bindings(bindings: Sequence[EnvironmentBinding]) -> str:
    """Name each variable and its source identity, never its value."""

    return ", ".join(f"{binding.name} from {binding.source}" for binding in bindings)


def bound_names(bindings: Sequence[EnvironmentBinding]) -> str:
    """Return the :data:`ENVIRONMENT_NAMES_LABEL` value for these bindings."""

    return ",".join(sorted({binding.name for binding in bindings}))


def realized_environment_matches(
    info: object, bindings: Sequence[EnvironmentBinding]
) -> bool:
    """Whether a container carries exactly these bindings and no earlier ones.

    The values are compared in memory and only a yes or no leaves this
    function. A container whose label names a variable that is no longer
    bound, or whose value for a bound variable differs, is recreated.
    """

    from aptl.backends._raes_runtime_environment_observation import (
        _container_environment,
    )

    config = info.get("Config") if isinstance(info, Mapping) else None
    labels = config.get("Labels") if isinstance(config, Mapping) else None
    recorded = (
        labels.get(ENVIRONMENT_NAMES_LABEL, "") if isinstance(labels, Mapping) else ""
    )
    realized = _container_environment(info) if isinstance(info, Mapping) else {}
    return recorded == bound_names(bindings) and all(
        realized.get(binding.name) == binding.value for binding in bindings
    )


def binding_context(
    realization: "DeploymentRealizationSpec",
    grants: Sequence[EnvironmentGrant],
    project_dir: Path,
) -> EnvironmentBindingContext:
    """Build the binding facts for one realization request.

    The process environment is read once, here, and only for the variables
    the admitted pack's grants name.
    """

    pack = realization.pack_identity
    pack_id = pack.pack_id if pack is not None else None
    used = sourced_names(realization, frozenset(n.address for n in realization.nodes))
    applicable = tuple(
        g for g in grants if g.pack == pack_id and (g.consumer, g.variable) in used
    )
    adapters = _adapter_grants(realization)
    named = {
        grant.source.variable
        for grant in applicable
        if grant.source.kind == "process-environment"
    }
    project_names = {
        g.source.variable
        for g in (*applicable, *adapters)
        if g.source.kind == "project-env-file" and (g.consumer, g.variable) in used
    }
    return EnvironmentBindingContext(
        pack_id=pack_id,
        adapter_grants=adapters,
        grants=tuple(grants),
        project_environment=_project_environment(project_dir, project_names),
        process_environment={v: os.environ[v] for v in named if v in os.environ},
    )


def _project_environment(
    project_dir: Path, names: set[str]
) -> Mapping[str, str] | None:
    """Return the project's ``.env`` values, or ``None`` when it cannot be read."""

    env_file = project_dir / ".env"
    try:
        values = load_dotenv(env_file) if names and env_file.is_file() else {}
        return {name: values[name] for name in names if name in values}
    except OSError, ValueError:
        return None


def _adapter_grants(
    realization: "DeploymentRealizationSpec",
) -> tuple[EnvironmentGrant, ...]:
    """Return explicit consumer grants from the admitted pack's own adapter.

    The adapter is selected for one exact pack identity; a selection made for
    any other identity supplies nothing here.
    """

    selection = realization.startup_selection
    plan = getattr(selection, "plan", None)
    if (
        plan is None
        or realization.pack_identity is None
        or selection.identity != realization.pack_identity
    ):
        return ()
    fixtures = {item.name for item in getattr(plan, "environment_fixtures", ())}
    aliases = {item.target for item in getattr(plan, "environment_aliases", ())}
    return tuple(
        grant
        for grant in getattr(plan, "environment_grants", ())
        if grant.pack == realization.pack_identity.pack_id
        and grant.source.kind == "project-env-file"
        and grant.source.variable in fixtures | aliases
    )


def unbound_environment_error(
    context: EnvironmentBindingContext,
    realization: "DeploymentRealizationSpec",
    addresses: frozenset[str],
    *,
    compose: bool = False,
) -> str | None:
    """Return why a node's declared environment cannot be bound, before mutation.

    Generated values do not exist yet, so a ``value_from`` variable only needs
    an artifact that binds it to this node; its value is read and checked when
    the artifact is generated. Generic-container values must survive Docker's
    env file now. Compose checks its sourced env-file values separately;
    authored Compose values are carried by the YAML model.
    """

    for node in realization.nodes:
        if node.address not in addresses or node.runtime is None:
            continue
        bound = dict.fromkeys(generated_environment_names(realization, node), "")
        try:
            for binding in bind_environment(
                context,
                consumer=node.name,
                declared=declared_environment(node.runtime),
                generated=bound,
            ):
                if binding.source != GENERATED_SOURCE and not compose:
                    environment_file_line(binding.name, binding.value)
        except (EnvironmentBindingError, EnvironmentDeliveryRefused) as exc:
            return f"Environment binding refused for node {node.name}: {exc}."
    return None


def unsupported_fixture_binding_error(
    realization: "DeploymentRealizationSpec",
) -> str | None:
    """Refuse external fixture values without OPEN environment authority.

    RAES expects a value-less secret fixture under exact authority to be empty.
    Withholding its commitment protects the secret but cannot satisfy that
    contract, so refuse before creating any resources rather than at readback.
    An absent authority is not permission to select a value either.
    """

    open_addresses = {
        authority.address
        for authority in realization.realization_authority
        if authority.requirement_kind == "runtime-environment"
        and authority.domain == "runtime-realization"
        and authority.mode is RealizationAuthorityMode.OPEN
    }
    for node in realization.nodes:
        if node.address in open_addresses:
            continue
        declared = declared_environment(node.runtime)
        for variable in getattr(node.runtime, "environment", ()):
            classification = _classification(variable)
            if _requires_open_environment(declared, variable.name, classification):
                return (
                    f"Environment binding refused for node {node.name}: "
                    f"{variable.name} needs open runtime-environment authority "
                    f"for an external {classification} value; exact or unspecified "
                    "authority requires a value-free readback."
                )
    return None


def _requires_open_environment(
    declared: DeclaredEnvironment, name: str, classification: str
) -> bool:
    """Whether exact readback would disclose a non-authored value's digest."""

    return (name in declared.sourced and classification == "secret_fixture") or (
        name in declared.generated
        and classification not in {"operator_secret", "redacted"}
    )


def warn_unused_grants(
    context: EnvironmentBindingContext, used: frozenset[tuple[str, str]]
) -> None:
    """Log each grant for the admitted pack that matched no value-less secret."""

    for grant in context.grants:
        if (
            grant.pack == context.pack_id
            and (grant.consumer, grant.variable) not in used
        ):
            log.warning(
                "Environment grant for node %s variable %s matched no value-less "
                "secret that node declares; it was not used.",
                grant.consumer,
                grant.variable,
            )


def sourced_names(
    realization: "DeploymentRealizationSpec", addresses: frozenset[str]
) -> frozenset[tuple[str, str]]:
    """Return every ``(node, variable)`` the given nodes declare out of band."""

    return frozenset(
        (node.name, name)
        for node in realization.nodes
        if node.address in addresses
        for name in declared_environment(node.runtime).sourced
    )
