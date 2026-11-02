# Experiment Runs

The experiment run system captures data from each scenario execution for reproducibility and post-run analysis.

For a portable, third-party-verifiable evidence archive built from a run's verified artifact closure, see [Portable Evidence Bundle Export](evidence-bundle-export.md) (`lilrae runs export-bundle`).

## Clean State Between Runs

Persistent containers accumulate state across runs: service databases, indexes, logs, generated in-container credentials, and files written during a prior exercise. That state contaminates the next run and undermines reliable batch execution and benchmarking.

The clean-boot lifecycle mode guarantees a fresh environment. It tears down the project-scoped deployment, removes the Compose-managed volumes, and then boots the lab again through the standard start path, so certificates, seeds, and the SOC stack come up fresh:

```bash
# Ephemeral clean boot: destroy lab state, then start fresh.
lilrae lab start --clean

# Skip the confirmation prompt (for scripted batch runs).
lilrae lab start --clean --yes
```

A clean boot removes only Docker Compose state for the configured project. It does not delete `.env`, the `keys/` directory, `.mcp.json`, checked-in configuration, or archived run directories. A failed cleanup is fatal: the lab does not start, because a contaminated environment must never be reused as clean.

The same capability backs `lilrae lab validate-live`, which clean-boots the lab before snapshotting it (pass `--skip-clean-boot` to validate the running lab without destroying it).

## Run Directory Structure

Runs live in the run store, which `run_storage.local_path` in `aptl.json` sets
(default `./runs`, relative to the project directory). Each run is one
directory, `<run store>/<run_id>/`. `lilrae lab start` creates one run per start
and names it `run_<UTC timestamp>`, for example `run_20261011T135200Z`. The
`lilrae runs` commands list only run directories that contain a `manifest.json`,
which `lilrae lab start` writes as its last step.

A run holds only what its writers produced. The tree shows the layout that the
shipped code writes; most paths appear only when the scenario, command, or
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
| `provenance/startup-provenance.json` | `src/aptl/core/provenance/record.py`, called by `lilrae lab start` | After the lab-start run record |
| `provenance/run-provenance.json` | `publish_provenance_record` in `src/aptl/core/provenance/record.py` | A caller that holds the admitted and executed run context publishes it; no `aptl` command does |
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
| `kali-side/<session_id>/` | `harvestSession` in `mcp/aptl-mcp-common/src/captures.ts` | An MCP server whose lab config names a capture container (the shipped red config does) finishes a `<prefix>_run_command` call, closes a session through `<prefix>_close_session` or `<prefix>_close_all_sessions`, sees the remote side of a session close, or shuts down with a session open. For the red server, `lilrae lab start` names this workspace's capture sidecar in `LILRAE_MCP_CAPTURE_CONTAINER`. The sidecar's capture broker writes `frames.jsonl` and `metadata.json` under `/var/log/aptl/captures/<run_id>/sessions/<session_id>/`. The harvest copies that directory after the broker confirms `metadata.json`. When the harvest fails, the directory holds `capture-harvest-failure.json` instead, which names the failure (see [Kali Red Team](../components/kali-redteam.md#mcp-integration)). A server that names no capture container does not harvest |

Only the execution controller (`src/aptl/core/execution/`) produces terminal
attempts. A run that `lilrae lab start` created never holds `seal.json`, so it
stays unsealed.

MCP servers write `mcp-side/` and `kali-side/` into the run that
`APTL_MCP_ADMITTED_RUN_ID` names in their environment. `lilrae lab start` sets it
in `.mcp.json` for the red and blue servers when it connects them to the lab's
Kali ingress; a server started without it writes under an `_unbound` run
instead. The capture broker's own record of the Kali sessions reaches the run
under `evidence/` when `lilrae lab stop` finalizes a full-run transcript capture.

The participant workbench (`src/aptl/workbench/runtime.py`) keeps its own run
store under its state directory and appends session events to
`<run_id>/workbench/events.jsonl` there.

## Run Provenance (`provenance/`)

Records which apparatus the run was actually realized on, so a later reader can
tell exactly which scenario, backend, participant implementation, images,
detector rules, collectors, and configuration produced the results.

There are two records, written at different lifecycle boundaries:

- `startup-provenance.json` is **provisional**. Lab start knows the effective
  configuration, detection content, dependency locks, and realized images, but
  not the admitted trial plan, the realized participants, or any execution
  outcome.
- `run-provenance.json` is the canonical **ready-to-seal** record, written by
  the collector that owns the admitted and executed run context. Publishing it
  without that context is refused rather than written with the experiment and
  participant sources reported missing.

Both are written **create-once**: republishing identical content is a no-op,
and republishing different content for the same run fails rather than
overwriting. Separate paths are what keep the provisional startup artifact from
foreclosing the later canonical write. Neither record is a seal; they carry no
signature or attestation claim.

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
so its provisional record reports those two sources `unavailable` rather than
leaving them out.

Content identity is framed per artifact: every detector rule, decoder,
allowlist, image, and configuration is a leaf bound to its logical role, and
family identities fold the sorted leaves. Changing one rule therefore moves
that rule's leaf and the aggregate, and nothing else. Secret sources are
excluded by allowlist before collection: `.env`, rendered secret-bearing
config, credentials, and private keys are never read or hashed.

## Sealed Terminal-Attempt Records (`manifest.json`, `seal.json`)

Every terminal execution attempt produces one conformant, sealed ACES run
record (ADR-050). The execution controller (`src/aptl/core/execution/`) drives
each admitted trial: it runs the trial workload under the evidence coordinator,
normalizes the terminal cause, and hands the archival coordinator an immutable
terminal-attempt context exactly once. The archival coordinator consumes the
admitted plan, the observed apparatus and participant provenance, the evidence
acquisition result, the evaluator-supplied result summaries, the clock context,
and the normalized terminal cause, and it composes the public RAES
`ExperimentRunModel` (`schema_version = experiment-run/v1`). It never recomputes
metrics, reconstructs captures, or infers a run from mutable state.

Each attempt always records its own terminal attestation as lifecycle evidence,
so the run record's mandatory evidence, traceability, and result fields are
satisfied even when a trial ends before any authored capture starts.

- `manifest.json` is the canonical serialized RAES run record for a terminal
  attempt. In a run that `lilrae lab start` created, `manifest.json` is the
  `aptl.run-record/v2` reproducibility record instead. One version-dispatching
  adapter reads every shape, including older `aptl.run-record/v1` archives.
- `seal.json` is the atomic seal marker. A run is discoverable as sealed only
  after this marker is durably committed. Before it exists the attempt is an
  unsealed recovery candidate even if `manifest.json` is present. The marker
  binds the canonical run-record digest, a bounded inventory (path, media type,
  size, and checksum for every sealed artifact), the applicable contract
  versions, and an explicit completeness and limitation statement.

Each execution attempt receives a distinct `attempt_id`, which is also its
portable `run_id` and its run-directory name. A retry reuses the same admitted
plan and `planned_trial_id` but gets a new `attempt_id`; retry and repair
lineage travel as RAES run references (`used_refs`, `derived_from_refs`,
`generated_refs`, and, where applicable, `invalidation.superseded_by`). The
terminal cause maps to the record's real status and is never overwritten by the
seal: completed execution records `completed` with the evaluator's outcome;
scenario or evaluator failure records `failed`; cancellation, policy stop, or
infrastructure interruption records `aborted`; capture loss or another validity
failure records `invalidated` with an invalidation reason; and a replaced record
version records `superseded`.

Sealing is atomic and immutable. The record and every referenced artifact are
verified and checksummed through the run store's descriptor-relative, no-follow
boundary before the marker is published create-once with durable, no-replace
semantics. Once sealed, every overwrite-capable writer refuses; a correction is
a new run version or attestation with explicit lineage, never an in-place edit.
Export packages the already-sealed bytes and never writes back into the archive.

A small, append-safe discovery index under the run store records bounded routing
facts (attempt identity, run version, manifest digest, seal state, terminal
timestamp, and safe relative location) using a prepared and committed journal.
Discovery replays that journal and verifies each entry against the on-disk seal
marker, so restart discovery works without scanning or trusting arbitrary
filesystem paths. The index is derived and rebuildable from sealed archives; its
loss never changes the portable record or the seal.

## Range Snapshot

The range snapshot records the realized lab for reproducibility. No separate
snapshot file exists: `lilrae lab start` captures the snapshot in the step before
its run record and embeds it in `manifest.json` at
`backend_evidence.range_snapshot`. `lilrae lab status --json` prints a fresh
snapshot, and `lilrae lab status --output <file>` writes one to a file with mode
`0600`. Capture and serialization live in `src/aptl/core/snapshot.py` and
`src/aptl/core/snapshot_models.py`. Contains:

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
| `containers[]` | Name, image, status, health, labels, networks, ports, and restart policy for each container the project owns |
| `wazuh_rules.total_rules` | Total Wazuh rules loaded |
| `wazuh_rules.custom_rules` | Custom rules in `/var/ossec/etc/rules/` |
| `wazuh_rules.custom_rule_files` | List of custom rule XML filenames |
| `wazuh_rules.total_decoders` | Total decoders loaded |
| `wazuh_rules.custom_decoders` | Custom decoders count |
| `networks[]` | Docker network name, subnet, gateway, connected containers |
| `config_hashes` | SHA-256 of `aptl.json` and of each `docker-compose*.yml` or `docker-compose*.yaml` file in the project directory. `.env` is deliberately excluded: it holds control-plane secrets whose values have a small guessable domain, so a digest of it would be a confirmation oracle rather than an opaque identity. |
| `services[]` | Service endpoints (name, URL, host, port, protocol) of running containers |
| `ssh[]` | SSH endpoints (name, host, port, user, key path, command) of running containers |

Snapshots and trace exports must not contain live credentials, API keys, bearer
tokens, cookies, JWTs, private key material, or default lab passwords. Redact at
the common serialization/tracing boundary before writing JSON or OTel span
attributes; do not rely on archive location, file permissions, or export
controls as the primary protection.

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
- `src/aptl/core/archival/`: Terminal-attempt archival, covering RAES run-record composition, terminal-cause status mapping, atomic seal marker, discovery index, and the legacy-manifest read adapter
- `src/aptl/core/execution/`: The execution controller that drives admitted trials to sealed terminal records, plus the owner-native RAES sub-model bridges (clock, apparatus context, parameters, stochastic controls, evidence artifacts, result summaries)
- `src/aptl/core/lab.py`: The `lilrae lab start` steps that capture the range snapshot and write the run record, provisional provenance, and correlation projection
- `src/aptl/core/snapshot.py`, `src/aptl/core/snapshot_models.py`: Range snapshot capture logic and dataclasses
- `src/aptl/core/exporter.py`: Local tar.gz and S3 export
- `src/aptl/core/evidence_bundle/`: Portable evidence bundle build and verification
- `src/aptl/cli/runs.py`: CLI commands (`lilrae runs list|show|path|export|export-bundle|verify-bundle`)
