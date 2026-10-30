"""Prepare capture containers before mutation and report verified additions."""

from dataclasses import dataclass, replace
import hashlib
import json

from raes import admit_instantiated_scenario, parse_sdl
from raes.prospective_content import admit_prospective_content
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.augmentation_preparation import (
    AugmentationEffect,
    AugmentationPreparation,
)
from raes_contracts.planning import (
    ChangeAction,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
    PlanScope,
)
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.realization_collections import node_collection_members
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model, materialization_differences
from raes_processor.planner import plan
from raes_processor.planner.augmentation_admission import admit_augmentation_preparation
from raes_processor.planner.realization_collections import planned_node_collection

from aptl.core.experiment.capture_plan import CaptureApparatus
from aptl.backends._raes_apply_reporting import closed_credential_result


@dataclass(frozen=True)
class PreparedCaptureResource:
    apparatus_id: str
    container_name: str
    resource: PlannedResource


def apparatus_node_name(item: CaptureApparatus) -> str:
    return "lilrae-cap-" + hashlib.sha256(item.apparatus_id.encode()).hexdigest()[:24]


def prepare_apparatus_completion(request, previous, manifest, apparatus):
    """Return a pure completion for the runtime's existing preparation gate."""
    prepared = prepare_apparatus_resources(request, previous, manifest, apparatus)
    operations = {operation.address: operation for operation in request.operations}
    for item in prepared:
        resource = item.resource
        operations[resource.address] = ProvisionOp(
            action=ChangeAction.UNCHANGED
            if previous.get(resource.address)
            else ChangeAction.CREATE,
            address=resource.address,
            resource_type=resource.resource_type,
            payload=resource.payload,
            ordering_dependencies=resource.ordering_dependencies,
            refresh_dependencies=resource.refresh_dependencies,
            profile_bindings=resource.profile_bindings,
        )
    return RealizationPreparation.for_request(
        request, previous, operations=tuple(operations.values())
    )


def prepare_apparatus_resources(
    request: ProvisioningPlan,
    previous: RuntimeSnapshot,
    manifest: BackendManifest,
    apparatus: tuple[CaptureApparatus, ...],
) -> tuple[PreparedCaptureResource, ...]:
    """Check both enclosing membership and augmentation before deployment."""
    containers = [
        item for item in apparatus if item.container_name and item.environment_visible
    ]
    if not containers:
        return ()
    source = request.materialization_source
    if source is None:
        raise ValueError("capture reporting requires its admitted source")
    original = admit_instantiated_scenario(json.loads(source.snapshot)["scenario"])
    definitions = {
        item.apparatus_id: (
            apparatus_node_name(item),
            {"type": "compute", "os": "linux", "description": item.purpose},
        )
        for item in containers
    }
    if len(definitions) != len(containers):
        raise ValueError("capture apparatus identities are ambiguous")
    nodes = {name: node for name, node in definitions.values()}
    if nodes.keys() & original.nodes.keys():
        raise ValueError("capture apparatus collides with authored membership")
    compiled = compile_runtime_model(
        parse_sdl(json.dumps({"name": "lilrae-capture", "nodes": nodes}))
    )
    inventory = plan(
        compiled,
        manifest,
        RuntimeSnapshot(),
        scope=PlanScope(run_id=source.run_id, target_name=manifest.name),
    )
    if not inventory.is_valid:
        raise ValueError("capture apparatus has no valid portable description")
    prepared = tuple(
        PreparedCaptureResource(
            item.apparatus_id,
            item.container_name,
            inventory.provisioning.resources[
                "provision.node." + definitions[item.apparatus_id][0]
            ],
        )
        for item in containers
    )
    authority = planned_node_collection(compile_runtime_model(original), request)
    members = dict(request.resources)
    members.update({item.resource.address: item.resource for item in prepared})
    if (
        authority is None
        or not evaluate_realization_constraint(
            authority.constraint_document,
            node_collection_members(
                members.values(),
                namespaces=authority.constraint_document.root.fields,
            ),
        ).conformant
    ):
        raise ValueError("capture apparatus exceeds the enclosing collection authority")
    document = json.loads(source.snapshot)["scenario"]
    document.pop("instantiation_provenance")
    document.setdefault("nodes", {}).update(nodes)
    prospective = admit_prospective_content(document)
    differences = materialization_differences(original, prospective)
    report = AugmentationPreparation.for_request(
        request,
        backend_manifest_v2_model(manifest),
        previous,
        content=prospective.model_dump_json(),
        effects=tuple(
            AugmentationEffect(
                field_pointer=item.field_pointer,
                requirement_refs=("backend-operational",),
                affected_scopes=(item.field_pointer,),
            )
            for item in differences
        ),
    )
    if not admit_augmentation_preparation(report, request, manifest, previous).is_valid:
        raise ValueError("capture apparatus exceeds the augmentation scope")
    return prepared


def append_verified_apparatus(
    result: ApplyResult,
    prepared: tuple[PreparedCaptureResource, ...],
    observations: tuple[dict[str, object], ...],
) -> ApplyResult:
    """Propose only first-party container additions with complete native readback."""
    if not result.success or not prepared:
        return result
    observed = {item.get("apparatus_id"): item for item in observations}
    if len(observed) != len(observations):
        raise ValueError("capture apparatus readback is ambiguous")
    entries = dict(result.snapshot.entries)
    changed = set(result.changed_addresses)
    for item in prepared:
        native = observed.get(item.apparatus_id)
        if (
            native is None
            or native.get("running") is not True
            or native.get("container_name") != item.container_name
        ):
            raise ValueError("capture apparatus readback is incomplete")
        resource = item.resource
        entries[resource.address] = SnapshotEntry(
            address=resource.address,
            domain=resource.domain,
            resource_type=resource.resource_type,
            payload=resource.payload,
            ordering_dependencies=resource.ordering_dependencies,
            refresh_dependencies=resource.refresh_dependencies,
            profile_bindings=resource.profile_bindings,
            status="ready",
        )
        changed.add(resource.address)
    return replace(
        result,
        snapshot=result.snapshot.with_entries(entries),
        changed_addresses=sorted(changed),
    )


class LilraeApparatusReportingMixin:
    """Keep preparation, native inventory and reporting on the provisioner owner."""

    def prepare(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot):
        """Offer capture additions through the public, read-only completion gate."""
        from aptl.backends.raes_manifest import create_aptl_manifest

        return prepare_apparatus_completion(
            plan,
            snapshot,
            self.reporting_manifest or create_aptl_manifest(),
            self.capture_plan.apparatus,
        )

    def _report_inventory(self, request, previous, result, *, apparatus_complete=True):
        from aptl.backends.lilrae_materialization_reporting import (
            materialization_result,
        )
        from aptl.backends.raes_manifest import create_aptl_manifest

        if self._attempt_id != request.materialization_source.run_id:
            raise ValueError("Native inventory requires the admitted run identity")
        facts = self.deployment_backend.runtime_descendant_inventory(self._attempt_id)
        if not apparatus_complete:
            facts = replace(
                facts,
                complete=False,
                diagnostics=(
                    *facts.diagnostics,
                    "lilrae.apparatus.readback-unavailable",
                ),
            )
        return materialization_result(
            request,
            previous,
            result,
            self.reporting_manifest or create_aptl_manifest(),
            facts=facts,
        )

    def refresh_inventory(self, request, previous):
        """Read current native state; never repeat provisioning during refresh."""
        # The refresh contract requires the exact predecessor. RAES projects
        # the new descendant descriptions after validating their native proof.
        result = ApplyResult(True, previous)
        apparatus_complete = True
        if self.capture_plan.apparatus:
            from aptl.backends._raes_apply_reporting import (
                capture_apparatus_observations,
            )
            from aptl.core.deployment.errors import BackendTimeoutError

            try:
                apparatus_complete = (
                    self._lilrae_deployment_spec is not None
                    and capture_apparatus_observations(
                        self.deployment_backend, self._lilrae_deployment_spec
                    )
                    is not None
                )
            except OSError, BackendTimeoutError, TypeError, ValueError:
                apparatus_complete = False
        return closed_credential_result(
            request,
            self._report_inventory(
                request,
                previous,
                result,
                apparatus_complete=apparatus_complete,
            ),
        )
