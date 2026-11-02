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
| Seat policy digest | `appliance/seat/lifecycle.py:_canonical_policy_digest` | `sha256:` and the hex SHA-256 of RFC 8785 of the `aptl.appliance-boundary/v1` policy. | `boundary_policy_digest` of the launch descriptor, which binds the boundary gate, and the policy file that `stage_seat` writes. | `conformance/testdata/vectors/seat-policy-digest.json` |
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

## Owner schemes

The owners below apply a rule of their own on top of the base schemes: a
name, an identifier, a digest input, or the byte form of a document that
another program reads or that a digest or a signature covers. Their
vectors call the owner.

| Scheme | Owner | Rule | Stored or compared by | Vectors |
| --- | --- | --- | --- | --- |
| Participant episode state dir | `backends/raes_participant_fixture_core.py:participant_episode_state_dir` | `/run/aptl/bounded-participant/` and the first 24 hex digits of the SHA-256 of the address, a NUL byte, and the episode ID. | The state root of one bounded participant episode in its container. | `conformance/testdata/vectors/participant-episode-state-dir.json` |
| Participant binding post state digest | `backends/raes_participant_support.py:binding_post_state_digest` | `sha256:` and the hex SHA-256 of the participant, action contract, observation boundary, and action instance addresses joined with a vertical bar (U+007C). | `post_state_digest` of the behavior events of an admission without one. | `conformance/testdata/vectors/participant-binding-post-state-digest.json` |
| Cert generator project name | `core/certs.py:_cert_generator_project_name` | `aptl-certs-` and the first 12 hex digits of the SHA-256 of the resolved project directory. | The Compose project name of the temporary certificate generator. | `conformance/testdata/vectors/cert-generator-project-name.json` |
| Correlation stable ref | `core/correlation/identity.py:stable_ref` | The hex SHA-256 of the domain and each part, each part after a 0x1F byte. An empty domain or no part is rejected. | The correlation references of a run. | `conformance/testdata/vectors/correlation-stable-ref.json` |
| Compose environment file names | `core/deployment/_compose_environment.py:sourced_environment_file` and `_compose_artifact_paths.py:artifact_environment_file_path` | The first 20 hex digits of the SHA-256 of the service name, and of the artifact address, as file and directory names. | The environment files that the Compose services read. | `conformance/testdata/vectors/compose-environment-file-names.json` |
| Compose receipt path | `core/deployment/_compose_resource_ownership.py:WorkspaceOwnership._receipt_path` | `.aptl/lifecycle/resource-receipts-v1/<kind>/` and the hex SHA-256 of the native ID with `.json`. | The resource receipts that stop, reset, and evidence read. | `conformance/testdata/vectors/compose-receipt-path.json` |
| Attempt directory names | `core/deployment/lilrae_docker_recording.py:RecordingStore` and `lilrae_native_evidence.py:_directory` | The hex SHA-256 of the attempt ID, below `.aptl/lifecycle/lilrae-docker-recording-v1/` and below `.aptl/lifecycle/lilrae-native-evidence-v1/`. | The recording and the native evidence of one start attempt. | `conformance/testdata/vectors/attempt-directory-names.json` |
| Sealed output schema name | `workbench/codex_agent.py:CodexManagedAgentAdapter._sealed_output_schema` | `participant-selection-`, the hex SHA-256 of the schema text with a final LF, and `.schema.json`. | The response schema file of one decision agent run. | `conformance/testdata/vectors/sealed-output-schema-name.json` |
| Ssh key fingerprint | `workbench/dispatch.py:key_fingerprint` | The OpenSSH SHA256 fingerprint: `SHA256:` and the unpadded base64 SHA-256 of the key blob. An invalid key is rejected. | The host key fingerprint of a seat access record and of the dispatch transport. | `conformance/testdata/vectors/ssh-key-fingerprint.json` |
| Postgres scram verifier | `aptl_techvault/database_access.py:_scram_verifier` | A PostgreSQL SCRAM-SHA-256 verifier (RFC 5802 and RFC 7677) with 100000 PBKDF2 iterations and base64 salt and keys. | The verifiers that the TechVault database stores. | `conformance/testdata/vectors/postgres-scram-verifier.json` |
| Techvault transcript chain | `aptl_techvault/evidence/techvault_transcript.py:_transcript_chain` | A SHA-256 chain from 32 zero bytes over each frame: sequence, timestamp, and direction, each followed by NUL, then the frame bytes. `sha256:` and hex. | The custody chain of a TechVault terminal transcript. | `conformance/testdata/vectors/techvault-transcript-chain.json` |
| Trial id and seed | `core/experiment/trial_plan.py:_derive_planned_trial_id` and `_derive_seed` | The hex SHA-256 of a versioned domain and the source set digest, condition, replication ordinal, and control ID, each after a 0x1F byte. The trial ID has the `trial-` prefix. | `planned_trial_id` and the seeds of each trial of the plan. | `conformance/testdata/vectors/trial-id-and-seed.json` |
| Participant control intent | `backends/_raes_participant_execution.py:_control_intent_fields` | The control intent fields, with the episode ID as the UUID 5 of `aptl:<run_id>:<participant>:episode` in the URL namespace. | The control intents that the participant evidence records. | `conformance/testdata/vectors/participant-control-intent.json` |
| Apparatus node name | `backends/lilrae_apparatus_reporting.py:apparatus_node_name` | `lilrae-cap-` and the first 24 hex digits of the SHA-256 of the apparatus ID. | The node name of a capture apparatus in the reports. | `conformance/testdata/vectors/apparatus-node-name.json` |
| Seat image names | `appliance/seat/image_selection.py:_selection_path` and `image_trust.py:configure_trust` | `refs/<the first 32 hex digits of the SHA-256 of the reference>.json` and `trust/<the hex SHA-256 of the repository>.pub`. | The image selection records and the trusted keys of the seat image cache. | `conformance/testdata/vectors/seat-image-names.json` |
| Participant observation event | `backends/raes_participant_actions.py:_observation_event` | The behavior event of one observation; `post_state_digest` is `sha256:` and the hex SHA-256 of stdout, LF, and stderr. | The behavior history of a participant episode. | `conformance/testdata/vectors/participant-observation-event.json` |
| Participant shared state records | `backends/raes_participant_actions.py:_shared_state_records` | The shared-state records of one action; each digest is `sha256:` and the hex SHA-256 of the reference, the action instance ID, and `True` or `False`, joined with `:`. | The shared-state records of a participant episode. | `conformance/testdata/vectors/participant-shared-state-records.json` |
| Seat observation id | `appliance/seat/observation.py:observation_id_for` | `sha256:` and the hex SHA-256 of RFC 8785 of the policy digest, payload digest, boot ID, listeners, and reachability result. | The host observation ID that the seat record and the boundary gate bind. | `conformance/testdata/vectors/seat-observation-id.json` |
| Live gate alert summary | `validation/_live_gate_probes.py:_matched_alert_summary` | The rule ID, event time, and redacted source of an alert, and the hex SHA-256 of its JSON with sorted keys, the default separators, and `default=str`. | The matched alerts of the live validation gate report. | `conformance/testdata/vectors/live-gate-alert-summary.json` |
| Guest recovery status | `appliance/guest_surfaces.py:_RECOVERY_STATUS` | The constant body `{"status":"available"}`. | The recovery status response of the guest surface. | `conformance/testdata/vectors/guest-recovery-status.json` |
| Seat guest access bundle | `appliance/seat/access.py:encode_guest_access_bundle` | RFC 8785 of the `aptl.guest-access-bundle/v1` model and a final LF. | The access response from the host to the seat guest. | `conformance/testdata/vectors/seat-guest-access-bundle.json` |
| Seat guest access request | `appliance/seat/access.py:publish_guest_access_request` | RFC 8785 of the `aptl.guest-access-request/v1` model. | The access enrollment that the seat guest publishes. | `conformance/testdata/vectors/seat-guest-access-request.json` |
| Seat overlay identity | `appliance/seat/overlay_identity.py:_new_identity` and `_persist_create_once` | The instance ID is `sha256:` and the hex SHA-256 of 32 random bytes, and the credential is the unpadded base64url of 32 more. The file is RFC 8785 of the identity. | The overlay identity of a seat instance. | `conformance/testdata/vectors/seat-overlay-identity.json` |
| Seat record | `appliance/seat/persistence.py:persist_seat_record` | RFC 8785 of the `aptl.seat-record/v1` model. | The seat state file that later seat commands read. | `conformance/testdata/vectors/seat-record.json` |
| Seat guest readiness | `appliance/seat/readiness.py:encode_guest_readiness` | RFC 8785 of the `aptl.guest-readiness/v1` envelope and a final LF. | The readiness response from the seat guest to the host. | `conformance/testdata/vectors/seat-guest-readiness.json` |
| Seat readiness challenge | `appliance/seat/readiness.py:publish_readiness_challenge` | RFC 8785 of the `aptl.guest-readiness-challenge/v1` model with a random nonce. | The readiness challenge from the host to the seat guest. | `conformance/testdata/vectors/seat-readiness-challenge.json` |
| Techvault boundary policy | `appliance/policy.py:write_full_techvault_boundary_policy` | RFC 8785 of the constant TechVault boundary policy. The vector holds its SHA-256 and size. | The boundary policy file of the TechVault appliance, whose digest the gate compares. | `conformance/testdata/vectors/techvault-boundary-policy.json` |
| Runtime evidence json | `backends/lilrae_runtime_evidence.py:_json_bytes` | Sorted compact JSON with raw UTF-8 (`ensure_ascii=False`). NaN and infinities are rejected. | The runtime evidence artifacts, which their SHA-256 identifies. | `conformance/testdata/vectors/runtime-evidence-json.json` |
| Docker recording json | `core/deployment/lilrae_docker_recording.py:_encode` and `recording_digest` | Sorted compact JSON with ASCII escapes and a final LF, and `sha256:` and its hex SHA-256. | The Docker operation recording of a start attempt and its digests. | `conformance/testdata/vectors/docker-recording-json.json` |
| Cleanup action record | `core/startup_reset_state.py:persist_cleanup_action` | Sorted compact JSON of the `aptl-lifecycle-cleanup-action/v1` or `/v2` record with a final LF, in a file named by its hex SHA-256. An unsupported action is rejected. | The pending cleanup records that the next `lab stop -v` finishes. | `conformance/testdata/vectors/cleanup-action-record.json` |
| Archival discovery line | `core/archival/discovery_index.py:DiscoveryIndex._render_line` | Sorted compact JSON of the event and the index entry, and a final LF. | The discovery index, which removes byte-identical lines on replay. | `conformance/testdata/vectors/archival-discovery-line.json` |
| Egress proxy policy | `core/appliance_boundary.py:render_egress_proxy_policy` | Sorted compact JSON of the sorted authority and port pairs and the proxy limits. A policy without an authority is rejected. | The configuration of the egress proxy broker. | `conformance/testdata/vectors/egress-proxy-policy.json` |
| Participant qualification attestation | `validation/participant_qualification_evidence.py:participant_qualification_attestation_payload` | Sorted compact JSON of the qualification report without its attestation. | The bytes that the qualification attestation signs and that the verifier checks. | `conformance/testdata/vectors/participant-qualification-attestation.json` |
| Family target encoding | `backends/scenario_family.py:encode_family_target` | Sorted compact JSON of the family API version and the qualified family target. An invalid target is rejected. | `family_target` of a `/v2` cleanup action record. | `conformance/testdata/vectors/family-target-encoding.json` |
| Operator group record | `core/operator_group_state.py:persist_admitted_operator_groups` | Sorted compact JSON of the sorted, unique groups and a final LF, in a file named by its hex SHA-256. An invalid group is rejected. | The admitted operator groups that recovery reads. | `conformance/testdata/vectors/operator-group-record.json` |
| Techvault bounded json | `aptl_techvault/evidence/techvault.py:_bounded_json` and `techvault_readiness_probes.py:bounded_json` | Sorted compact JSON with ASCII escapes, or no bytes above the byte bound. NaN is written as `NaN`, which strict JSON rejects. A Go encoder that rejects NaN changes the scheme, which #1511 treats as a functional change. | The native responses and readiness documents in the TechVault evidence. | `conformance/testdata/vectors/techvault-bounded-json.json` |
| Compose ownership override | `core/deployment/_compose_ownership_override.py:write_compose_ownership_override` | PyYAML `safe_dump` with sorted keys of the label and name overrides, in `.aptl/lifecycle/compose-ownership/` with the first 16 hex digits of the SHA-256 of the attempt ID and the YAML as its name. PyYAML writes an anchor and aliases for the shared label mapping. An invalid project name is rejected. | The Compose override of a start attempt, which `docker compose` reads. | `conformance/testdata/vectors/compose-ownership-override.json` |
| Bundle JSONL projection | `core/evidence_bundle/projections/jsonl.py:JsonlProjection.project` | RFC 8785 of each evidence record in evidence record ID order, one row each, each row ending in LF; a null member stays. The member digest is `sha256:` and the hex SHA-256 of the body. No record gives no member. | `projections/jsonl/evidence-records.jsonl` in an evidence bundle and its member digest. | `conformance/testdata/vectors/bundle-jsonl-projection.json` |
| Lifecycle attestation | `core/execution/assembly.py:write_lifecycle_evidence` | RFC 8785 of the `aptl.lifecycle-attestation/v1` payload in `lifecycle/<hex SHA-256>`, and the evidence record JSON of the run store. | The lifecycle evidence of each attempt, which the run record requires. | `conformance/testdata/vectors/lifecycle-attestation.json` |
| Apparatus provenance leaves | `core/provenance/providers/apparatus.py:ApparatusManifestProvider.collect` | Each manifest leaf is `sha256:` and the hex SHA-256 of RFC 8785 of the manifest; the payload holds the identity projection of each manifest. | The apparatus leaves of the provenance record. | `conformance/testdata/vectors/apparatus-provenance-leaves.json` |
| Runtime facts provenance | `core/provenance/providers/runtime_facts.py:RuntimeFactsProvider.collect` | The image, tool version, range snapshot, and host facts leaves, with the provenance identity of each projection, and the RFC 8785 digest of the snapshot as an observation. | The runtime leaves of the provenance record. | `conformance/testdata/vectors/runtime-facts-provenance.json` |
| Apparatus configuration digest | `core/experiment/bindings.py:_apparatus_configuration` | `sha256:` and the hex SHA-256 of RFC 8785 of `aptl-experiment-apparatus-configuration/v1` and the apparatus binding values. An unknown target or two values for one target are rejected. | The apparatus configuration digest of an experiment condition. | `conformance/testdata/vectors/apparatus-configuration-digest.json` |
| Capture plan | `core/experiment/capture_plan.py:admit_capture_demands` | RFC 8785 of the `aptl-capture-plan/v1` projection, its `sha256:` digest, and the `capture-plan-` ID. The vectors hold the empty plan. A plan with bindings needs a pack collector that RAES admits for a demand. | The capture plan of a run, its digest, and its ID. | `conformance/testdata/vectors/capture-plan.json` |
| Techvault misp readiness | `aptl_techvault/evidence/techvault_misp_readiness.py:_readiness_document` | Sorted compact JSON of `misp_authenticated_api_ready` and the required MISP facts, or no document when a fact is false, missing, or differs from the admitted state. | The MISP readiness evidence of TechVault. | `conformance/testdata/vectors/techvault-misp-readiness.json` |
| Techvault wazuh agent readiness | `aptl_techvault/evidence/techvault_wazuh_agent_readiness.py:_readiness_document` | Sorted compact JSON of `wazuh_agent_ready` and the required fields of each host in node reference order, or no document when a host is missing or not ready. | The Wazuh agent readiness evidence of TechVault. | `conformance/testdata/vectors/techvault-wazuh-agent-readiness.json` |
| Techvault sqli correlation | `aptl_techvault/evidence/techvault.py:SuricataWazuhSqliSource.fetch` and `_sqli_result` | Sorted compact JSON of the `aptl-techvault-sqli-correlation/v1` document with one Suricata and one Wazuh row of a shared flow, and its source pipeline. An uncorrelated pair is a mid-run loss. | The SQL injection correlation evidence of TechVault. | `conformance/testdata/vectors/techvault-sqli-correlation.json` |
| Techvault suricata readiness | `aptl_techvault/evidence/techvault_readiness.py:SuricataRuleReadinessSource.fetch` | Sorted compact JSON of the `aptl-techvault-suricata-readiness/v1` record and its source pipeline. | The Suricata rule readiness evidence of TechVault. | `conformance/testdata/vectors/techvault-suricata-readiness.json` |
| Techvault transcript document | `aptl_techvault/evidence/techvault_transcript.py:_transcript_result` | Sorted compact JSON of the `aptl-techvault-transcript/v2` document with the sessions in start order, the redacted frames, and each `terminal-` reference as the hex SHA-256 of `aptl.techvault.terminal-ref/v1`, NUL, the session ID, NUL, and the chain digest. | The terminal transcript evidence of TechVault. | `conformance/testdata/vectors/techvault-transcript-document.json` |
| Participant crossing policies | `backends/_raes_participant_crossing.py:_delivery_crossing_policies` | One policy reference for each participant; `policy_digest` is `sha256:` and the hex SHA-256 of the sorted compact JSON of the seven policy coordinates, and the interval runs from the first control order to one past the last. A policy that changes within one participant sequence is rejected. | The crossing policy references of the participant delivery evidence. | `conformance/testdata/vectors/participant-crossing-policies.json` |
| Participant delivery evidence | `backends/_raes_participant_evidence.py:_ParticipantDeliveryCollector.stop` | `json.dumps` of the delivery payload with sorted keys and the default separators, so the bytes hold spaces and ASCII escapes. | The delivery evidence of each participant instruction. | `conformance/testdata/vectors/participant-delivery-evidence.json` |
| Native cleanup observation | `core/deployment/lilrae_native_evidence.py:record_cleanup` | The receipt bytes retained under their hex SHA-256, and sorted compact JSON of the `lilrae.native-cleanup/v1` observation with a final LF under a random name. An unknown cause is rejected. | The native evidence of a removed resource. | `conformance/testdata/vectors/native-cleanup-observation.json` |
| Compiled runtime model | `backends/raes_runtime_model_artifact.py:compiled_runtime_model_bytes` and `compiled_runtime_model_sha256` | RFC 8785 of `aptl.raes-runtime-model-artifact/v1` and the canonical runtime model, and a final LF: enumerations as values, data classes and models as objects, tuples as arrays, and sets sorted by the RFC 8785 bytes of each item. The vector holds the digest and size for a compiled scenario. | `compiled_model_sha256` of the bounded participant driver. | `conformance/testdata/vectors/compiled-runtime-model.json` |
| Participant candidate selections | `backends/raes_participant_candidates.py:candidate_selections` | One selection for each variant of the finite argument domain; the proposal reference ends in `arguments-` and the first 16 hex digits of the SHA-256 of RFC 8785 of the arguments. | The candidate selections and proposal references of a participant decision. | `conformance/testdata/vectors/participant-candidate-selections.json` |
| Parquet canonical JSON | `core/evidence_bundle/projections/parquet.py:_canonical_json` | RFC 8785 decoded as text. The current code decodes as ASCII and rejects a non-ASCII reference (#1598); `dev` fixes it in #1599. | The `source_refs` and `provenance_refs` columns of the Parquet projection. | `conformance/testdata/vectors/parquet-canonical-json.json` |

## Other call sites

The call sites below use a base scheme with no rule of their own, or write a
value that no other run, program, or implementation reads as bytes.

### Content digests

Each owner hashes bytes or UTF-8 text with SHA-256 and adds no projection of
its own, so the raw bytes vectors (`conformance/testdata/vectors/sha256-bytes.json`)
define it. The input and the spelling are the owner rule.

| File | Functions | Input and form |
| --- | --- | --- |
| `aptl/appliance/access_service_support.py` | `_descriptor_digest` | The descriptor file bytes, as `sha256:<hex>`. |
| `aptl/appliance/download.py` | `_file_identity` | The file bytes, as `sha256:<hex>`, and the size. |
| `aptl/appliance/guest_observation.py` | `_read_guest_boot_id` | The UTF-8 text of `kern.boottime` when the kernel has no boot ID, as `sha256:<hex>`. |
| `aptl/appliance/seat/image_disk_cache.py` | `_sha256_of` | The bytes, as `sha256:<hex>`. |
| `aptl/appliance/seat/image_trust.py` | `verify_cached_image`, `verify_remote_image` | The public key file bytes, as hex. |
| `aptl/appliance/seat/launch_descriptor.py` | `verify_seat_launch` | The policy file bytes, as `sha256:<hex>`, compared with the launch descriptor. |
| `aptl/appliance/seat/lifecycle.py` | `_launch_descriptor_digest` | The launch descriptor file bytes, as `sha256:<hex>`. |
| `aptl/backends/_raes_participant_evidence.py` | `_delivery_record` | The UTF-8 instruction, response, and session ID, each as `sha256:<hex>`. |
| `aptl/backends/_raes_participant_transport.py` | `_private_file_sha256` | The private file bytes, as hex. |
| `aptl/backends/_raes_stateful_observation.py` | `_artifact_evidence` | The rendered configuration file bytes, as hex. |
| `aptl/backends/lilrae_materialization_archive.py` | `read` | The blob bytes, as hex, compared with the record checksum. |
| `aptl/backends/lilrae_participant_configuration.py` | `configured_opencode_executor` | The UTF-8 prompt, as hex, compared with the recorded digest. |
| `aptl/backends/lilrae_runtime_evidence.py` | `_artifact_bytes`, `_blob`, `_collect_native` | The artifact bytes, as hex. |
| `aptl/backends/raes_artifact_availability.py` | `_materialized_specifications` | The Dockerfile bytes, as `sha256:<hex>`, compared with the realized digest. |
| `aptl/backends/raes_content_satisfaction.py` | `_resolved_content_digest` | The bytes that the pack resolves, as `sha256:<hex>`. |
| `aptl/backends/raes_docker_materializer.py` | `place_file` | The UTF-8 file content, as hex, compared with `sha256sum` in the container. |
| `aptl/backends/raes_image_realization.py` | `_materialized_component_image` | The Dockerfile bytes, as `sha256:<hex>`, compared with the realized digest. |
| `aptl/backends/raes_participant_driver.py` | `__post_init__` | The scenario file bytes, as hex. The compiled model digest has the compiled runtime model vectors. |
| `aptl/backends/raes_participant_evidence_publication.py` | `persist_action_evidence` | The UTF-8 action instance ID, as hex, which names the evidence transaction. |
| `aptl/backends/raes_participant_projection.py` | `_render_visible_context` | The UTF-8 text, as hex. |
| `aptl/backends/raes_repro.py` | `_raes_lock_digest` | The lock file bytes, as hex. |
| `aptl/core/appliance_boundary.py` | `load_boundary_policy` | The policy file bytes, as `sha256:<hex>`, compared with the expected digest. |
| `aptl/core/archival/seal.py` | `build_inventory_entry` | The member bytes, as hex. |
| `aptl/core/archival/verify.py` | `_verify_inventory`, `verify_sealed_archive` | The member and manifest bytes, as hex and as `sha256:<hex>`. |
| `aptl/core/deployment/_forwarding_agent_realization.py` | `_file_digest_matches` | The UTF-8 payload, as hex, compared with `sha256sum` in the container. |
| `aptl/core/deployment/_wazuh_agent_realization.py` | `_file_digest_matches` | The UTF-8 payload, as hex, compared with `sha256sum` in the container. |
| `aptl/core/deployment/lilrae_native_evidence.py` | `_receipt_artifacts` | The receipt bytes, as hex, which name the retained receipts. |
| `aptl/core/evidence/content_store.py` | `create_content_addressed` | The blob bytes, as `sha256:<hex>`, and the hex as the file name. |
| `aptl/core/evidence_bundle/_io.py` | `_stream` | The bytes, as `sha256:<hex>`, and the size. |
| `aptl/core/evidence_bundle/archive.py` | `_member_bytes` | The member bytes, as `sha256:<hex>`. |
| `aptl/core/evidence_bundle/inventory.py` | `envelope_member` | The member bytes, as `sha256:<hex>`. |
| `aptl/core/evidence_bundle/schemas.py` | `resolve_schema` | The schema bytes, as `sha256:<hex>`. |
| `aptl/core/evidence_bundle/verify.py` | `_sha256_hex` | The bytes, as `sha256:<hex>`. |
| `aptl/core/execution_boundary.py` | `_digest` | The UTF-8 value, as hex, or an empty string for an empty value. |
| `aptl/core/exporter.py` | `_sha256_file` | The file bytes, as hex. |
| `aptl/core/lab.py` | `_persist_cleanup_actions` | The UTF-8 run ID or reset admission ID, as hex, which is the admission ID. |
| `aptl/core/provenance/identity.py` | `digest_bytes` | The bytes, as `sha256:<hex>`. |
| `aptl/core/snapshot.py` | `_hash_config_files` | The configuration file bytes, as hex. |
| `aptl/utils/deterministic_archive.py` | `hash_file_nofollow` | The file bytes, as `sha256:<hex>`, and the size. |
| `aptl/validation/_gate_no_start_backend.py` | `_simulated_digest` | The UTF-8 reference, as `sha256:<hex>`, in the offline gate. |
| `aptl/validation/_live_gate_models.py` | `make_live_gate_report` | The UTF-8 scenario text, as `sha256:<hex>`. |
| `aptl/validation/participant_profile.py` | `_read_reference`, `_resolve_pack_profile`, `load_participant_profile` | The profile and manifest bytes, as hex. |
| `aptl/validation/participant_qualification_evidence.py` | `_load_evidence_json`, `verify_participant_qualification_attestation` | The evidence bytes, as hex, and the DER key bytes, as the `sha256:<hex>` key ID. |
| `aptl/validation/techvault_live_gate.py` | `_verification_identities` | The verified bytes, as `sha256:<hex>`. |
| `aptl/workbench/agent.py` | `_assert_config_unchanged`, `_load_server_config` | The configuration bytes, as hex. |
| `aptl/workbench/client_files.py` | `_digest` | The UTF-8 text, or an empty string, as hex. |
| `aptl/workbench/lilrae_opencode.py` | `__init__`, `_verify_profile_config` | The prompt and configuration bytes, as hex. |
| `aptl/workbench/runtime.py` | `_sha256_text` | The UTF-8 text, as hex. |
| `aptl_techvault/log_sources.py` | `_ensure_samba_dropin` | The UTF-8 payload, as hex, compared with `sha256sum` in the container. |

### Values without vectors

No other run, program, or implementation reads these values as bytes.

| File | Functions | Reason |
| --- | --- | --- |
| `aptl/appliance/seat/image_disk_cache.py` | `write_verification_stamp` | A local cache record with the inode, mtime, and mode of the disk; the same host parses it. |
| `aptl/appliance/seat/image_selection.py` | `save_selection` | A local cache record that the same host parses. Its file name has the seat image names vectors. |
| `aptl/appliance/seat/image_trust.py` | `publish_verified_image` | A local trust receipt that the same host parses and compares by field. |
| `aptl/appliance/seat/image.py` | `cache_seat_image_config` | A local binding file that the same host parses and compares by field. |
| `aptl/appliance/seat/vm.py` | `write_vm_pid` | A runtime process file that the same host parses. |
| `aptl/backends/_raes_participant_transport.py` | `_render_runtime_profile_config` | An MCP configuration file that each run writes again for its own runtime. |
| `aptl/workbench/profiles.py` | `render_profile_config` | An agent configuration file that each run writes again for its own runtime. |
| `aptl/backends/raes_participant_provider.py` | `_compact_selection_prompt`, `select` | The prompt text of one decision; no record holds it. |
| `aptl/workbench/decision_schema.py` | `admit_decision_response_schema` | The response schema of one decision run. Its file name has the sealed output schema name vectors. |
| `aptl/cli/seat.py` | `_emit` | A seat command result on standard output, as sorted compact JSON (base vectors). The conformance inventory owns the command results. |
| `aptl/core/lifecycle_policy.py` | `save_state` | Local state with an indent of 2 that the next command parses. |
| `aptl_techvault/evidence/techvault_enrollment_baseline.py` | `record_enrollment_baseline` | A local baseline file that the next readiness check parses and compares by value. |
| `aptl/backends/raes_evidence_acquisition.py` | `_mark_transcript_finalized`, `mark_transcript_activation_failed`, `mark_transcript_finalization_failed`, `persist_active_transcript_authority` | Local restart state of a transcript capture that the next stop parses. |
| `aptl/workbench/app.py` | `<module>` | The CSP hash of the script that the server sends, computed when the server starts. |
| `aptl/workbench/browser_mcp.py` | `terminal_page` | The CSP hash of the script of the page, computed for each page. |
| `aptl_techvault/build_cache.py` | `<module>`, `_dependency_only_manifest` | An npm manifest that each image build derives again for its cache. |
