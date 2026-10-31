"""Independent structural factorial family fixture (#1465).

The pack overlay and compile-time apparatus in ``tests/fixtures/structural_family``
belong to a third-party family owner. This module scaffolds the pack from the
installed env-packs template and compiles its experiment through public RAES.
It imports no LilRAE code, so an installed-package check can load it by path.
"""

from __future__ import annotations

import json
import shutil
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from raes.participant_control_context import SDLControlContextConfigurationValidator
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedApparatusBindingModel,
    AdmittedParticipantManifestReferenceModel,
    AdmittedTrialPlanModel,
    BackendManifestV2Model,
    ExperimentBackendReferenceModel,
    ExperimentManifestReferenceModel,
    ExperimentProcessorReferenceModel,
    ParticipantImplementationManifestModel,
    ProcessorManifestV2Model,
    TrialExecutionAuthorityModel,
)
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_env_packs import PackExperiment, derive_pack_content_manifest
from raes_processor.trial_compiler import compile_admitted_trial_plan

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "structural_family"
PACK_NAME = "structural-fixture"
SPEC = "experiments/structural-design.exp.yaml"
_CONTENT_MANIFEST = "associated-artifacts.json"


def build_pack(parent: Path, fixture: Path = FIXTURE) -> Path:
    """Assemble the complete pack from the installed template and the overlay."""

    root = parent / PACK_NAME
    shutil.copytree(Path(str(files("raes_env_packs") / "resources" / "template")), root)
    for rel in ("pack.yaml", "pack.compatibility.yaml", "docs/provenance-ledger.yaml"):
        path = root / rel
        path.write_text(
            path.read_text(encoding="utf-8").replace("<name>", PACK_NAME),
            encoding="utf-8",
        )
    shutil.copytree(fixture / "pack", root, dirs_exist_ok=True)
    pack = root / "pack.yaml"
    pack.write_text(
        pack.read_text(encoding="utf-8")
        + f"associated_artifact_manifest: {_CONTENT_MANIFEST}\n",
        encoding="utf-8",
    )
    write_content_manifest(root)
    return root


def write_content_manifest(root: Path) -> None:
    """Declare every pack file, then let env-packs bind each file's bytes."""

    manifest = root / _CONTENT_MANIFEST
    manifest.unlink(missing_ok=True)
    members = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "associated-artifact-manifest/v1",
                "manifest_id": f"{PACK_NAME}-associated-artifacts",
                "manifest_version": "0.1.0",
                "canonicalization_profile": "associated-artifact-set/v1",
                "scope": "scenario",
                "parent_ref": {"ref_kind": "scenario", "ref_id": PACK_NAME},
                "artifacts": {
                    f"artifact-{index}": {
                        "artifact_id": f"artifact-{index}",
                        "role": "other",
                        "media_type": "application/octet-stream",
                        "uri": f"raes-environment-pack:/{quote(member, safe='/-._~')}",
                        "checksum": {"algorithm": "sha256", "value": "0" * 64},
                        "size_bytes": 0,
                        "created_at": "2026-10-30T00:00:00Z",
                        "source": "environment-pack-author",
                        "sensitivity": "internal",
                    }
                    for index, member in enumerate(members)
                },
                "set_digest": "sha256:" + "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    bound = derive_pack_content_manifest(root)
    manifest.write_text(bound.model_dump_json(indent=2) + "\n", encoding="utf-8")


def compile_plan(
    experiment: PackExperiment, fixture: Path = FIXTURE
) -> AdmittedTrialPlanModel:
    """Compile one loaded experiment with the family owner's apparatus context."""

    request = experiment.compilation_request(**_apparatus_context(experiment, fixture))
    result = compile_admitted_trial_plan(request)
    if result.plan is None:
        raise AssertionError([diagnostic.code for diagnostic in result.diagnostics])
    return result.plan


def _apparatus_context(experiment: PackExperiment, fixture: Path) -> dict[str, object]:
    """Load the fixture manifests and bind them to every family participant."""

    def load(name: str) -> object:
        return json.loads((fixture / "apparatus" / name).read_text(encoding="utf-8"))

    backend = BackendManifestV2Model.model_validate(load("backend-manifest.json"))
    processor = ProcessorManifestV2Model.model_validate(load("processor-manifest.json"))
    participant = ParticipantImplementationManifestModel.model_validate(
        load("participant-manifest.json")
    )
    envelope = BackendRealizationEnvelopeModel.model_validate(
        load("realization-envelope.json")
    )
    tail = (
        participant.identity.name,
        participant.identity.version,
        participant.schema_version,
    )
    addresses = [f"agents.{name}" for name in sorted(experiment.family.agents)]
    owner = participant.configuration_registry.owner
    return {
        "apparatus": AdmittedApparatusBindingModel(
            manifest_refs=[
                _manifest_ref(backend, "backend", ExperimentBackendReferenceModel),
                _manifest_ref(
                    processor, "processor", ExperimentProcessorReferenceModel
                ),
            ],
            realization_envelope=envelope.identity,
            capability_refs=sorted(
                experiment.experiment.apparatus_intent.required_capabilities
            ),
            participant_manifest_refs=[
                AdmittedParticipantManifestReferenceModel(
                    participant_address=address,
                    implementation_name=tail[0],
                    implementation_version=tail[1],
                    manifest_version=tail[2],
                    manifest_digest=canonical_json_digest(
                        participant.model_dump(mode="json")
                    ),
                )
                for address in addresses
            ],
        ),
        "apparatus_manifests": {
            ("backend", *_identity(backend), "backend-manifest/v2"): backend,
            ("processor", *_identity(processor), "processor-manifest/v2"): processor,
        },
        "realization_envelope": envelope,
        "execution_authority": TrialExecutionAuthorityModel.model_validate(
            load("execution-authority.json")
        ),
        "participant_manifests": {
            (address, *tail): participant for address in addresses
        },
        "participant_configuration_validators": {
            (owner.validator_id, owner.validator_version): (
                SDLControlContextConfigurationValidator(experiment.family)
            )
        },
    }


def _identity(
    manifest: BackendManifestV2Model | ProcessorManifestV2Model,
) -> tuple[str, str]:
    return manifest.identity.name, manifest.identity.version


def _manifest_ref(
    manifest: BackendManifestV2Model | ProcessorManifestV2Model,
    kind: str,
    subject: type[ExperimentBackendReferenceModel]
    | type[ExperimentProcessorReferenceModel],
) -> ExperimentManifestReferenceModel:
    name, version = _identity(manifest)
    return ExperimentManifestReferenceModel(
        ref_kind="manifest",
        ref_id=name,
        ref_version=f"{kind}-manifest/v2",
        ref_digest=canonical_json_digest(manifest.model_dump(mode="json")),
        subject_ref=subject(ref_kind=kind, ref_id=name, ref_version=version),
    )
