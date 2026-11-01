# RAES and env-packs consumer inventory

This inventory lists each RAES and env-packs name that LilRAE imports in
`src/`. It groups the names by the capability that they serve. For each
capability, it names the upstream issue that owns the capability in Go and the
LilRAE Go ports that need it. Go port 05
([#1556](https://github.com/OpenRAE/lilrae/issues/1556)) records it, and the
[preflight](issue-1556-raes-go-boundary-preflight.md) sets its rules.

A Python module path in this inventory is evidence of a capability. It is not
a proposed Go package. The RAES and env-packs Go ports can change their package
boundaries, so the contract is the capability.

## Scope

- The inventory describes `src/` at `go-cutover` commit `12d2c11a`, with RAES
  10.1.0 and raes-env-packs 7.0.0 from `uv.lock`.
- At that commit, `src/` has 488 import statements of RAES and env-packs
  modules in 172 files. 418 statements are at module level, 46 are under
  `TYPE_CHECKING`, and 24 are inside functions. They import 323 names from 97
  modules.
- The Python `ast` module finds each import statement. The scan does not
  import the product code.
- The scan also follows each imported RAES module to the attributes that
  `src/` reads from it: `SCHEMAS` and `corpus_family_root` of
  `raes_contracts.corpus`, and the two snapshot value limits of `raes_runtime`.
- `core/evidence_bundle/schemas.py` also reads the installed RAES version with
  `importlib.metadata.version("raes")`. An evidence bundle records that version
  with each RAES schema that it carries. The Go port needs the version of the
  RAES Go module for the same record.
- `tests/test_raes_consumer_inventory.py` fails when an import or a module
  attribute in `src/` has no row in the name tables. It also fails when a row
  names a module or a name that `src/` does not use.
- The LilRAE area of a name is the package of the importing file below `src/`.
  The LilRAE Go port of a file is the port whose scope contains that file. In
  the tables, GP*n* is LilRAE Go port *n*, followed by its issue number.

## Upstream owners

| Capability | Upstream owner | LilRAE Go ports |
| --- | --- | --- |
| SDL source loading and parse errors | [rae#1782](https://github.com/OpenRAE/rae/issues/1782) | GP16 (#1567), GP17 (#1568), GP18 (#1569), GP20 (#1571), GP21 (#1572), GP24 (#1575) |
| SDL models, semantic validation, and canonical identity | [rae#1783](https://github.com/OpenRAE/rae/issues/1783) | GP16 (#1567), GP17 (#1568), GP18 (#1569), GP20 (#1571), GP21 (#1572), GP24 (#1575) |
| SDL runtime inventory families | [rae#1784](https://github.com/OpenRAE/rae/issues/1784) | GP18 (#1569), GP19 (#1570), GP21 (#1572), GP26 (#1577) |
| SDL instantiation, variation, and modules | [rae#1785](https://github.com/OpenRAE/rae/issues/1785) | GP11 (#1562), GP16 (#1567), GP17 (#1568), GP18 (#1569), GP20 (#1571), GP21 (#1572), GP24 (#1575) |
| Shared primitives | [rae#1779](https://github.com/OpenRAE/rae/issues/1779) | GP11 (#1562), GP16 (#1567), GP17 (#1568), GP18 (#1569), GP21 (#1572) |
| Contract bindings, diagnostics, and the published corpus | [rae#1780](https://github.com/OpenRAE/rae/issues/1780) | GP11 (#1562), GP17 (#1568), GP18 (#1569), GP19 (#1570), GP21 (#1572), GP22 (#1573), GP24 (#1575) |
| Concept authority and vocabularies | [rae#1781](https://github.com/OpenRAE/rae/issues/1781) | GP18 (#1569), GP20 (#1571), GP21 (#1572), GP22 (#1573) |
| Processor compiler, planner, and realization semantics | [rae#1787](https://github.com/OpenRAE/rae/issues/1787) | GP11 (#1562), GP16 (#1567), GP17 (#1568), GP18 (#1569), GP19 (#1570), GP20 (#1571), GP21 (#1572), GP22 (#1573), GP24 (#1575), GP26 (#1577) |
| Experiments, trial plans, and experiment records | [rae#1788](https://github.com/OpenRAE/rae/issues/1788) | GP11 (#1562), GP16 (#1567), GP17 (#1568), GP18 (#1569), GP21 (#1572), GP22 (#1573), GP25 (#1576), GP26 (#1577) |
| Processor analysis services | [rae#1789](https://github.com/OpenRAE/rae/issues/1789) | GP11 (#1562), GP17 (#1568), GP22 (#1573) |
| Backend contracts, interfaces, manifests, and realization envelopes | [rae#1790](https://github.com/OpenRAE/rae/issues/1790) | GP11 (#1562), GP17 (#1568), GP18 (#1569), GP20 (#1571), GP21 (#1572), GP22 (#1573), GP26 (#1577) |
| Runtime control plane, snapshots, and results | [rae#1791](https://github.com/OpenRAE/rae/issues/1791) | GP11 (#1562), GP17 (#1568), GP18 (#1569), GP20 (#1571), GP21 (#1572), GP22 (#1573), GP24 (#1575) |
| Participant control, crossing, and decision surfaces | [rae#1794](https://github.com/OpenRAE/rae/issues/1794) | GP22 (#1573) |
| Participant execution, episodes, and behavior | [rae#1795](https://github.com/OpenRAE/rae/issues/1795) | GP11 (#1562), GP17 (#1568), GP22 (#1573), GP24 (#1575) |
| Backend conformance | [rae#1796](https://github.com/OpenRAE/rae/issues/1796) | GP24 (#1575) |
| Run materialization archive | [rae#1797](https://github.com/OpenRAE/rae/issues/1797) | GP21 (#1572) |
| Pack static validation | [env-packs#564](https://github.com/OpenRAE/env-packs/issues/564) | GP17 (#1568) |
| Pack content identity and artifact resolution | [env-packs#565](https://github.com/OpenRAE/env-packs/issues/565) | GP17 (#1568), GP18 (#1569), GP20 (#1571), GP26 (#1577) |
| Pack catalog | [env-packs#572](https://github.com/OpenRAE/env-packs/issues/572) | GP17 (#1568) |

[rae#1825](https://github.com/OpenRAE/rae/issues/1825) owns the public Go API
of RAES for environment packs, LilRAE, and Coldlight. LilRAE uses the RAES
capabilities above through that API, as rae sets it. env-packs has no such
issue. LilRAE uses the library operation that each env-packs owner issue sets.

LilRAE is downstream of RAES and env-packs. It conforms to the Go API that they
set, and it makes no request or change to their issues. Each LilRAE Go port
above is blocked on its owner issues until they deliver.

The scope lists of the owner issues do not name each module.
[Names without a named owner](#names-without-a-named-owner) lists the names
whose owner follows from the capability only.

## Names by capability

### SDL source loading and parse errors

Owner: [rae#1782](https://github.com/OpenRAE/rae/issues/1782).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes` | `SDLError`, `SDLInstantiationError`, `SDLParseError`, `SDLValidationError`, `parse_sdl`, `parse_sdl_file` | `backends`, `core`, `core/experiment`, `validation` |
| `raes.artifact_requirements` | `ArtifactIdentity`, `ArtifactMechanismProfile`, `ArtifactRequirement`, `ArtifactSatisfactionRoute` | `backends` |

### SDL models, semantic validation, and canonical identity

Owner: [rae#1783](https://github.com/OpenRAE/rae/issues/1783).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes` | `InstantiatedScenarioSnapshot`, `Scenario`, `canonical_instantiated_sdl_bytes`, `canonical_instantiated_sdl_digest`, `canonical_sdl_digest` | `backends`, `core/experiment` |
| `raes.accounts` | `Account` | `validation` |
| `raes.canonical` | `SDLCanonicalDigest`, `canonical_instantiated_sdl_digest`, `canonical_sdl_digest` | `core/experiment` |
| `raes.explicitness` | `ExplicitnessClass` | `backends` |
| `raes.nodes` | `NodeType` | `backends` |
| `raes.phase_contracts` | `TrialInstantiationProvenance` | `backends` |
| `raes.prospective_content` | `admit_prospective_content` | `backends` |
| `raes.realization_designation` | `designation_records`, `resolve_realization_designation` | `backends` |
| `raes.scenario` | `ExpandedScenario`, `InstantiatedScenario`, `Scenario` | `backends`, `core/experiment`, `validation` |

### SDL runtime inventory families

Owner: [rae#1784](https://github.com/OpenRAE/rae/issues/1784).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes.runtime_configuration` | `RuntimeConfiguration`, `RuntimeControlInterface`, `RuntimeOrchestrationAuthority`, `ServiceUnitActiveState`, `ServiceUnitEnabledState` | `aptl_techvault`, `backends`, `core/deployment` |
| `raes.runtime_filesystem` | `RuntimeFilesystemEntryType` | `backends` |
| `raes.runtime_mounts` | `RuntimeMountSourceKind` | `backends` |

### SDL instantiation, variation, and modules

Owner: [rae#1785](https://github.com/OpenRAE/rae/issues/1785).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes` | `admit_instantiated_scenario`, `instantiate_scenario` | `backends`, `validation` |
| `raes.instantiate` | `instantiate_scenario` | `core/experiment` |
| `raes.module_registry` | `LOCKFILE_NAME` | `backends`, `validation` |
| `raes.variables` | `VariableType` | `core/experiment` |
| `raes.variation` | `ParameterVariationPoint` | `core/experiment` |

### Shared primitives

Owner: [rae#1779](https://github.com/OpenRAE/rae/issues/1779).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.addressing` | `render_compiled_address` | `backends` |
| `raes_contracts.bounded_domains` | `scalar_in_domain` | `core/experiment` |
| `raes_contracts.canonical` | `canonical_json_bytes`, `canonical_json_digest` | `backends` |
| `raes_contracts.contracts` | `RandomStreamDrawRecordModel` | `core/archival` |
| `raes_contracts.errors` | `InvalidInputError` | `core/experiment` |

### Contract bindings, diagnostics, and the published corpus

Owner: [rae#1780](https://github.com/OpenRAE/rae/issues/1780).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.associated_artifacts` | `AssociatedArtifactManifestModel`, `AssociatedArtifactValidationLimits`, `load_associated_artifact_manifest_json`, `validate_associated_artifact_manifest` | `core/experiment` |
| `raes_contracts.corpus` | `SCHEMAS`, `corpus_family_root`, module import | `core/evidence_bundle` |
| `raes_contracts.diagnostics` | `Diagnostic`, `Severity` | `backends`, `cli`, `core/correlation`, `core/evidence`, `core/experiment`, `validation` |

### Concept authority and vocabularies

Owner: [rae#1781](https://github.com/OpenRAE/rae/issues/1781).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.apparatus` | `RealizationSupportMode`, `RealizationVerificationScope` | `backends` |
| `raes_contracts.realization_envelope` | `ObservationStrength` | `backends` |
| `raes_contracts.vocabulary` | `Closure`, `ObservationStrength`, `ParticipantFeatureSupportLevel`, `ProcessResourceLimitKind`, `ProcessResourceLimitScope`, `RealizationVerificationScope`, `WorkflowFeature`, `WorkflowStatePredicateFeature` | `backends` |

### Processor compiler, planner, and realization semantics

Owner: [rae#1787](https://github.com/OpenRAE/rae/issues/1787).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.artifact_requirements` | `ArtifactAvailabilityContext` | `backends` |
| `raes_contracts.augmentation_preparation` | `AugmentationEffect`, `AugmentationPreparation` | `backends` |
| `raes_contracts.contracts` | `ArtifactAcquisitionTimingModel`, `ArtifactAvailabilityContext`, `ArtifactMechanismCapability`, `ArtifactRequirementAvailability`, `PROCESSOR_MANIFEST_V2_SCHEMA_VERSION` | `backends`, `core/experiment` |
| `raes_contracts.plan_projection` | `runtime_plan_digest` | `backends` |
| `raes_contracts.planning` | `ChangeAction`, `EvaluationPlan`, `OrchestrationPlan`, `PlanScope`, `PlannedResource`, `ProvisionOp`, `ProvisioningPlan`, `RealizationAuthorityMode`, `RealizationResolutionSource`, `ResolvedRealizationAuthority`, `RuntimeDomain` | `backends`, `core/deployment`, `core/experiment`, `validation` |
| `raes_contracts.realization_authority` | `RealizationAuthorityMode` | `backends` |
| `raes_contracts.realization_collections` | `node_collection_members` | `backends` |
| `raes_contracts.realization_preparation` | `RealizationPreparation`, `preparation_snapshot_digest` | `backends` |
| `raes_contracts.realization_profiles` | `PlanProfileAuthority` | `backends` |
| `raes_contracts.realization_structure` | `evaluate_realization_constraint`, `validate_realization_value` | `backends` |
| `raes_contracts.run_scope` | `PlanScope` | `backends` |
| `raes_processor.capabilities` | `ProcessorManifest` | `core/experiment` |
| `raes_processor.capture_admission` | `CaptureDemand`, `capture_admission_diagnostics`, `compile_scenario_capture_demands` | `backends`, `core/experiment` |
| `raes_processor.compiler` | `compile_runtime_model`, `compile_scenario_runtime_model`, `materialization_differences` | `backends`, `validation` |
| `raes_processor.manifest` | `create_reference_processor_manifest`, `reference_processor_manifest_payload` | `core/experiment`, `core/provenance` |
| `raes_processor.models` | `ExecutionPlan`, `ParticipantAutonomousExecutionRuntime`, `ParticipantBehaviorHistoryEvent`, `ParticipantBehaviorSpecificationRuntime`, `RuntimeModel`, `resolve_participant_action_arguments` | `backends` |
| `raes_processor.planner` | `plan`, `realization_authority_disclosure` | `backends` |
| `raes_processor.planner.augmentation_admission` | `admit_augmentation_preparation` | `backends` |
| `raes_processor.planner.realization_collections` | `planned_node_collection` | `backends` |
| `raes_processor.reference` | `ReferenceProcessorResult`, `ScenarioInput`, `run_reference_processor` | `core/experiment` |
| `raes_processor.semantics.realization` | `CONCERN_PAYLOAD_PATH`, `CompiledRealizationRequirement`, `project_realization_concern` | `aptl_techvault`, `backends` |
| `raes_processor.semantics.realization_concerns` | `realization_concern_descriptor`, `realization_concern_descriptors` | `backends` |
| `raes_processor.trial_realization` | `instantiate_admitted_trial_entry` | `backends` |

### Experiments, trial plans, and experiment records

Owner: [rae#1788](https://github.com/OpenRAE/rae/issues/1788).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.contracts` | `AdmittedTrialPlanModel`, `BindingOwnerModel`, `BindingScalarType`, `ConfigurationTargetDeclarationModel`, `ConfigurationTargetRegistryModel`, `ExperimentApparatusCompatibilityReferenceModel`, `ExperimentApparatusComponentModel`, `ExperimentApparatusConstraintModel`, `ExperimentApparatusContextModel`, `ExperimentArtifactRefModel`, `ExperimentAugmentationDisclosureModel`, `ExperimentBackendReferenceModel`, `ExperimentBindingDescriptorModel`, `ExperimentBindingDescriptorSetModel`, `ExperimentCaptureRequirementModel`, `ExperimentCaptureSpecModel`, `ExperimentCaptureSpecReferenceModel`, `ExperimentChecksumModel`, `ExperimentClockContextModel`, `ExperimentEvidenceRecordModel`, `ExperimentEvidenceRecordReferenceModel`, `ExperimentInvalidationModel`, `ExperimentManifestReferenceModel`, `ExperimentMeasurementChannelReferenceModel`, `ExperimentParameterModel`, `ExperimentProcessorReferenceModel`, `ExperimentRealizedFormDisclosureModel`, `ExperimentReferenceModel`, `ExperimentResultSummaryModel`, `ExperimentRunModel`, `ExperimentRunTraceabilityModel`, `ExperimentScenarioSnapshotReferenceModel`, `ExperimentSpecModel`, `ExperimentStochasticControlModel`, `ExperimentTaskModel`, `ExperimentTaskReferenceModel`, `ExperimentValidityNoteModel`, `LiteralBindingValueModel`, `ParticipantConfigurationModel`, `ParticipantConfigurationResultModel`, `ParticipantImplementationBindingTargetModel`, `RealizedBindingProvenanceModel`, `ScenarioBindingTargetModel`, `validate_experiment_run_archival_datetimes`, `validate_experiment_run_structure_against_task`, `validate_experiment_run_time_model` | `aptl_techvault`, `backends`, `core`, `core/archival`, `core/evidence`, `core/evidence_bundle`, `core/execution`, `core/experiment`, `workbench` |
| `raes_contracts.contracts.capabilities` | `ApparatusIdentityModel` | `core/execution` |
| `raes_contracts.contracts.experiment_capture` | `ExperimentRawEvidenceContentModel` | `core/evidence`, `core/execution` |
| `raes_contracts.contracts.experiment_manifest_references` | `ExperimentEvidenceSatisfactionReferenceModel`, `ExperimentManifestReferenceModel`, `ExperimentRunEvidenceArtifactReferenceModel` | `core/execution` |
| `raes_contracts.experiment_bindings` | `ApparatusManifestKey`, `ParticipantManifestKey`, `ScenarioBindingResolution`, `validate_experiment_binding_targets` | `core/experiment` |
| `raes_contracts.experiment_spec` | `ExperimentSpecModel`, `ExperimentSpecValidationError`, `parse_experiment_spec` | `core/experiment` |

### Processor analysis services

Owner: [rae#1789](https://github.com/OpenRAE/rae/issues/1789).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.satisfiability` | `canonical_contract_digest` | `backends`, `core/archival`, `core/experiment` |

### Backend contracts, interfaces, manifests, and realization envelopes

Owner: [rae#1790](https://github.com/OpenRAE/rae/issues/1790).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_backend_protocols.capabilities` | `BackendManifest`, `EvaluatorCapabilities`, `ObservationCapabilities`, `ObservationCaptureOffer`, `OperatingSystemCompatibility`, `OrchestratorCapabilities`, `ParticipantExecutionBinding`, `ParticipantFeatureSupport`, `ParticipantRuntimeCapabilities`, `ProvisionerCapabilities`, `TIME_CAPABILITY_REQUIRED_CONTRACTS`, `TimeCapabilities` | `aptl_techvault`, `backends`, `core/experiment` |
| `raes_backend_protocols.manifest` | `BackendManifest`, `backend_manifest_payload`, `backend_manifest_v2_model` | `backends`, `core/experiment`, `core/provenance` |
| `raes_backend_protocols.participant_action_commit` | `reject_participant_action_outcome` | `backends` |
| `raes_backend_protocols.participant_runtime_base` | `BaseParticipantRuntime` | `backends` |
| `raes_backend_protocols.provisioner_capabilities` | `ProvisionerCapabilities` | `backends` |
| `raes_contracts.apparatus` | `ConceptBinding`, `ProcessResourceLimitCapability`, `RealizationObservationCapability`, `RealizationSupportDeclaration` | `backends` |
| `raes_contracts.contracts` | `BACKEND_MANIFEST_V2_SCHEMA_VERSION`, `BackendManifestV2Model` | `backends`, `core/experiment` |
| `raes_contracts.contracts.materialization_attestation` | `MaterializationArchiveRecord` | `backends` |
| `raes_contracts.manifest_authority` | `BACKEND_SUPPORTED_CONTRACT_IDS`, `PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS` | `backends` |
| `raes_contracts.materialization` | `MATERIALIZATION_MAX_BYTES`, `MaterializationSubmission`, `require_materialization_records` | `backends` |
| `raes_contracts.materialization_inventory` | `RuntimeDescendantBinding`, `RuntimeInventoryEvidence`, `RuntimeInventoryReport` | `backends` |
| `raes_contracts.realization_envelope` | `BackendRealizationEnvelopeModel`, `RealizationConcern`, `realization_envelope_digest`, `realizer_configuration_digest` | `backends` |

### Runtime control plane, snapshots, and results

Owner: [rae#1791](https://github.com/OpenRAE/rae/issues/1791).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.account_credentials` | `account_placement_has_credential_bindings`, `value_free_account_placement_payload` | `backends` |
| `raes_contracts.contracts.time_model` | `RealizedTimeModelProvenanceModel`, `TimeModelDeclarationModel` | `core/archival` |
| `raes_contracts.evaluation` | `EvaluationExecutionState`, `EvaluationHistoryEvent`, `EvaluationHistoryEventType`, `EvaluationResultContract`, `EvaluationResultStatus` | `backends` |
| `raes_contracts.realization_observation` | `ObservedOperatingSystemIdentity`, `RealizationObservation`, `RealizationObservationDisclosure`, `bind_compute_substrate_observations`, `bind_operating_system_observations` | `backends` |
| `raes_contracts.realization_observation_demand` | `compute_substrate_collection_addresses` | `backends` |
| `raes_contracts.realization_preparation` | `jsonable_fallback`, `to_jsonable_python` | `backends` |
| `raes_contracts.runtime_state` | `ApplyResult`, `OperationReceipt`, `OperationState`, `OperationStatus`, `RealizationObservationDisclosure`, `RuntimeSnapshot`, `RuntimeSnapshotEnvelope`, `SnapshotEntry` | `backends`, `core`, `validation` |
| `raes_contracts.workflow` | `WorkflowExecutionContract`, `WorkflowExecutionState`, `WorkflowHistoryEvent`, `WorkflowHistoryEventType`, `WorkflowResultContract`, `WorkflowStatus`, `WorkflowStepExecutionState`, `WorkflowStepLifecycle`, `WorkflowStepOutcome` | `backends`, `core/runtime` |
| `raes_runtime` | `backend_input_contracts`, `backend_snapshot_contracts` | `backends` |
| `raes_runtime.backend_account_credentials` | `plan_has_account_credentials` | `backends` |
| `raes_runtime.backend_input_contracts` | `RUNTIME_SNAPSHOT_VALUE_LIMITS` | `backends` |
| `raes_runtime.backend_snapshot_contracts` | `_VALUE_LIMITS` | `backends` |
| `raes_runtime.control_plane` | `RuntimeControlPlane` | `backends`, `validation` |
| `raes_runtime.control_plane_execution` | `execute_participant_action` | `backends`, `validation` |
| `raes_runtime.control_plane_security` | `ControlPlaneIdentity`, `ControlPlaneRole`, `ParticipantControlSubjectBinding` | `backends` |
| `raes_runtime.manager` | `RuntimeManager` | `backends` |
| `raes_runtime.operation_supervision_configuration` | `OperationSupervisionConfiguration` | `backends` |
| `raes_runtime.registry` | `ReferenceTimeRuntime`, `RuntimeTarget` | `backends`, `validation` |

### Participant control, crossing, and decision surfaces

Owner: [rae#1794](https://github.com/OpenRAE/rae/issues/1794).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.contracts` | `ParticipantDecisionSurfaceDeliveryV2Model`, `ParticipantDecisionSurfaceDerivationAnchorV2Model`, `ParticipantDecisionSurfaceSelectionV2Model`, `ParticipantDecisionSurfaceV2Model` | `backends` |
| `raes_contracts.contracts.participant_crossing` | `ParticipantCrossingGateDisposition`, `ParticipantCrossingPolicyReferenceModel` | `backends` |
| `raes_contracts.participant_binding_v2` | `ParticipantDecisionSurfaceBindingResolversV2` | `backends` |
| `raes_contracts.participant_decision_surface_delivery` | `deliver_participant_decision_surface_v2` | `backends` |
| `raes_processor.models` | `ParticipantBehaviorProjectionAnchorRequestV2`, `ParticipantDecisionSurfaceActionAssessment`, `ParticipantDecisionSurfaceProjectionInputV2`, `ParticipantExposureAssessment`, `ParticipantExposureAuthorizationRecordV2`, `ParticipantExposurePolicyDecisionV2`, `ParticipantExposureResolversV2`, `project_participant_decision_surface_v2`, `resolve_participant_behavior_projection_anchor_v2`, `resolve_participant_episode_readiness_anchor_v2` | `backends` |
| `raes_runtime.participant_control_intents` | `ParticipantExternalDirectionControlIntent`, `ParticipantProposalControlIntent` | `backends` |
| `raes_runtime.participant_crossing_mediation` | `ParticipantCrossingEvidence`, `ParticipantCrossingIntent`, `ParticipantCrossingPolicyResolution`, `ParticipantCrossingSemanticGates`, `ParticipantCrossingValidationContext` | `backends` |

### Participant execution, episodes, and behavior

Owner: [rae#1795](https://github.com/OpenRAE/rae/issues/1795).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_contracts.contracts` | `ParticipantActionResultModel`, `ParticipantImplementationManifestModel`, `ParticipantImplementationProvenanceModel`, `ParticipantImplementationSelectionModel`, `ParticipantTemporalRuntimeContextModel` | `backends`, `core/archival`, `core/execution`, `core/experiment` |
| `raes_contracts.participant_autonomous_state` | `require_participant_autonomous_runtime_snapshot` | `backends` |
| `raes_contracts.participant_behavior` | `ParticipantBehaviorHistoryEventType`, `ParticipantLifecycleOperationState`, `ParticipantObservationStatus`, `ParticipantPhaseRealization`, `ParticipantRuntimeLifecyclePhase`, `iter_participant_behavior_snapshot_violations` | `backends`, `validation` |
| `raes_contracts.participant_binding` | `ParticipantActionAdmissionRequest`, `ParticipantActionApplyResult`, `ParticipantNativeActionExecution` | `backends`, `validation` |
| `raes_contracts.participant_concurrency` | `iter_participant_concurrency_snapshot_violations` | `validation` |
| `raes_contracts.participant_configuration` | `ConfigurationOverrideModel`, `realize_participant_configuration`, `validate_participant_configuration_selection` | `backends`, `core/experiment` |
| `raes_contracts.participant_episode` | `ParticipantEpisodeExecutionState`, `ParticipantEpisodeHistoryEventType`, `ParticipantEpisodeTerminalReason`, `iter_participant_episode_snapshot_violations` | `backends`, `validation` |
| `raes_contracts.participant_native_execution` | `ParticipantNativeActionExecution` | `backends` |
| `raes_contracts.participant_shared_state` | `iter_participant_shared_state_snapshot_violations` | `validation` |

### Backend conformance

Owner: [rae#1796](https://github.com/OpenRAE/rae/issues/1796).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_conformance.conformance` | `BackendConformanceReport`, `run_target_conformance` | `validation` |

### Run materialization archive

Owner: [rae#1797](https://github.com/OpenRAE/rae/issues/1797).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_operations.run_artifacts` | `RunMaterializationArchive`, `is_valid_run_id_label` | `backends` |

### Pack static validation

Owner: [env-packs#564](https://github.com/OpenRAE/env-packs/issues/564).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_env_packs` | `validate_pack` | `core` |

### Pack content identity and artifact resolution

Owner: [env-packs#565](https://github.com/OpenRAE/env-packs/issues/565).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_env_packs` | `PackDigestError`, `resolve_pack_artifact`, `validate_pack_content_manifest` | `aptl_techvault`, `backends`, `core`, `core/deployment` |

### Pack catalog

Owner: [env-packs#572](https://github.com/OpenRAE/env-packs/issues/572).

| Module | Names | LilRAE areas |
| --- | --- | --- |
| `raes_env_packs.catalog` | `Source`, `build_catalog` | `core` |

## Extended classes

LilRAE extends three RAES classes. In RAES 10.1.0, `RuntimeManager` is another
name for `RuntimeControlPlane`, so two of the classes extend the same base.
LilRAE also uses private RAES members. Go has no inheritance. The Go port uses
the extension points that RAES Go sets for this behavior, and it is blocked on
the owner issue until they exist. It does not copy a base class, and it does
not change RAES state that is not public.

| LilRAE class | RAES base | Overrides and the behavior that they add | Private RAES members | Owner |
| --- | --- | --- | --- | --- |
| `AptlRuntimeManager` in `backends/raes_planning_compat.py` | `raes_runtime.manager.RuntimeManager` | `__init__` binds the scenario bundle, the admitted planning compatibility decision, and native evidence capture. `apply` runs in the admitted runtime node budget, then captures native evidence. `refresh_inventory` and `evaluate` capture native evidence after the RAES call. `plan` compiles the scenario once, applies the admitted compatibility change, and plans against the committed snapshot. | `_target`. `_runtime_value_limits` replaces `raes_runtime.backend_input_contracts.RUNTIME_SNAPSHOT_VALUE_LIMITS` and the private `raes_runtime.backend_snapshot_contracts._VALUE_LIMITS` during a call, under a process lock. | [rae#1791](https://github.com/OpenRAE/rae/issues/1791) |
| `AptlParticipantControlPlane` in `backends/raes_participant_driver.py` | `raes_runtime.control_plane.RuntimeControlPlane` | No override. It adds `solicit_participant_selection`, which RAES does not have. The method runs the provider solicitation through `execute_participant_action`. Thus the operation is durable before the provider runs, and a timeout or malformed output becomes a failed operation. | `_target`, `_reject_submission` | [rae#1791](https://github.com/OpenRAE/rae/issues/1791) |
| `AptlParticipantRuntime` in `backends/raes_participant_runtime.py` | `raes_backend_protocols.participant_runtime_base.BaseParticipantRuntime` | `__init__` binds the deployment backend, the action specifications, the plan authority, and the autonomous bindings. `admit_actions_concurrently` checks each installed binding before RAES dispatches the batch. `admit_action` keeps the committed behavior history and publishes the action evidence. A publication failure adds diagnostics and keeps the accepted transition. `status` adds the backend name, the action participants, and the scenario source digest. `_model_action` sends an admitted action to its LilRAE realization. | `_model_action`, a private method that the class overrides | [rae#1790](https://github.com/OpenRAE/rae/issues/1790) |

## Stored and adapter-visible types

LilRAE stores these RAES documents. The published RAES schemas in
`contracts/schemas/` are normative, so the Go port can validate a stored
document against its schema without a local model.

| RAES contract | Where LilRAE stores it | Owner |
| --- | --- | --- |
| `experiment-run-v1` (`ExperimentRunModel`) | The sealed archival run record (`core/archival/coordinator.py`). | [rae#1788](https://github.com/OpenRAE/rae/issues/1788) |
| `experiment-evidence-record-v1` (`ExperimentEvidenceRecordModel`) | The evidence records (`core/evidence/_persist.py`), which evidence bundles carry. | [rae#1788](https://github.com/OpenRAE/rae/issues/1788) |
| `runtime-snapshot-v1` (`RuntimeSnapshot`) | A value-free projection in the reproducibility record (`backends/raes_repro.py`), and the runtime evidence (`backends/lilrae_runtime_evidence.py`). | [rae#1791](https://github.com/OpenRAE/rae/issues/1791) |
| `backend-manifest-v2` | The reproducibility record (`backends/raes_repro.py`). | [rae#1790](https://github.com/OpenRAE/rae/issues/1790) |
| Materialization archive records (`MaterializationArchiveRecord`) | The run materialization archive (`backends/lilrae_materialization_archive.py`), through `RunMaterializationArchive`. | [rae#1790](https://github.com/OpenRAE/rae/issues/1790), [rae#1797](https://github.com/OpenRAE/rae/issues/1797) |

The scenario adapter API of
[family adapters](../reference/family-adapters.md) passes these RAES types to
an adapter. Go port 16 ([#1567](https://github.com/OpenRAE/lilrae/issues/1567))
defines that API in Go with the RAES Go types that rae sets.

| RAES type | Role in the adapter API | Owner |
| --- | --- | --- |
| `AdmittedTrialPlanModel` | The sealed trial plan in `FamilyTrialInput`. | [rae#1788](https://github.com/OpenRAE/rae/issues/1788) |
| `ExpandedScenario` | The validated family in `FamilyTrialInput`. | [rae#1783](https://github.com/OpenRAE/rae/issues/1783) |
| `InstantiatedScenario` | The scenario of an admitted family trial. | [rae#1783](https://github.com/OpenRAE/rae/issues/1783) |
| Canonical instantiated SDL bytes and digest | The snapshot of an admitted family trial. | [rae#1783](https://github.com/OpenRAE/rae/issues/1783) |
| `TrialInstantiationProvenance` | The provenance of an admitted family trial. | [rae#1783](https://github.com/OpenRAE/rae/issues/1783) |
| `ParticipantConfigurationResultModel` | The participant configuration results of an admitted family trial. | [rae#1788](https://github.com/OpenRAE/rae/issues/1788) |

## Conformance

The LilRAE Go backend must pass the RAES backend conformance suite for the
target that `backends/identity.py` declares: `aptl` 0.1.0 with the
`full-remote-control-plane` profile. Today the suite has two parts:

- `raes_conformance.conformance.run_target_conformance`, which
  `validation/_gate_checks.py` runs against the target.
- `raes conformance backend --profile full-remote-control-plane`, which
  `validation/_gate_raes_cli.py` runs in the RAES scenario validation gate of
  CI.

[rae#1796](https://github.com/OpenRAE/rae/issues/1796) ports both parts to Go.
The Go backend is the system under test. A pass of the Python backend is no
evidence for the Go backend. The LilRAE black-box suite in `conformance/` and
the [serialization vectors](../reference/serialization-schemes.md) are separate
evidence, and neither replaces the RAES suite.

## Names without a named owner

The owner issues name their scope with module lists and examples. No owner
issue names the modules of these names. The inventory assigns each name to the
owner of its capability. When rae or env-packs puts a name in another issue,
the inventory follows that choice.

| Capability | Owner that follows from the capability | Names |
| --- | --- | --- |
| SDL models, semantic validation, and canonical identity | [rae#1783](https://github.com/OpenRAE/rae/issues/1783) | `raes.accounts.Account`, `raes.prospective_content.admit_prospective_content`, `raes.realization_designation.designation_records`, `raes.realization_designation.resolve_realization_designation` |
| Shared primitives | [rae#1779](https://github.com/OpenRAE/rae/issues/1779) | `raes_contracts.contracts.RandomStreamDrawRecordModel` |
| Contract bindings, diagnostics, and the published corpus | [rae#1780](https://github.com/OpenRAE/rae/issues/1780) | `raes_contracts.associated_artifacts.AssociatedArtifactManifestModel`, `raes_contracts.associated_artifacts.AssociatedArtifactValidationLimits`, `raes_contracts.associated_artifacts.load_associated_artifact_manifest_json`, `raes_contracts.associated_artifacts.validate_associated_artifact_manifest`, `raes_contracts.diagnostics.Diagnostic`, `raes_contracts.diagnostics.Severity` |
| Processor compiler, planner, and realization semantics | [rae#1787](https://github.com/OpenRAE/rae/issues/1787) | `raes_contracts.artifact_requirements.ArtifactAvailabilityContext`, `raes_contracts.augmentation_preparation.AugmentationEffect`, `raes_contracts.augmentation_preparation.AugmentationPreparation`, `raes_contracts.contracts.ArtifactAcquisitionTimingModel`, `raes_contracts.contracts.ArtifactAvailabilityContext`, `raes_contracts.contracts.ArtifactMechanismCapability`, `raes_contracts.contracts.ArtifactRequirementAvailability`, `raes_contracts.plan_projection.runtime_plan_digest`, `raes_contracts.planning.PlanScope`, `raes_contracts.realization_collections.node_collection_members`, `raes_contracts.realization_preparation.RealizationPreparation`, `raes_contracts.realization_preparation.preparation_snapshot_digest`, `raes_contracts.realization_structure.evaluate_realization_constraint`, `raes_contracts.realization_structure.validate_realization_value`, `raes_contracts.run_scope.PlanScope` |
| Experiments, trial plans, and experiment records | [rae#1788](https://github.com/OpenRAE/rae/issues/1788) | `raes_contracts.contracts.capabilities.ApparatusIdentityModel` |
| Backend contracts, interfaces, manifests, and realization envelopes | [rae#1790](https://github.com/OpenRAE/rae/issues/1790) | `raes_contracts.apparatus.ConceptBinding`, `raes_contracts.apparatus.ProcessResourceLimitCapability`, `raes_contracts.apparatus.RealizationObservationCapability`, `raes_contracts.apparatus.RealizationSupportDeclaration`, `raes_contracts.contracts.materialization_attestation.MaterializationArchiveRecord`, `raes_contracts.manifest_authority.BACKEND_SUPPORTED_CONTRACT_IDS`, `raes_contracts.manifest_authority.PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS`, `raes_contracts.materialization.MATERIALIZATION_MAX_BYTES`, `raes_contracts.materialization.MaterializationSubmission`, `raes_contracts.materialization.require_materialization_records`, `raes_contracts.materialization_inventory.RuntimeDescendantBinding`, `raes_contracts.materialization_inventory.RuntimeInventoryEvidence`, `raes_contracts.materialization_inventory.RuntimeInventoryReport` |
| Runtime control plane, snapshots, and results | [rae#1791](https://github.com/OpenRAE/rae/issues/1791) | `raes_contracts.account_credentials.account_placement_has_credential_bindings`, `raes_contracts.account_credentials.value_free_account_placement_payload` |
| Participant execution, episodes, and behavior | [rae#1795](https://github.com/OpenRAE/rae/issues/1795) | `raes_contracts.contracts.ParticipantImplementationManifestModel`, `raes_contracts.contracts.ParticipantImplementationProvenanceModel`, `raes_contracts.contracts.ParticipantImplementationSelectionModel` |
