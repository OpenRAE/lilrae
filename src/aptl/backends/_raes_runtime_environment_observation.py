"""Provider-observed disclosure of declared runtime environment variables.

A value-less ``secret_fixture`` takes its value from an operator grant or the
admitted pack's startup adapter (issue #965), not from the scenario. RAES would
disclose that value as an unsalted SHA-256 commitment, against which a guess
can be checked offline, so the readback never reads it and leaves the variable
out of the disclosed environment; the start's binding log names its source. A
value-less ``operator_secret`` or ``redacted`` variable is disclosed by
presence only, and a value that the scenario authors keeps its commitment.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from raes.runtime_configuration import RuntimeConfiguration

from aptl.backends._runtime_concern_disclosure import _PROTECTED, _disclose
from aptl.core.deployment._environment_bindings import (
    _classification,
    declared_environment,
)


def observe_environment(
    info: Mapping[str, Any],
    runtime: RuntimeConfiguration,
) -> object | None:
    """Disclose declared variables carrying their realized container values."""

    declared = runtime.environment
    if not declared:
        return None
    realized = _container_environment(info)
    withheld = _out_of_band_commitments(runtime)
    records = [
        record
        for variable in declared
        if getattr(variable, "name", "") not in withheld
        and (record := _realized_environment_record(variable, realized)) is not None
    ]
    return _disclose("runtime-environment", records) if records else None


def _out_of_band_commitments(runtime: RuntimeConfiguration) -> frozenset[str]:
    """Name the variables whose grant or adapter value RAES would commit."""

    sourced = declared_environment(runtime).sourced
    return frozenset(
        variable.name
        for variable in runtime.environment
        if variable.name in sourced and _classification(variable) not in _PROTECTED
    )


def _realized_environment_record(
    variable: object, realized: Mapping[str, str]
) -> dict[str, object] | None:
    """Project one declared variable through its realized value boundary."""

    name = getattr(variable, "name", "")
    record = None
    if name:
        candidate = variable.model_dump(mode="json", by_alias=True)
        classification = candidate.get("value_classification")
        declared_value = candidate.get("value")
        if classification not in _PROTECTED and not declared_value:
            realized_value = realized.get(name)
            if realized_value:
                candidate["value"] = realized_value
            record = candidate
        elif name in realized:
            candidate["value"] = "" if classification in _PROTECTED else realized[name]
            record = candidate
    return record


def _container_environment(info: Mapping[str, Any]) -> dict[str, str]:
    """Parse the realized container's ``Config.Env`` into a name/value map."""

    config = info.get("Config") if isinstance(info, Mapping) else None
    entries = config.get("Env") if isinstance(config, Mapping) else None
    realized: dict[str, str] = {}
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, str) and "=" in entry:
                name, _, value = entry.partition("=")
                realized[name] = value
    return realized


__all__ = ("observe_environment",)
