# Serialization Schemes

This inventory lists the byte and identity schemes that the Python
implementation uses for persisted and compared values, and the vectors that
define them. The [serialization vectors design](../architecture/issue-1555-serialization-vectors-design.md)
gives the corpus format. The Python tests in
`tests/test_serialization_vectors.py` call the owner of each scheme with each
vector. The Go ports must pass the same vectors.

Two schemes that share a hash or a serializer are different schemes when their
input, options, framing, or digest spelling differ. A changed scheme is a
functional change.

## Canonical JSON

| Scheme | Owner | Byte form | Stored or compared by | Vectors |
| --- | --- | --- | --- | --- |
| RFC 8785 | `rfc8785.dumps` (rfc8785 0.1.4) | RFC 8785: UTF-16 key order, ECMAScript numbers, raw UTF-8. Integers outside the safe range, NaN, and infinities are rejected. | Each RFC 8785 owner below. | `conformance/testdata/vectors/rfc8785.json` |
| Sorted compact JSON | `json.dumps(sort_keys=True, separators=(",", ":"))`, UTF-8 | Code point key order, `\uXXXX` escapes for non-ASCII text, `1.0` for a float, and `NaN` and `Infinity` written. | The credential descriptor digest, and the owners that hash or write sorted JSON. | `conformance/testdata/vectors/sorted-compact-json.json` |
| Compose ownership JSON | `core/deployment/_compose_resource_ownership.py:_canonical_json` | Sorted compact JSON and a final LF. | The workspace identity and the resource receipts under `.aptl/lifecycle/resource-receipts-v1`. | `conformance/testdata/vectors/compose-ownership-json.json` |
| Run store canonical payload | `core/runstore_internals.py:_canonicalize_payload` | A JSON round trip, then RFC 8785. `json.dumps` accepts NaN, and RFC 8785 then rejects it. | The create-once JSON files of the run store, such as `experiment-plans/<plan_id>`. | `conformance/testdata/vectors/runstore-canonical-payload.json` |

## Digests and identities

| Scheme | Owner | Input and form | Stored or compared by | Vectors |
| --- | --- | --- | --- | --- |
| Raw bytes SHA-256 | `hashlib.sha256` | All bytes of a file, blob, or archive, without decoding. Lowercase hex. | File, blob, member, and archive checksums. | `conformance/testdata/vectors/sha256-bytes.json` |
| Credential descriptor digest | `core/_credential_sources.py:ProcessEnvironmentCredentialSource.descriptor_digest` | `sha256:` and the hex SHA-256 of the sorted compact JSON of the descriptor. | `descriptor_sha256` in the configuration identity of the provenance record and in the participant source binding. | `conformance/testdata/vectors/credential-descriptor-digest.json` |
| Provenance identity | `core/provenance/identity.py:derive_identity` | `sha256:` and the hex SHA-256 of RFC 8785 of `{"domain": <versioned separator>, "payload": ...}`. An unsafe domain or a value that RFC 8785 rejects is an error. | The identities of the provenance record and its providers. | `conformance/testdata/vectors/provenance-identity.json` |
| Source set digest | `core/experiment/trial_plan.py:compute_source_set_digest` | `sha256:` and the hex SHA-256 of RFC 8785 of the source set projection. | `source_set_digest` of the admitted trial plan. | `conformance/testdata/vectors/source-set-digest.json` |
| Evidence record ID | `core/evidence/records.py:derive_evidence_record_id` | The record ID prefix and the hex SHA-256 of RFC 8785 of the identity projection, with sorted window references. | The ID and the file name of each evidence record. | `conformance/testdata/vectors/evidence-record-id.json` |
| Artifact profile digest | `backends/raes_artifact_mechanisms.py:_profile_digest` | `sha256:` and the hex SHA-256 of the sorted compact JSON of a profile body. | The digest of the `exact-artifact` mechanism profile. | `conformance/testdata/vectors/artifact-profile-digest.json` |
| Participant selection fingerprint | `backends/raes_participant_control_evidence.py:selection_fingerprint` | `sha256:` and the hex SHA-256 of sorted compact JSON with ASCII escapes. | The fingerprint of a participant selection in the control evidence. | `conformance/testdata/vectors/participant-selection-fingerprint.json` |
| Governed arguments digest | `backends/raes_participant_execution_support.py:mapping_digest` | The same form as the selection fingerprint. | The digest of normalized governed arguments. | `conformance/testdata/vectors/governed-arguments-digest.json` |
| Participant workflow digest | `backends/raes_participant_fixture_core.py:_mapping_digest` | The same form as the selection fingerprint. | The digests of the bounded participant workflow. | `conformance/testdata/vectors/participant-workflow-digest.json` |
| Boundary policy digest | `core/deployment/_boundary_validation.py:canonical` and `digest` | `sha256:` and the hex SHA-256 of sorted compact JSON text. | The identity of the enforcement input of the boundary. | `conformance/testdata/vectors/boundary-policy-digest.json` |
| Correlation content signature | `core/correlation/_extract.py:_content_signature` | `json.dumps` with sorted keys, the default separators, and `default=str`. Not hashed. | The grouping of byte-identical raw records before the correlation references are derived. | `conformance/testdata/vectors/correlation-content-signature.json` |
| Apparatus mapping digest | `backends/raes_participant_apparatus.py:canonical_mapping_digest` | `sha256:` and the hex SHA-256 of RFC 8785. | The digest of one apparatus mapping. | `conformance/testdata/vectors/apparatus-mapping-digest.json` |
| Declared artifact digest | `backends/_raes_proposition_truth.py:_declared_artifact_digest` | `sha256:` and the hex SHA-256 of RFC 8785. | The digest of one declared-state projection. | `conformance/testdata/vectors/declared-artifact-digest.json` |
| Evidence cut key | `backends/_raes_evidence_truth_refresh.py:evidence_cut_key` | `aptl-native-evidence-` and the hex SHA-256 of the sorted compact JSON of the RAES evidence record models. | The key of one evidence collection, which RAES requires to be new for each one. | `conformance/testdata/vectors/evidence-cut-key.json` |
| Bundle identity | `core/evidence_bundle/envelope.py:BundleEnvelopeV1` and `verify.py:_root_identity` | The root identity is `sha256:` and the hex SHA-256 of RFC 8785 of the envelope without `created_at` and `seal`. `bundle.json` is RFC 8785 of the whole envelope without null fields. The verifier recomputes the root from the parsed document. | `bundle.json` and `seal.root_identity` of an evidence bundle, and `lilrae runs verify-bundle`. | `conformance/testdata/vectors/bundle-identity.json` |
| Collector registration digest | `core/experiment/capture_registry.py:CollectorRegistration.effective_config_digest` | `sha256:` and the hex SHA-256 of RFC 8785 of the declaration projection, with each set sorted. | `effective_config_digest` of each capture binding in the trial plan, which runtime verifies. | `conformance/testdata/vectors/collector-registration-digest.json` |
| Correlation projection | `core/correlation/models.py:CorrelationProjection` | RFC 8785 of the canonical projection, and `sha256:` and its hex SHA-256. A dangling edge or an unknown reference kind is rejected. | The correlation projection of a run and its `projection_digest`. | `conformance/testdata/vectors/correlation-projection.json` |
| Trial plan | `core/experiment/trial_plan_models.py:canonicalize_trial_plan` | RFC 8785 of the `aptl-experiment-trial-plan/v3` projection, its `sha256:` digest, and the `plan-` ID. | The trial plan file, its digest, and its plan ID. | `conformance/testdata/vectors/trial-plan.json` |
| Seat launch descriptor | `appliance/seat/launch_descriptor.py:canonical_launch_bytes` | RFC 8785 of the `aptl.appliance-launch/v2` or `v3` descriptor. A `v3` descriptor needs exactly one desktop mode. | The launch descriptor that the seat guest authenticates. | `conformance/testdata/vectors/seat-launch-bytes.json` |
| Seat policy digest | `appliance/seat/lifecycle.py:_canonical_policy_digest` | `sha256:` and the hex SHA-256 of RFC 8785 of the `aptl.appliance-boundary/v1` policy. | `boundary_policy_digest` of the launch descriptor, which binds the boundary gate. | `conformance/testdata/vectors/seat-policy-digest.json` |
| Flag token | `core/flags.py:verify_token` | `aptl:v1:<hostname>:<level>:<nonce>:<signature>`, where the signature is the hex MD5 of `key:hostname:level:nonce`. | The flags that the lab plants and checks. | `conformance/testdata/vectors/flag-token.json` |
| Locator digest | `core/experiment/resolver.py:_digest_hex` | Lowercase hex BLAKE3, SHA-256, or SHA-512 of the artifact bytes. | The integrity check of each experiment artifact locator, and the `sha256:` digest of each resolved artifact. | `conformance/testdata/vectors/locator-digest.json` |

## Parsers

| Scheme | Owner | Rule | Readers | Vectors |
| --- | --- | --- | --- | --- |
| YAML safe load | `yaml.safe_load` (PyYAML 6.0.3) | YAML 1.1: `yes`, `no`, `on`, and `off` are booleans, `0755` is octal, `1:30` is sexagesimal, a float needs a dot, dates and times are typed, merge keys apply, a duplicate key keeps the last value, keys that compare equal in Python merge, and a second document or an unknown tag is rejected. | `docker-compose.yml` and the generated Compose files (`backends/raes_profiles.py`, `core/host_ports.py`, `core/lab.py`, `core/deployment/_compose_build_dedupe.py`, `_compose_substrate_gate.py`, `_compose_observability.py`), the capture configuration (`_compose_capture_config.py`), the certificate provenance (`_stateful_certificates.py`), `generate-indexer-certs.yml` and the Compose services (`appliance/input_images.py`), and the image digests that Docker prints (`_compose_image_realization.py`). | `conformance/testdata/vectors/yaml-safe-load.json` |
| YAML Compose loader | `core/deployment/_compose_ownership_override.py:_ComposeLoader` | The safe loader and the Compose `!reset` tag, which returns the scalar text, the list, or the mapping. | The Compose files that the ownership override merges. | `conformance/testdata/vectors/yaml-compose-loader.json` |
| Experiment YAML preflight | `core/experiment/spec_loading.py:_yaml_duplicate_key_preflight` | A safe loader that rejects a duplicate key, a merge key, a second document, and an unknown tag before the public RAES loader parses the file. | The experiment root, task, capture specification, and participant manifest. | `conformance/testdata/vectors/experiment-yaml-preflight.json` |
| Strict JSON | `utils/strict_json.py:loads_strict` | JSON that rejects a duplicate member, `NaN`, `Infinity`, invalid UTF-8, and trailing data. | The security-sensitive JSON readers that call it. Other readers use `json.loads`, which accepts duplicates and non-finite constants. | `conformance/testdata/vectors/strict-json.json` |

RAES parses the SDL scenarios with its own loader; RAES owns those parse
results. A parse result that JSON cannot carry has a tag in the corpus: `$float`,
`$int`, `$date`, `$datetime`, `$bytes_hex`, and `$map` for a mapping with a key
that is not a string.

The Go ports decode YAML and JSON strictly (ADR-065). Where a Python reader
accepts more, such as a duplicate key in a Compose file, the vector records the
current result, and the Go port that owns the reader states its compatibility
decision.

## Timestamps

| Scheme | Owner | Form | Stored or compared by | Vectors |
| --- | --- | --- | --- | --- |
| UTC now with Z | `core/correlation/clock.py:utc_now` | `datetime.isoformat` in UTC with `+00:00` replaced by `Z`. A zero fraction is omitted; any other fraction has six digits. | The clock contexts and the other callers of the canonical UTC formatter. | `conformance/testdata/vectors/utc-now.json` |
| Continuity now | `core/continuity.py:_utc_now_iso` | `datetime.isoformat` in UTC with `+00:00`. | The timestamps of the continuity findings. | `conformance/testdata/vectors/continuity-now.json` |
| Workflow next timestamp | `core/runtime/workflow_engine.py:_next_timestamp` | Parses the previous timestamp (a `Z` or an offset, or a naive value that stays naive), adds the offset in milliseconds, and writes `Z` for UTC. | The ordered timestamps of the workflow history. | `conformance/testdata/vectors/workflow-next-timestamp.json` |

## Names

| Scheme | Owner | Rule | Stored or compared by | Vectors |
| --- | --- | --- | --- | --- |
| Participant session ID | `backends/_raes_participant_execution.py:_ParticipantDeliveryExecutor._session_id` | UUID 5 in the URL namespace of `aptl:<run_id>:<participant_address>`. | The session of a participant role, for conversation continuity. | `conformance/testdata/vectors/participant-session-id.json` |
| Run store ID | `core/runstore_internals.py:_validate_id` | ASCII word characters, dots, and hyphens, starting with a word character, without `..`. | Run, trace, and correlation IDs and the run directory names. | `conformance/testdata/vectors/run-store-id.json` |
| Workspace names | `core/deployment/_compose_resource_ownership.py:WorkspaceOwnership` | The project name is the logical name, cut to fit, `-w`, and the first 12 characters of the workspace ID. A container name puts `w` and those characters after `aptl-`, or before the semantic name. The labels name the workspace, the project, and the attempt. | The Compose project, the container names, and the owner labels of the lab, and the workspace state file. | `conformance/testdata/vectors/workspace-names.json` |
| Compose project name | `core/config.py:validate_compose_project_name` | 1 to 63 lowercase letters, digits, hyphens, or underscores, starting with a letter or a digit. | `deployment.project_name` of `aptl.json`. | `conformance/testdata/vectors/compose-project-name.json` |
| Startup run ID | `core/lab.py` (the run of `lilrae lab start`) | `run_`, the UTC start as `YYYYMMDDTHHMMSSZ`, `_`, and 12 lowercase hex characters of a random UUID. | The run directory and `run_id` of the run record. | No vector: the suffix is random. The run store ID vectors cover its validation. |
| Random identifiers | `uuid.uuid4` and `secrets.token_hex` or `token_urlsafe` at their call sites | A random UUID or token of a fixed length. | Workspace IDs, nonces, attempt IDs, and generated credentials. | No vector: the values are random. The workspace names vectors cover the use of a workspace ID. |

## Generated files with stored digests

The Go code must keep the bytes of these files, because a record stores or
compares their digest.

| File | Producer | Record and field | Coverage |
| --- | --- | --- | --- |
| The compiled runtime model | `backends/raes_runtime_model_artifact.py:compiled_runtime_model_bytes` | The content digest of the compiled model artifact (`compiled_runtime_model_sha256`), which the runtime freeze uses. Its bytes are RFC 8785 of an `aptl.raes-runtime-model-artifact/v1` envelope and a final LF. | No file vector: its input is a compiled RAES model, which RAES owns. The RFC 8785 vectors cover its serializer. |
| The project configuration files | Lab init and the rendered configuration | `backend_evidence.config_digests` of the run record, from the range snapshot. | The raw bytes SHA-256 vectors cover the digest. |
| The detection content | The detection rules of the project | `backend_evidence.detection_content_digest` of the run record. | The raw bytes SHA-256 vectors cover the digest. |
| The evidence blobs | `core/evidence/content_store.py` | The content-addressed blob names and the checksums of the evidence records. | The raw bytes SHA-256 vectors cover the digest. |
| `bundle.json` and the bundle members | `core/evidence_bundle/` | The root identity, the seal, and the member digests of the bundle inventory. | `conformance/testdata/vectors/bundle-identity.json` |
| The workspace state and the resource receipts | `core/deployment/_compose_resource_ownership.py` | A retry accepts only byte-identical receipt bytes. | `conformance/testdata/vectors/compose-ownership-json.json` |
| The seat launch descriptor | `appliance/seat/launch_descriptor.py` | The guest authenticates the descriptor bytes and the policy digest that they carry. | `conformance/testdata/vectors/seat-launch-bytes.json` |

## Other call sites

The owners below use the base schemes of this inventory: RFC 8785, sorted
compact JSON, and raw bytes SHA-256. The base vectors define those serializers
and the hash. No vector of its own pins the projection that each of these
owners builds; the owner tests cover it. The Go port that ports an owner adds
its owner vectors to this corpus.

| Scheme | Owner | Rule | Stored or compared by | Vectors |
| --- | --- | --- | --- | --- |
| Parquet canonical JSON | `core/evidence_bundle/projections/parquet.py:_canonical_json` | RFC 8785 decoded as text. The current code decodes as ASCII and rejects a non-ASCII reference (#1598); `dev` fixes it in #1599. | The `source_refs` and `provenance_refs` columns of the Parquet projection. | `conformance/testdata/vectors/parquet-canonical-json.json` |

### RFC 8785 owners

| File | Functions |
| --- | --- |
| `aptl/appliance/policy.py` | `write_full_techvault_boundary_policy` |
| `aptl/appliance/seat/access.py` | `encode_guest_access_bundle`, `publish_guest_access_request` |
| `aptl/appliance/seat/lifecycle.py` | `stage_seat` |
| `aptl/appliance/seat/observation.py` | `observation_id_for` |
| `aptl/appliance/seat/overlay_identity.py` | `_persist_create_once` |
| `aptl/appliance/seat/persistence.py` | `persist_seat_record` |
| `aptl/appliance/seat/readiness.py` | `encode_guest_readiness`, `publish_readiness_challenge` |
| `aptl/backends/raes_participant_candidates.py` | `candidate_selections` |
| `aptl/backends/raes_runtime_model_artifact.py` | `compiled_runtime_model_bytes` |
| `aptl/core/evidence_bundle/projections/jsonl.py` | `project` |
| `aptl/core/execution/assembly.py` | `write_lifecycle_evidence` |
| `aptl/core/experiment/bindings.py` | `_apparatus_configuration` |
| `aptl/core/experiment/capture_plan.py` | `admit_capture_demands` |
| `aptl/core/provenance/providers/apparatus.py` | `collect` |
| `aptl/core/provenance/providers/runtime_facts.py` | `_gather` |

### Sorted JSON owners

| File | Functions |
| --- | --- |
| `aptl/appliance/guest_surfaces.py` | `<module>` |
| `aptl/appliance/seat/image.py` | `cache_seat_image_config` |
| `aptl/appliance/seat/image_disk_cache.py` | `write_verification_stamp` |
| `aptl/appliance/seat/image_selection.py` | `save_selection` |
| `aptl/appliance/seat/image_trust.py` | `publish_verified_image` |
| `aptl/appliance/seat/vm.py` | `write_vm_pid` |
| `aptl/backends/_raes_participant_crossing.py` | `_delivery_crossing_policies` |
| `aptl/backends/_raes_participant_evidence.py` | `stop` |
| `aptl/backends/_raes_participant_transport.py` | `_render_runtime_profile_config` |
| `aptl/backends/lilrae_runtime_evidence.py` | `_json_bytes` |
| `aptl/backends/raes_evidence_acquisition.py` | `_mark_transcript_finalized`, `mark_transcript_activation_failed`, `mark_transcript_finalization_failed`, `persist_active_transcript_authority` |
| `aptl/backends/raes_participant_provider.py` | `_compact_selection_prompt`, `select` |
| `aptl/backends/scenario_family.py` | `encode_family_target` |
| `aptl/cli/seat.py` | `_emit` |
| `aptl/core/appliance_boundary.py` | `render_egress_proxy_policy` |
| `aptl/core/archival/discovery_index.py` | `_render_line` |
| `aptl/core/deployment/lilrae_docker_recording.py` | `_encode` |
| `aptl/core/deployment/lilrae_native_evidence.py` | `record_cleanup` |
| `aptl/core/lifecycle_policy.py` | `save_state` |
| `aptl/core/operator_group_state.py` | `load_admitted_operator_groups`, `persist_admitted_operator_groups` |
| `aptl/core/startup_reset_state.py` | `_encode` |
| `aptl/validation/_live_gate_probes.py` | `_matched_alert_summary` |
| `aptl/validation/participant_qualification_evidence.py` | `participant_qualification_attestation_payload` |
| `aptl/workbench/decision_schema.py` | `admit_decision_response_schema` |
| `aptl/workbench/profiles.py` | `render_profile_config` |
| `aptl_techvault/build_cache.py` | `<module>`, `_dependency_only_manifest` |
| `aptl_techvault/evidence/techvault.py` | `_bounded_json`, `_sqli_result` |
| `aptl_techvault/evidence/techvault_enrollment_baseline.py` | `record_enrollment_baseline` |
| `aptl_techvault/evidence/techvault_misp_readiness.py` | `_readiness_document` |
| `aptl_techvault/evidence/techvault_readiness.py` | `fetch` |
| `aptl_techvault/evidence/techvault_readiness_probes.py` | `bounded_json` |
| `aptl_techvault/evidence/techvault_transcript.py` | `_transcript_result` |
| `aptl_techvault/evidence/techvault_wazuh_agent_readiness.py` | `_readiness_document` |

### SHA-256 owners

| File | Functions |
| --- | --- |
| `aptl/appliance/access_service_support.py` | `_descriptor_digest` |
| `aptl/appliance/download.py` | `_file_identity` |
| `aptl/appliance/guest_observation.py` | `_read_guest_boot_id` |
| `aptl/appliance/seat/image_disk_cache.py` | `_sha256_of` |
| `aptl/appliance/seat/image_selection.py` | `_selection_path` |
| `aptl/appliance/seat/image_trust.py` | `_key_path`, `configure_trust`, `verify_cached_image`, `verify_remote_image` |
| `aptl/appliance/seat/launch_descriptor.py` | `verify_seat_launch` |
| `aptl/appliance/seat/lifecycle.py` | `_launch_descriptor_digest` |
| `aptl/appliance/seat/observation.py` | `observation_id_for` |
| `aptl/appliance/seat/overlay_identity.py` | `_new_identity` |
| `aptl/backends/_raes_participant_crossing.py` | `_delivery_crossing_policies` |
| `aptl/backends/_raes_participant_evidence.py` | `_delivery_record` |
| `aptl/backends/_raes_participant_transport.py` | `_private_file_sha256` |
| `aptl/backends/_raes_stateful_observation.py` | `_artifact_evidence` |
| `aptl/backends/lilrae_apparatus_reporting.py` | `apparatus_node_name` |
| `aptl/backends/lilrae_materialization_archive.py` | `read` |
| `aptl/backends/lilrae_participant_configuration.py` | `configured_opencode_executor` |
| `aptl/backends/lilrae_runtime_evidence.py` | `_artifact_bytes`, `_blob`, `_collect_native` |
| `aptl/backends/raes_artifact_availability.py` | `_materialized_specifications` |
| `aptl/backends/raes_content_satisfaction.py` | `_resolved_content_digest` |
| `aptl/backends/raes_docker_materializer.py` | `place_file` |
| `aptl/backends/raes_image_realization.py` | `_materialized_component_image` |
| `aptl/backends/raes_participant_actions.py` | `_observation_event`, `_shared_state_records` |
| `aptl/backends/raes_participant_candidates.py` | `candidate_selections` |
| `aptl/backends/raes_participant_driver.py` | `__post_init__` |
| `aptl/backends/raes_participant_evidence_publication.py` | `persist_action_evidence` |
| `aptl/backends/raes_participant_fixture_core.py` | `participant_episode_state_dir` |
| `aptl/backends/raes_participant_projection.py` | `_render_visible_context` |
| `aptl/backends/raes_participant_support.py` | `binding_post_state_digest` |
| `aptl/backends/raes_repro.py` | `_raes_lock_digest` |
| `aptl/backends/raes_runtime_model_artifact.py` | `compiled_runtime_model_sha256` |
| `aptl/core/appliance_boundary.py` | `load_boundary_policy` |
| `aptl/core/archival/seal.py` | `build_inventory_entry` |
| `aptl/core/archival/verify.py` | `_verify_inventory`, `verify_sealed_archive` |
| `aptl/core/certs.py` | `_cert_generator_project_name` |
| `aptl/core/correlation/identity.py` | `stable_ref` |
| `aptl/core/deployment/_boundary_validation.py` | `digest` |
| `aptl/core/deployment/_compose_artifact_paths.py` | `artifact_environment_file_path` |
| `aptl/core/deployment/_compose_environment.py` | `sourced_environment_file` |
| `aptl/core/deployment/_compose_ownership_override.py` | `write_compose_ownership_override` |
| `aptl/core/deployment/_compose_resource_ownership.py` | `_receipt_path` |
| `aptl/core/deployment/_forwarding_agent_realization.py` | `_file_digest_matches` |
| `aptl/core/deployment/_wazuh_agent_realization.py` | `_file_digest_matches` |
| `aptl/core/deployment/lilrae_docker_recording.py` | `__init__`, `recording_digest` |
| `aptl/core/deployment/lilrae_native_evidence.py` | `_directory`, `_receipt_artifacts`, `record_cleanup` |
| `aptl/core/evidence/content_store.py` | `create_content_addressed` |
| `aptl/core/evidence_bundle/_io.py` | `_stream` |
| `aptl/core/evidence_bundle/archive.py` | `_member_bytes` |
| `aptl/core/evidence_bundle/envelope.py` | `root_identity` |
| `aptl/core/evidence_bundle/inventory.py` | `envelope_member` |
| `aptl/core/evidence_bundle/projections/jsonl.py` | `project` |
| `aptl/core/evidence_bundle/schemas.py` | `resolve_schema` |
| `aptl/core/evidence_bundle/verify.py` | `_sha256_hex` |
| `aptl/core/execution/assembly.py` | `write_lifecycle_evidence` |
| `aptl/core/execution_boundary.py` | `_digest` |
| `aptl/core/experiment/bindings.py` | `_apparatus_configuration` |
| `aptl/core/experiment/capture_plan.py` | `admit_capture_demands` |
| `aptl/core/experiment/trial_plan.py` | `_derive_planned_trial_id`, `_derive_seed` |
| `aptl/core/exporter.py` | `_sha256_file` |
| `aptl/core/lab.py` | `_persist_cleanup_actions` |
| `aptl/core/operator_group_state.py` | `load_admitted_operator_groups`, `persist_admitted_operator_groups` |
| `aptl/core/provenance/identity.py` | `digest_bytes` |
| `aptl/core/snapshot.py` | `_hash_config_files` |
| `aptl/core/startup_reset_state.py` | `_read_record`, `persist_cleanup_action` |
| `aptl/utils/deterministic_archive.py` | `hash_file_nofollow` |
| `aptl/validation/_gate_no_start_backend.py` | `_simulated_digest` |
| `aptl/validation/_live_gate_models.py` | `make_live_gate_report` |
| `aptl/validation/_live_gate_probes.py` | `_matched_alert_summary` |
| `aptl/validation/participant_profile.py` | `_read_reference`, `_resolve_pack_profile`, `load_participant_profile` |
| `aptl/validation/participant_qualification_evidence.py` | `_load_evidence_json`, `verify_participant_qualification_attestation` |
| `aptl/validation/techvault_live_gate.py` | `_verification_identities` |
| `aptl/workbench/agent.py` | `_assert_config_unchanged`, `_load_server_config` |
| `aptl/workbench/app.py` | `<module>` |
| `aptl/workbench/browser_mcp.py` | `terminal_page` |
| `aptl/workbench/client_files.py` | `_digest` |
| `aptl/workbench/codex_agent.py` | `_sealed_output_schema` |
| `aptl/workbench/dispatch.py` | `key_fingerprint` |
| `aptl/workbench/lilrae_opencode.py` | `__init__`, `_verify_profile_config` |
| `aptl/workbench/runtime.py` | `_sha256_text` |
| `aptl_techvault/database_access.py` | `_scram_verifier` |
| `aptl_techvault/evidence/techvault_transcript.py` | `_transcript_chain`, `_transcript_result` |
| `aptl_techvault/log_sources.py` | `_ensure_samba_dropin` |

### UUID 5 owners

| File | Functions |
| --- | --- |
| `aptl/backends/_raes_participant_execution.py` | `_control_intent_fields` |
