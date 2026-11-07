"""Generic executor for a plugin-owned participant MCP smoke plan (ADR-067).

An installed ``aptl.participant_mcp_smoke_plans`` entry point loads a static
operation tuple or a provider. Discovery reads declarations only. Executable
resolution gives a provider the admitted run's non-secret inputs. Every plan,
whatever its source, passes one complete validation before any MCP process
starts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import Path

from aptl.core.mcp_policy import McpRunAdmission
from aptl.core.mcp_smoke_contract import (
    SMOKE_PROVIDER_API_VERSION,
    AdmittedAddress,
    AdmittedNode,
    AdmittedServicePort,
    McpSmokeCheck,
    McpSmokeContext,
    McpSmokeOperation,
    McpSmokeProvider,
    McpToolGrant,
    ParticipantMcpSmokeError,
    ParticipantSmokeTargetError,
)
from aptl.validation.mcp_protocol import McpProtocolError, call_mcp_tool
from aptl.validation.participant_profile import ResolvedParticipantProfile
from aptl.validation.participant_qualification import QualificationCheckEvidence

PARTICIPANT_SMOKE_ENTRY_POINT_GROUP = "aptl.participant_mcp_smoke_plans"
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_MAX_OPERATIONS = 64
_MAX_ARGUMENT_BYTES = 64 * 1024
_MALFORMED_PLAN_MESSAGE = "participant smoke plan is malformed"
_MALFORMED_PROVIDER_MESSAGE = "participant smoke provider is malformed"


@dataclass(frozen=True)
class McpRegistration:
    """One management-owned released MCP process registration."""

    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]


@dataclass(frozen=True)
class _Admitted:
    """Host-derived admitted surface that every plan is validated against."""

    servers: tuple[str, ...]
    grants: tuple[McpToolGrant, ...]
    checks: tuple[McpSmokeCheck, ...]
    readiness: frozenset[tuple[str, str]]


def _safe_id(value: object) -> bool:
    """Return whether ``value`` is one bounded evidence-safe identifier."""

    return isinstance(value, str) and _SAFE_ID.fullmatch(value) is not None


def _profile_selector(profile: ResolvedParticipantProfile) -> str:
    """Return the bounded installed-plan selector for one admitted profile."""

    selector = f"{profile.manifest.profile_id}.{profile.manifest.scenario.catalog_id}"
    if _SAFE_ID.fullmatch(selector) is None:
        raise ParticipantMcpSmokeError("participant smoke selector is invalid")
    return selector


def _installed_plan_entry_points() -> list[metadata.EntryPoint]:
    """Return installed participant-smoke plan entry points."""

    return list(metadata.entry_points(group=PARTICIPANT_SMOKE_ENTRY_POINT_GROUP))


def _load_installed_plan(selector: str) -> object:
    """Load the one installed smoke plan whose selector matches exactly."""

    if _SAFE_ID.fullmatch(selector) is None:
        raise ParticipantMcpSmokeError("participant smoke selector is invalid")
    exact = [
        entry_point
        for entry_point in _installed_plan_entry_points()
        if entry_point.name == selector
    ]
    if len(exact) != 1:
        raise ParticipantMcpSmokeError(
            "exactly one compatible participant smoke plan must be installed"
        )
    try:
        return exact[0].load()
    except Exception:
        raise ParticipantMcpSmokeError(
            "participant smoke plan could not be loaded"
        ) from None


def _is_static(loaded: object) -> bool:
    """Return whether an installed plan is the static operation-tuple form."""

    return isinstance(loaded, (tuple, list))


def _provider_checks(provider: object) -> tuple[McpSmokeCheck, ...]:
    """Return a provider's validated check declarations."""

    checks = getattr(provider, "checks", None)
    if (
        getattr(provider, "extension_api_version", None) != SMOKE_PROVIDER_API_VERSION
        or not callable(getattr(provider, "resolve", None))
        or not isinstance(checks, tuple)
        or not checks
        or len(checks) > _MAX_OPERATIONS
        or not all(isinstance(check, McpSmokeCheck) for check in checks)
        or not all(
            _safe_id(check.check_id)
            and _safe_id(check.server_id)
            and _safe_id(check.tool_name)
            for check in checks
        )
        or len({check.check_id for check in checks}) != len(checks)
    ):
        raise ParticipantMcpSmokeError(_MALFORMED_PROVIDER_MESSAGE)
    return checks


def _host_arguments(arguments: object) -> dict[str, object]:
    """Return a host-owned JSON copy of bounded operation arguments."""

    if not isinstance(arguments, Mapping):
        raise ParticipantMcpSmokeError(_MALFORMED_PLAN_MESSAGE)
    try:
        encoded = json.dumps(dict(arguments), allow_nan=False)
    except (TypeError, ValueError):
        raise ParticipantMcpSmokeError(_MALFORMED_PLAN_MESSAGE) from None
    if len(encoded.encode()) > _MAX_ARGUMENT_BYTES:
        raise ParticipantMcpSmokeError(_MALFORMED_PLAN_MESSAGE)
    return json.loads(encoded)


def _host_operation(operation: object) -> McpSmokeOperation:
    """Validate one operation and return the host-owned copy to dispatch."""

    if (
        not isinstance(operation, McpSmokeOperation)
        or not _safe_id(operation.check_id)
        or not _safe_id(operation.server_id)
        or not _safe_id(operation.tool_name)
        or not callable(operation.validates)
    ):
        raise ParticipantMcpSmokeError(_MALFORMED_PLAN_MESSAGE)
    return replace(operation, arguments=_host_arguments(operation.arguments))


def _validated_operations(loaded: object) -> tuple[McpSmokeOperation, ...]:
    """Return one bounded, typed plan made of host-owned operation copies."""

    if not isinstance(loaded, tuple) or not loaded or len(loaded) > _MAX_OPERATIONS:
        raise ParticipantMcpSmokeError(_MALFORMED_PLAN_MESSAGE)
    operations = tuple(_host_operation(operation) for operation in loaded)
    if len({operation.check_id for operation in operations}) != len(operations):
        raise ParticipantMcpSmokeError(_MALFORMED_PLAN_MESSAGE)
    return operations


def _required_capabilities(profile: ResolvedParticipantProfile) -> frozenset[str]:
    """Return capabilities that a required narrative operation names."""

    return frozenset(
        operation.capability_id
        for operation in profile.narrative.operations
        if operation.classification == "required"
    )


def _grants(
    profile: ResolvedParticipantProfile, servers: tuple[str, ...]
) -> tuple[McpToolGrant, ...]:
    """Return one exact tool grant per admitted server, refusing conflicts."""

    grants: dict[str, tuple[str, ...]] = {}
    for workbench in profile.workbench_profiles:
        for server in workbench.servers:
            if server.server_id not in servers:
                continue
            if grants.setdefault(server.server_id, server.tool_names) != (
                server.tool_names
            ):
                raise ParticipantMcpSmokeError(
                    "profile grants conflicting tools to one MCP server"
                )
    return tuple(McpToolGrant(server_id, grants[server_id]) for server_id in servers)


def admitted_mcp_server_ids(
    profile: ResolvedParticipantProfile, admission: McpRunAdmission | None = None
) -> tuple[str, ...]:
    """Return the profile's MCP servers that the run admission selected.

    Without an admission the profile surface applies, as before ADR-067.
    """

    if admission is None:
        return profile.mcp_server_ids
    selected = set(admission.server_ids)
    return tuple(server for server in profile.mcp_server_ids if server in selected)


def _admitted_surface(
    profile: ResolvedParticipantProfile, admission: McpRunAdmission | None
) -> _Admitted:
    """Derive the admitted servers, grants, and expected readiness checks."""

    servers = admitted_mcp_server_ids(profile, admission)
    grants = _grants(profile, servers)
    required = _required_capabilities(profile)
    tools = {grant.server_id: grant.tool_names for grant in grants}
    expected: list[McpSmokeCheck] = []
    for check in profile.readiness.checks:
        if check.kind != "mcp-tool":
            continue
        if check.subject_id not in profile.mcp_server_ids:
            raise ParticipantMcpSmokeError(
                "profile MCP readiness suite names an unknown server"
            )
        if check.subject_id in tools:
            expected.append(
                McpSmokeCheck(check.check_id, check.subject_id, check.operation_id)
            )
        elif check.capability_id in required:
            raise ParticipantMcpSmokeError("required MCP server is not admitted")
    if not expected:
        raise ParticipantMcpSmokeError("no admitted MCP readiness checks")
    return _Admitted(
        servers=servers,
        grants=grants,
        checks=tuple(expected),
        readiness=frozenset((check.check_id, check.server_id) for check in expected),
    )


def _validate_against_admission(
    operations: tuple[McpSmokeOperation, ...], admitted: _Admitted
) -> None:
    """Require the plan to equal the admitted readiness surface and grants."""

    if {operation.server_id for operation in operations} != set(admitted.servers):
        raise ParticipantMcpSmokeError(
            "profile MCP operation registry does not match the allowed surface"
        )
    if {
        (operation.check_id, operation.server_id) for operation in operations
    } != admitted.readiness:
        raise ParticipantMcpSmokeError(
            "profile MCP readiness suite does not match the operation registry"
        )
    tools = {grant.server_id: grant.tool_names for grant in admitted.grants}
    if any(
        operation.tool_name not in tools[operation.server_id]
        for operation in operations
    ):
        raise ParticipantMcpSmokeError("participant smoke tool is not granted")


def _context(
    profile: ResolvedParticipantProfile,
    admission: McpRunAdmission,
    admitted: _Admitted,
) -> McpSmokeContext:
    """Project the admitted run onto the provider's non-secret context."""

    return McpSmokeContext(
        extension_api_version=SMOKE_PROVIDER_API_VERSION,
        profile_id=profile.manifest.profile_id,
        scenario_id=profile.manifest.scenario.catalog_id,
        pack=admission.pack,
        nodes=admission.nodes,
        grants=admitted.grants,
        checks=admitted.checks,
    )


def _provider_operations(
    provider: object,
    profile: ResolvedParticipantProfile,
    admission: McpRunAdmission | None,
    admitted: _Admitted,
) -> tuple[McpSmokeOperation, ...]:
    """Resolve one provider plan and keep it within its declarations."""

    declared = set(_provider_checks(provider))
    if admission is None:
        raise ParticipantMcpSmokeError(
            "participant smoke provider requires admitted inputs"
        )
    context = _context(profile, admission, admitted)
    try:
        loaded = provider.resolve(context)
    except ParticipantSmokeTargetError:
        raise ParticipantSmokeTargetError() from None
    except Exception:
        raise ParticipantMcpSmokeError("participant smoke provider failed") from None
    operations = _validated_operations(loaded)
    if any(
        McpSmokeCheck(operation.check_id, operation.server_id, operation.tool_name)
        not in declared
        for operation in operations
    ):
        raise ParticipantMcpSmokeError(
            "participant smoke provider emitted an undeclared check"
        )
    return operations


def discover_participant_mcp_smoke_checks(selector: str) -> tuple[McpSmokeCheck, ...]:
    """Return the checks one installed plan declares, without resolving it."""

    loaded = _load_installed_plan(selector)
    if _is_static(loaded):
        return tuple(
            McpSmokeCheck(operation.check_id, operation.server_id, operation.tool_name)
            for operation in _validated_operations(loaded)
        )
    return _provider_checks(loaded)


def resolve_participant_mcp_smoke_plan(
    selector: str,
) -> tuple[McpSmokeOperation, ...]:
    """Load one static adapter-owned plan by its bounded release selector.

    A provider needs admitted inputs, so this form refuses it. Use
    :func:`discover_participant_mcp_smoke_checks` for declaration-only discovery.
    """

    loaded = _load_installed_plan(selector)
    if not _is_static(loaded):
        _provider_checks(loaded)
        raise ParticipantMcpSmokeError(
            "participant smoke provider requires admitted inputs"
        )
    return _validated_operations(loaded)


def _resolved_plan(
    profile: ResolvedParticipantProfile,
    admission: McpRunAdmission | None,
    operations: Sequence[McpSmokeOperation] | None,
) -> tuple[tuple[McpSmokeOperation, ...], _Admitted]:
    """Resolve, copy, and completely validate one plan before any dispatch."""

    admitted = _admitted_surface(profile, admission)
    if operations is not None:
        if not isinstance(operations, Sequence):
            raise ParticipantMcpSmokeError(_MALFORMED_PLAN_MESSAGE)
        plan = _validated_operations(tuple(operations))
    else:
        loaded = _load_installed_plan(_profile_selector(profile))
        plan = (
            _validated_operations(loaded)
            if _is_static(loaded)
            else _provider_operations(loaded, profile, admission, admitted)
        )
    _validate_against_admission(plan, admitted)
    return plan, admitted


def resolve_participant_mcp_smoke_operations(
    profile: ResolvedParticipantProfile,
    admission: McpRunAdmission | None = None,
) -> tuple[McpSmokeOperation, ...]:
    """Resolve and validate the installed plan for an admitted profile and run."""

    return _resolved_plan(profile, admission, None)[0]


def _passes(operation: McpSmokeOperation, result: Mapping[str, object]) -> bool:
    """Run an adapter validator; any exception is a failed semantic check."""

    try:
        return bool(operation.validates(result))
    except Exception:
        return False


def run_participant_mcp_smoke(
    profile: ResolvedParticipantProfile,
    registrations: Mapping[str, McpRegistration],
    operations: Sequence[McpSmokeOperation] | None = None,
    *,
    admission: McpRunAdmission | None = None,
) -> tuple[QualificationCheckEvidence, ...]:
    """Resolve, validate, then invoke every admitted MCP operation exactly once."""

    plan, admitted = _resolved_plan(profile, admission, operations)
    if set(registrations) != set(admitted.servers):
        raise ParticipantMcpSmokeError(
            "MCP registration surface does not match the participant profile"
        )
    timeouts = {
        check.check_id: check.timeout_seconds
        for check in profile.readiness.checks
        if check.kind == "mcp-tool"
    }
    tools = {grant.server_id: grant.tool_names for grant in admitted.grants}
    evidence: list[QualificationCheckEvidence] = []
    for operation in plan:
        registration = registrations[operation.server_id]
        try:
            result = call_mcp_tool(
                registration.argv,
                operation.tool_name,
                operation.arguments,
                cwd=registration.cwd,
                env=registration.env,
                timeout_seconds=timeouts[operation.check_id],
                expected_tool_names=tools[operation.server_id],
            )
            passed = _passes(operation, result)
        except McpProtocolError:
            passed = False
        evidence.append(
            QualificationCheckEvidence(
                check_id=operation.check_id,
                status="passed" if passed else "failed",
                summary=(
                    "semantic backend operation passed"
                    if passed
                    else "semantic backend operation failed"
                ),
            )
        )
    return tuple(evidence)


__all__ = [
    "PARTICIPANT_SMOKE_ENTRY_POINT_GROUP",
    "SMOKE_PROVIDER_API_VERSION",
    "AdmittedAddress",
    "AdmittedNode",
    "AdmittedServicePort",
    "McpRegistration",
    "McpSmokeCheck",
    "McpSmokeContext",
    "McpSmokeOperation",
    "McpSmokeProvider",
    "McpToolGrant",
    "ParticipantMcpSmokeError",
    "ParticipantSmokeTargetError",
    "admitted_mcp_server_ids",
    "discover_participant_mcp_smoke_checks",
    "resolve_participant_mcp_smoke_plan",
    "resolve_participant_mcp_smoke_operations",
    "run_participant_mcp_smoke",
]
