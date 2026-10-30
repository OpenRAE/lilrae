"""Describe native facts; RAES alone admits membership and provenance."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from uuid import uuid4
from typing import Any

from raes import admit_instantiated_scenario, parse_sdl
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.materialization import MaterializationSubmission
from raes_contracts.materialization_inventory import (
    RuntimeDescendantBinding,
    RuntimeInventoryEvidence,
    RuntimeInventoryReport,
)
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import ProvisioningPlan, OrchestrationPlan, EvaluationPlan
from raes_contracts.realization_preparation import preparation_snapshot_digest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import materialization_differences
from raes_processor.semantics.realization_concerns import (
    realization_concern_descriptors,
)

from aptl.backends.raes_diagnostics import _set_path, _pop_path
from aptl.core.deployment.lilrae_recorded_inventory import RecordedInventorySnapshot

_ABSENT = object()


def _value(mapping: object, path: tuple[str, ...]) -> object:
    current = mapping
    for token in path:
        if not isinstance(current, dict) or token not in current:
            return _ABSENT
        current = current[token]
    return current


def _describe_nodes(document: dict[str, Any], snapshot: RuntimeSnapshot) -> None:
    """Preserve declaration structure and replace observed concern values."""
    nodes = document.setdefault("nodes", {})
    for entry in snapshot.entries.values():
        if entry.resource_type != "node":
            continue
        name = entry.payload.get("name")
        if name not in nodes:
            if entry.payload.get("spec", {}).get("node"):
                nodes[name] = deepcopy(entry.payload["spec"]["node"])
            continue
        node = nodes[name]
        for descriptor in realization_concern_descriptors():
            if descriptor.section != "nodes":
                continue
            observed = _value(entry.payload, descriptor.payload_path)
            if (
                observed is _ABSENT
                or observed is None
                or (len(descriptor.authored_path) == 1 and observed == "")
            ):
                _pop_path(node, descriptor.authored_path)
            else:
                _set_path(node, descriptor.authored_path, deepcopy(observed))


def _previous_report(
    request: ProvisioningPlan, previous: RuntimeSnapshot
) -> RuntimeInventoryReport | None:
    source = request.materialization_source
    return next(
        (
            record.inventory
            for record in reversed(previous.materialization_attestations)
            if record.inventory is not None
            and record.inventory.run_id == source.run_id
            and record.inventory.source_digest == source.instantiated_digest
            and record.inventory.target_scope == source.target_scope
        ),
        None,
    )


def _evidence(request: ProvisioningPlan, digest: str) -> RuntimeInventoryEvidence:
    return RuntimeInventoryEvidence(
        run_id=request.materialization_source.run_id,
        operation_id=request.operation_id,
        attempt_id=request.inventory_attempt_id,
        evidence_digest=digest,
    )


def _descendants(
    request: ProvisioningPlan,
    previous: RuntimeSnapshot,
    facts: RecordedInventorySnapshot,
    document: dict[str, Any],
) -> RuntimeInventoryReport:
    preceding = _previous_report(request, previous)
    records = {r.address: r for r in preceding.descendants} if preceding else {}
    nodes = document.setdefault("nodes", {})
    for child in facts.children:
        creation = child.creation
        if creation.attempt_id != request.materialization_source.run_id:
            raise ValueError("native descendant belongs to another attempt")
        old = records.get(creation.address)
        record = RuntimeDescendantBinding(
            address=creation.address,
            parent_address=creation.parent_address,
            source_address=creation.source_address,
            native_identity_digest=canonical_json_digest(
                {
                    "daemon": creation.daemon_id,
                    "workspace": creation.workspace_id,
                    "native_id": creation.native_id,
                }
            ),
            creation=old.creation
            if old
            else _evidence(request, creation.evidence_digest),
            state=child.state,
            lifecycle=(
                None
                if child.state == "active"
                else old.lifecycle
                if old and old.state == child.state
                else _evidence(
                    request,
                    canonical_json_digest(
                        {"creation": creation.evidence_digest, "state": child.state}
                    ),
                )
            ),
        )
        if old and record.native_identity_digest != old.native_identity_digest:
            raise ValueError("native descendant incarnation changed")
        records[record.address] = record
        name = record.address.removeprefix("provision.node.")
        if child.state != "autoremoved":
            nodes[name] = {"type": "compute"}
            if child.platform:
                nodes[name]["os"] = child.platform
    # A failed scan cannot erase previously accepted members or tombstones.
    for record in records.values():
        name = record.address.removeprefix("provision.node.")
        if record.state == "autoremoved":
            nodes.pop(name, None)
        elif name not in nodes:
            entry = previous.entries.get(record.address)
            if entry is None:
                raise ValueError("retained descendant description unavailable")
            nodes[name] = deepcopy(entry.payload["spec"]["node"])
    report = RuntimeInventoryReport(
        attempt_id=request.inventory_attempt_id,
        sequence=preceding.sequence + 1 if preceding else 1,
        complete=facts.complete,
        source_digest=request.materialization_source.instantiated_digest,
        run_id=request.materialization_source.run_id,
        target_scope=request.materialization_source.target_scope,
        descendants=tuple(records.values()),
        unavailable_evidence=tuple(
            canonical_json_digest({"diagnostic": code}) for code in facts.diagnostics
        ),
    )
    return report


def materialization_result(
    request: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    previous: RuntimeSnapshot,
    result: ApplyResult,
    manifest: BackendManifest,
    *,
    facts: RecordedInventorySnapshot | None = None,
) -> ApplyResult:
    """Return phase-bound SDL, with inventory only on provisioning operations."""
    source = request.materialization_source
    if not result.success or source is None:
        return result
    original = admit_instantiated_scenario(json.loads(source.snapshot)["scenario"])
    document = json.loads(source.snapshot)["scenario"]
    document.pop("instantiation_provenance")
    _describe_nodes(document, result.snapshot)
    report = None
    if isinstance(request, ProvisioningPlan):
        if not isinstance(facts, RecordedInventorySnapshot):
            raise ValueError("native descendant inventory unavailable")
        report = _descendants(request, previous, facts, document)
    bindings = []
    for name, node in document.get("nodes", {}).items():
        kind = "network" if node.get("type") == "switch" else "node"
        address = f"provision.{kind}.{name}"
        resource = (
            request.resources.get(address)
            if isinstance(request, ProvisioningPlan)
            else None
        )
        entry = result.snapshot.entries.get(address)
        payload = resource.payload if resource else entry.payload if entry else {}
        for index in range(payload.get("count") or 1):
            binding = {"address": address, "node_name": name, "instance_index": index}
            if name in original.nodes:
                binding["source_node"] = name
            bindings.append(binding)
    provenance = {
        "profile": "raes-materialization-attestation/v1",
        "attestation_id": "lilrae-" + uuid4().hex,
        "authored_digest": {
            "profile": "raes-sdl-semantic/v2",
            "algorithm": "sha256",
            "value": source.authored_digest,
        },
        "instantiated_digest": {
            "profile": "raes-sdl-instantiated-snapshot/v2",
            "algorithm": "sha256",
            "value": source.instantiated_digest,
        },
        "plan_digest": runtime_plan_digest(request),
        "predecessor_digest": preparation_snapshot_digest(previous),
        "operation_id": request.operation_id,
        "run_id": source.run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "boundary": "post-materialization",
        "producer": {
            "name": manifest.name,
            "version": manifest.version,
            "manifest_digest": canonical_json_digest(
                backend_manifest_v2_model(manifest).model_dump(mode="json")
            ),
            "configuration_digest": manifest.realization_envelope.configuration.configuration_digest,
        },
        "coverage_profile": "raes-materialization-effects/v1",
        "origins": [],
        "resource_bindings": bindings,
    }
    if report is not None:
        provenance["inventory"] = report.model_dump(mode="json")
    document["materialization_provenance"] = provenance
    parsed = parse_sdl(json.dumps(document))
    provenance["origins"] = [
        o.model_dump(mode="json") for o in materialization_differences(original, parsed)
    ]
    return replace(
        result,
        materialization_attestation=MaterializationSubmission(sdl=json.dumps(document)),
    )
