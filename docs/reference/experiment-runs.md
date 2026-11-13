# Experiment Runs

The experiment run system captures data from each scenario execution for reproducibility and post-run analysis.

RAES owns experiment admission, dispatch, replacement and resume.
The serving interface accepts an already admitted `TrialUnitRequest` through `aptl.backends.trial_serving.LilraeTrialUnit`.
This adapter receives the request's RAES runtime unit, `DeclaredCleanup`, selected Docker backend, and a shared local placement-state root. Every worker that uses the same daemon must use the same state root.
The adapter keeps the admitted entry, run and attempt identities. It does
not create an experiment plan or schedule a batch.

Trial delivery must have a `TrialReadiness` gate bound to that same runtime
target. `ReadinessEnvironment` identifies the selected approved lab owners.
`ReadinessTrialServices` wraps the runtime's installed trial services. Readiness uses the admitted RAES entry directly.
It examines required local artifacts, participant implementation and complete
settings, clean placement, containment, required capture, and writable storage.

Required services and capture sources are checked after provisioning and
before effects. Missing, unavailable, crashing, malformed, and timed-out checks
block the affected trial. Source readiness uses a separate read-only operation.
It never invokes acquisition or its stimuli. A fully ceased preparation refusal
releases newly claimed placement fences before dispatch.

Clock accuracy is required only by a selected capture
contract that declares it. No cloud resource is required for the fixed existing
VM baseline. See [trial readiness](../architecture/trial-serving.md#required-readiness).

The adapter holds the project lifecycle lock and a daemon lock during delivery.
It rejects preexisting containers, networks or volumes. Pending execution,
interruption or failed cleanup leaves durable ownership fences that block
unrelated lab mutation and subsequent trials, also after restart.

Recovery must have the same attempt and its original RAES ledger.
Fence deletion does not recover the attempt. A different runtime does not recover it either. A `fresh-range-required` outcome must have a new approved placement rather than reuse of the old one. Cancellation and
deadlines use RAES's stop and observation path, and keep partial evidence before declared cleanup. See [trial serving](../architecture/trial-serving.md).

`aptl.backends.trial_recovery.recover_interrupted_trial` accepts the original `LilraeTrialUnit` and `AssignedTrial`.
It must also have coordinator cancellation control, worker runtime, clock, and execution identity.
Recovery must have RAES 10.7.0 or later and the original durable RAES stores.
See [recover an assigned trial](run-operations.md#recover-an-assigned-trial) for the procedure. Recovery validates the
retained intent before native work and uses the original run and attempt IDs.
It does not allocate a replacement or resume another entry.

Recovery seals the producer record and retained bytes under
`<run store>/archives/<snapshot digest>/<run_id>/`. Each snapshot has its own
manifest, seal and discovery index.
The working run stays writable and can keep later cleanup facts. These writes do not change an old archive.

Execution,
capture and cleanup keep their separate RAES states. Unknown cessation has
no invented end time. Verified sealing alone does not permit target reuse.
Cleanup, native absence and probe cessation must also be proven.

Duplicate
completed requests verify the retained archive and leave later owners alone.
See [interrupted trial recovery](../architecture/interrupted-trial-recovery.md).

For a portable, third-party-verifiable evidence archive built from a run's verified artifact closure, see [Portable Evidence Bundle Export](evidence-bundle-export.md) (`lilrae runs export-bundle`).

## Clean State Between Runs

Containers can keep databases, indices, logs, generated credentials, and files from earlier exercises.
`lilrae lab start --clean` removes the project deployment and its managed volumes before ordinary startup.
Cleanup failure prevents startup.
The operation keeps `.env`, keys, generated client configuration, tracked source configuration, and archived run directories.
It does not prune unrelated Docker state.

Live validation uses the same initial cleanup unless `--skip-clean-boot` is selected.
See [prepare run evidence](run-operations.md#clean-state-between-runs) for the destructive procedure.

## Run Directory Structure

Runs live in the run store, which `run_storage.local_path` in `aptl.json` sets
(default `./runs`, relative to the project directory). Each run is one
directory, `<run store>/<run_id>/`. `lilrae lab start` creates one run per start
and names it `run_<UTC timestamp>`, for example `run_20261011T135200Z`. The
`lilrae runs` commands list only run directories that contain a `manifest.json`,
which `lilrae lab start` writes as its last step.

A run holds only what its writers produced. The tree shows the layout that the
shipped code writes. Most paths appear only when the scenario, command, or
capture that writes them ran.

```
<run_id>/
  manifest.json                   # Run record: lab start, or a sealed terminal attempt
  seal.json                       # Atomic seal marker (terminal attempt)
  attempt-intent.json             # Attempt intent (terminal attempt)
  correlation.json                # Correlation-identity and clock projection
  continuity-events.jsonl         # Continuity audit events
  provenance/
    startup-provenance.json       # Provisional apparatus provenance
    run-provenance.json           # Canonical ready-to-seal provenance
  orchestration/<workflow>/
    result.json                   # Workflow result
    history.jsonl                 # Workflow history events
  evidence/
    capture-plans/<plan_id>.json  # Admitted capture plan
    blobs/<sha256>                # Content-addressed raw evidence
    records/<record_id>.json      # Evidence records
  lifecycle/<sha256>              # Lifecycle attestation (terminal attempt)
  readiness/clean/<sha256>.json   # Ordinary clean-placement observation
  readiness/prepared/<sha256>.json # Entry and installed-resource observations
  readiness/live/<sha256>.json    # Required live service and capture observations
  trial-serving/intent.json      # Immutable admitted request and owner commitments
  trial-serving/handoff.json     # Cleanup and readiness references
  participant/
    inject-deliveries.jsonl       # Participant inject deliveries
    observations.jsonl            # Participant action observations
  evaluator/
    participant-action-transactions/<transaction>.json
    participant-action-evidence.jsonl
    participant-control-evidence.jsonl
  participant-profile/
    qualification.json            # Participant profile qualification
  live-gate/
    manifest.json                 # Live validation gate manifest
  mcp-side/
    tool-calls.jsonl              # Red MCP tool calls
    ocsf.jsonl                    # OCSF-aligned red MCP records
    sessions/<session_id>.jsonl   # SSH session output
  kali-side/<session_id>/         # Capture harvest for one MCP session
```

| Path | Writer | Written when |
|------|--------|--------------|
| `manifest.json` (lab start) | `_write_run_record` in `src/aptl/core/lab.py`, built by `src/aptl/backends/raes_repro.py` | The last step of a successful `lilrae lab start`: the REP-001 reproducibility record (`aptl.run-record/v2`), which embeds the [range snapshot](#range-snapshot) |
| `manifest.json`, `seal.json` (terminal attempt) | `src/aptl/core/archival/coordinator.py` | A terminal attempt is sealed: the RAES `experiment-run/v1` record and its seal marker, both create-once |
| `attempt-intent.json` | `src/aptl/core/execution/executor.py` | A terminal attempt starts |
| `lifecycle/` | `src/aptl/core/execution/assembly.py` | A terminal attempt ends: its lifecycle attestation, with an evidence record in `evidence/records/` |
| `readiness/`, `trial-serving/handoff.json` | `TrialReadiness` and `LilraeTrialUnit` | The trial examines clean placement and required resources. Handoff follows verified cleanup and probe cessation. Results are create-once and include failures when storage works |
| `provenance/startup-provenance.json` | `src/aptl/core/provenance/record.py`, called by `lilrae lab start` | After the lab-start run record |
| `provenance/run-provenance.json` | `publish_provenance_record` in `src/aptl/core/provenance/record.py` | A caller that holds the admitted and executed run context publishes it. No `aptl` command does |
| `correlation.json` | `src/aptl/core/correlation/persistence.py` | After the lab-start run record, built from `manifest.json` and `orchestration/` |
| `orchestration/<workflow>/` | `src/aptl/backends/raes_orchestrator.py` | `lilrae lab start` runs a scenario workflow |
| `evidence/capture-plans/` | `src/aptl/backends/_raes_native_evidence_acquisition.py` | `lilrae lab start` acquires native captures or activates a full-run transcript capture |
| `evidence/blobs/`, `evidence/records/` | `src/aptl/core/evidence/` | `lilrae lab start` acquires the scenario's native captures, `lilrae lab stop` finalizes a full-run transcript capture, or a terminal attempt acquires its declared captures |
| `participant/`, `evaluator/` | `src/aptl/backends/_raes_participant_execution.py`, `src/aptl/backends/raes_participant_evidence_publication.py`, `src/aptl/backends/raes_participant_control_evidence.py` | `lilrae lab start` delivers participant injects or realizes participant actions |
| `continuity-events.jsonl` | `src/aptl/core/continuity.py` | `lilrae lab continuity-audit --run-id <run-id>` records at least one event |
| `participant-profile/qualification.json` | `src/aptl/validation/participant_qualification.py` | `lilrae lab qualify-profile --run-id <run-id>` accepts a report |
| `live-gate/manifest.json` | `src/aptl/validation/_live_gate_checks.py` | `lilrae lab validate-live` records its check outcomes |
| `mcp-side/tool-calls.jsonl`, `mcp-side/ocsf.jsonl` | `mcp/mcp-red/src/capture.ts`, `mcp/mcp-red/src/logger.ts` | Each red MCP tool call, plus an OCSF record for each command it runs |
| `mcp-side/sessions/` | `createPtyTeeWriter` in `mcp/aptl-mcp-common/src/runs.ts` | Each SSH session or one-shot command an MCP server runs, appended as output arrives |
| `kali-side/<session_id>/` | `harvestSession` in `mcp/aptl-mcp-common/src/captures.ts` | A configured capture server finishes a command or closes a session locally, remotely, or during shutdown. Explicit close tools are `<prefix>_close_session` and `<prefix>_close_all_sessions`. For the red server, `lilrae lab start` names this workspace's capture sidecar in `LILRAE_MCP_CAPTURE_CONTAINER`. The sidecar's capture broker writes `frames.jsonl` and `metadata.json` under `/var/log/aptl/captures/<run_id>/sessions/<session_id>/`. The harvest copies that directory after the broker confirms `metadata.json`. When the harvest fails, the directory holds `capture-harvest-failure.json` instead, which names the failure (see [Kali Red Team](../components/kali-redteam.md#mcp-integration)). A server that names no capture container does not harvest |

The legacy execution composer and the assigned-trial recovery adapter publish
sealed records through the shared archival coordinator. A run that `lilrae lab start` created never holds `seal.json`, so it
stays unsealed.

MCP servers write `mcp-side/` and `kali-side/` into the run that
`APTL_MCP_ADMITTED_RUN_ID` names in their environment. Lab start sets this value in generated MCP configuration. Without an admitted run ID, a server writes under `_unbound`. The capture broker's own record of the Kali sessions reaches the run
under `evidence/` when `lilrae lab stop` finalizes a full-run transcript capture.

The participant workbench (`src/aptl/workbench/runtime.py`) keeps its own run
store under its state directory and appends session events to
`<run_id>/workbench/events.jsonl` there.

## Run Provenance (`provenance/`)

Provenance records the apparatus used for the run. It identifies the scenario, backend, participant implementation, images, detector rules, collectors, and configuration.

There are two records, written at different lifecycle boundaries:

- `startup-provenance.json` is **provisional**. Lab start knows effective configuration, detection content, dependency locks, and realized images. It lacks the admitted trial plan, realized participants, and execution outcome.
- `run-provenance.json` is the canonical **ready-to-seal** record. The collector with admitted and executed run context writes it. Publication without that context is refused. Missing context is not replaced with invented experiment or participant sources.

Both records use **create-once** publication. An identical second publication makes no change.
A different second publication for the same run fails. It does not overwrite the record.

The provisional startup artifact has a different path. It therefore cannot block the later canonical write.
Neither record is a seal. They carry no signature or attestation claim.

| Field | Description |
|-------|-------------|
| `schema_version` | Version of the record shape |
| `run_id` | The run this provenance describes |
| `seal_state` | `ready-to-seal` for the canonical record, `provisional` for the startup record |
| `aggregate_identity` | Canonical identity over every section |
| `registry_declaration_digest` | Pins which provider declarations collected this run |
| `sections[]` | One entry per provenance source: status, declaration digest, content identity, and a bounded payload |
| `limitations[]` | Every source that did not fully collect, with a stable reason code |

Each source is collected by a code-owned provider under declared byte, entry,
and time limits. A source that is unavailable, denied, unsupported, truncated,
timed out, or failed appears in `limitations[]` with a stable reason code. Such
a source is never silently omitted and never given a fabricated digest. A plain
`lilrae lab start` has no admitted experiment plan and no installed participants,
so its provisional record reports those two sources `unavailable`. It does not omit them.

Each detector rule, decoder, allowlist, image, and configuration has a content identity bound to its logical role. Family identities combine the sorted leaves. If one rule changes, its leaf and the aggregate change. Other leaves remain unchanged. Secret sources are
excluded by allowlist before collection: `.env`, rendered secret-bearing
config, credentials, and private keys are never read or hashed.

## Sealed Run Records (`manifest.json`, `seal.json`)

Assigned trials use RAES's record producer. Recovery passes its original
`ExperimentRunModel` to the archival coordinator and does not change statuses, event times or attempt accounting. Both terminal and partial records can be
sealed. A partial record states its limitations and does not establish cessation.
The returned archive path identifies the immutable snapshot. The ordinary CLI
run listing does not scan nested snapshot stores.

The legacy execution composer (`src/aptl/core/execution/`) remains available to
existing archival consumers. It composes a terminal-attempt context from its
workload and evidence acquisition. Its ID allocation and terminal-cause mapping
do not apply to RAES-assigned trial recovery. Legacy terminal attempts include
a lifecycle attestation even when authored capture never started.

- `manifest.json` is the canonical serialized RAES run record for an immutable
  snapshot. In a run that `lilrae lab start` created, `manifest.json` is the
  `aptl.run-record/v2` reproducibility record instead. One version-dispatching
  adapter reads every shape, also for older `aptl.run-record/v1` archives.
- `seal.json` is the atomic seal marker. A run is discoverable as sealed only
  after this marker is durably committed. Before it exists the attempt is an
  unsealed recovery candidate even if `manifest.json` is present. The marker
  binds the canonical run-record digest, a bounded inventory (path, media type,
  size, and checksum for every sealed artifact), the applicable contract
  versions, and an explicit completeness and limitation statement.

The legacy archival composer uses its `attempt_id` as its portable `run_id`.
Assigned trials instead keep RAES's preallocated `run_id` and separate
`execution_attempt_id`. Recovery never substitutes one for the other. RAES owns retry and replacement identity for assigned trials. Retry and repair
lineage travel as RAES run references (`used_refs`, `derived_from_refs`,
`generated_refs`, and, where applicable, `invalidation.superseded_by`).

Sealing keeps the producer's status. Completed execution records `completed` with its evaluator outcome. Scenario or evaluator failure records `failed`.

Cancellation, policy stop, or infrastructure interruption records `aborted`. Capture loss or another validity failure records `invalidated` with a reason.

A replaced version records `superseded`.

Sealing is atomic and immutable. The run store verifies and checksums the record and referenced artifacts through descriptor-relative operations that refuse symlinks. It then durably publishes the marker without replacement. Once sealed, every overwrite-capable writer refuses another write. A correction is
a new run version or attestation with explicit lineage, never an in-place edit.
Export packages the already-sealed bytes and never writes back into the archive.

A small, append-safe discovery index under the run store records bounded routing
facts (run identity, run version, manifest digest, seal state, routing
timestamp, and safe relative location) with a prepared and committed journal.
Discovery replays that journal and verifies each entry against the on-disk seal
marker, so restart discovery does not scan or trust arbitrary filesystem paths. Partial snapshots use their retained archive observation time only for local routing.
This does not add an end time to the run record. The index is derived and
rebuildable from sealed archives. Its
loss never changes the portable record or the seal.

## Range Snapshot

The range snapshot records the realized lab for reproducibility. No separate
snapshot file exists: `lilrae lab start` captures the snapshot in the step before
its run record and embeds it in `manifest.json` at
`backend_evidence.range_snapshot`. `lilrae lab status --json` prints a fresh
snapshot, and `lilrae lab status --output <file>` writes one to a file with mode
`0600`. Capture and serialization live in `src/aptl/core/snapshot.py` and
`src/aptl/core/snapshot_models.py`. The snapshot contains these fields:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 capture time |
| `software.python_version` | Python interpreter version |
| `software.docker_version` | Docker Engine version |
| `software.compose_version` | Docker Compose version |
| `software.wazuh_manager_version` | Wazuh manager version (from `/var/ossec/bin/wazuh-control`) |
| `software.wazuh_indexer_version` | OpenSearch version on the Wazuh indexer |
| `software.aptl_version` | APTL package version |
| `software.raes_version` | Installed `raes` package version |
| `containers[]` | One entry for each container the project owns, in any state |
| `containers[].name` | Container name |
| `containers[].container_id` | Full 64-hex ID of this container instance, read from backend inspection. Empty when that inspection does not prove it is the container the project inventory listed |
| `containers[].image` | Image reference from `docker ps`, usually the tag the container was created from |
| `containers[].image_id` | The daemon's `sha256:` ID of the image this container runs, from the same inspection. Empty when that inspection does not prove it |
| `containers[].image_digest` | Immutable registry digest of the image, which the run record copies into `container_image_digests`. Snapshot capture does not set it, so it is empty ([#1340](https://github.com/OpenRAE/lilrae/issues/1340)) |
| `containers[].status` | Status text from `docker ps`, for example `Up 5 minutes (healthy)` |
| `containers[].health` | `healthy`, `unhealthy` or `starting`, parsed from the status text. Empty for a container without a health check |
| `containers[].labels` | Container labels |
| `containers[].networks` | The container's IPv4 address on each network, keyed by network name |
| `containers[].ports` | Published port mappings, as `docker ps` reports them |
| `containers[].restart_policy` | Docker restart-policy name (`no`, `always`, `unless-stopped`). It tells a run-to-completion helper from a long-running service |
| `wazuh_rules.total_rules` | Total Wazuh rules loaded |
| `wazuh_rules.custom_rules` | Custom rules in `/var/ossec/etc/rules/` |
| `wazuh_rules.custom_rule_files` | List of custom rule XML filenames |
| `wazuh_rules.total_decoders` | Total decoders loaded |
| `wazuh_rules.custom_decoders` | Custom decoders count |
| `networks[]` | Docker network name, subnet, gateway, connected containers |
| `config_hashes` | SHA-256 of `aptl.json` and of each `docker-compose*.yml` or `docker-compose*.yaml` file in the project directory. `.env` is excluded. Its secrets can have guessable values. Those hashes could confirm guesses. |
| `services[]` | Service endpoints (name, URL, host, port, protocol) of running containers |
| `ssh[]` | SSH endpoints (name, host, port, user, key path, command) of running containers |

Container identity, image identity and the image's registry digest are three
separate fields, as
[ADR-059](../adrs/adr-059-canonical-techvault-delivery-and-host-mcp-access.md)
requires. Snapshots recorded before `containers[].container_id` existed hold the
`docker ps` container ID, which can be truncated, in `containers[].image_id`. In
a manifest whose container entries have no `container_id` key, read `image_id`
as that container ID, not as an image identity.

Snapshots and trace exports must not contain live credentials, API keys, bearer
tokens, cookies, JWTs, private key material, or default lab passwords. Before you write JSON or OTel attributes, apply redaction. Archive location, permissions, and export controls do not replace this protection.

## CLI Commands

```bash
# List recent runs
lilrae runs list

# Show run details
lilrae runs show <run-id>

# Print run directory path
lilrae runs path <run-id>

# Export run as tar.gz archive
lilrae runs export <run-id>

# Export to S3 (requires pip install lilrae[s3])
lilrae runs export <run-id> --s3-bucket my-bucket --s3-prefix runs/

# Build a portable evidence bundle (written to ./exports by default)
lilrae runs export-bundle <run-id>

# Verify an evidence bundle
lilrae runs verify-bundle ./exports/<run-id>.evidence-bundle.tar
```

[Portable Evidence Bundle Export](evidence-bundle-export.md) describes the
bundle options, layout, and verification.

## Key Source Files

- `src/aptl/core/runstore.py`: Storage backend protocol and local filesystem implementation, seal-marker commit, and sealed-state immutability
- `src/aptl/backends/trial_recovery.py`: Recovery of one RAES-assigned interrupted attempt
- `src/aptl/backends/trial_archive.py`: Immutable snapshots of producer facts and original artifacts
- `src/aptl/core/archival/`: Terminal-attempt archival with RAES run-record composition, terminal-cause status mapping, atomic seal marker, discovery index, and the legacy-manifest read adapter
- `src/aptl/core/execution/`: Legacy terminal-record composition and the owner-native RAES sub-model bridges (clock, apparatus context, parameters, stochastic controls, evidence artifacts, result summaries)
- `src/aptl/core/lab.py`: The `lilrae lab start` steps that capture the range snapshot and write the run record, provisional provenance, and correlation projection
- `src/aptl/core/snapshot.py`, `src/aptl/core/snapshot_models.py`: Range snapshot capture logic and dataclasses
- `src/aptl/core/exporter.py`: Local tar.gz and S3 export
- `src/aptl/core/evidence_bundle/`: Portable evidence bundle build and verification
- `src/aptl/cli/runs.py`: CLI commands (`lilrae runs list|show|path|export|export-bundle|verify-bundle`)
