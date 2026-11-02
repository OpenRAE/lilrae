# Issue #1554: Black-box Conformance Preflight

The installed command is the test boundary. The suite observes CLI results and
files through public operations; it does not import either implementation.
The supplied issue is the delivery contract, with no formal requirement
transition. This note records guardrails, not an implementation plan or a claim
that conformance already passes. No new ADR is needed: ADR-025, ADR-029,
ADR-030, ADR-031, and ADR-065 already establish the relevant boundaries.

## Contract authority and schema ownership

Start the inventory from [the CLI reference](../reference/cli.md),
[experiment runs](../reference/experiment-runs.md),
[evidence bundles](../reference/evidence-bundle-export.md), and the other
command-specific reference pages. Check documented behavior against the current
installed Python artifact and existing tests. A disagreement needs an explicit
disposition; neither a patched Python unit test nor an accidental behavior
automatically becomes a portable contract.

Each inventory row needs a stable identity, its source, contract versus
implementation-detail classification, and the case or named lab qualification
check covering it. Include options, aliases, defaults, confirmations, streams,
exit codes, JSON fields, and persistent paths. Inventory commands whose protocol
coverage belongs to a later port and name that boundary explicitly. Do not
claim that help invocation qualifies an interactive shell, MCP, or web service.
Keep the inventory readable; it needs no new workflow engine or coverage DSL.

| Surface | Canonical incumbent and constraint |
| --- | --- |
| CLI action JSON | `src/aptl/cli/_common.py` owns exits, version 1, JSON emission, prompt refusal, and free-form redaction. `cli/doctor.py` and `cli/lab.py` project their existing results. Capture those projections, not `api/schemas.py` or core dataclass layouts. |
| Startup semantics | `core/lab_types.py`, ADR-030, and `cli/lab_render.py` own outcomes, diagnostics, residue, and access reporting. Outcome, severity, impact, success, and observed ports are distinct facts. |
| Status and snapshots | `core/snapshot_models.py:RangeSnapshot.to_dict` owns the redacted snapshot. Reuse one snapshot schema for `lab status --json`, `--output`, and the embedded run snapshot. Status has no action envelope or instance schema version. |
| Configuration | `core/config.py:AptlConfig` and nested models own `aptl.json`. `_credential_sources.py` owns the discriminated source locators and grants. Publish their input shape; `config show --json` is the resolved model with defaults, not a lifecycle envelope. |
| Installed assets | `core/assets.py`, `src/aptl/_asset_manifest.py`, and `hatch_build.py` own `lab init` materialization, exclusions, and default config. Verify installed assets, conflict refusal, and explicit force behavior without reconstructing their packaging logic or freezing a release's file count. |
| Execution boundary | `core/execution_boundary.py:ExecutionBoundaryObservation` owns `aptl.execution-boundary/v1`. Reuse its definition wherever embedded. An observed daemon, a selected profile, and verified containment are different claims. |
| Run records | `backends/raes_repro.py` writes `aptl.run-record/v2` for lab starts. `core/archival/` writes RAES `experiment-run/v1` for terminal attempts. `archival/legacy_manifest.py` also reads v1 reproducibility and older flat manifests. Preserve version dispatch and legacy reads; `runstore_internals.py:RunManifest` alone describes none of this union. |
| Bundle manifest | `core/evidence_bundle/envelope.py:BundleEnvelopeV1` owns `bundle.json`, `aptl-evidence-bundle/v1`. It describes packaging and references canonical records. `evidence_bundle/schemas.py` already selects exact published RAES schema bytes; never recreate RAES schemas from LilRAE models. |

Use reviewed, checked-in schema artifacts as the independent test oracle.
Existing Pydantic models can produce candidate schemas during authoring; the
suite must not regenerate expectations from the implementation under test.
Declare each schema dialect and identity, resolve references from a closed local
registry, and reject unresolved references without HTTP or arbitrary file reads.
Use ADR-065's JSON Schema dependency rather than writing a validator. Preserve
the published RAES dialect, bytes, version, and provenance when including its
schemas. Publishing schemas must make the same artifacts available to readers
and the harness, not create a documentation copy that can drift.

Model required, absent, null, empty, and defaulted values separately. Config
rejects unknown fields at every first-party model level. Action JSON permits
additive fields without a version increase; a blanket `additionalProperties:
false` there would contradict its documented compatibility rule. Removing or
retyping a field raises that action schema version. Persisted formats retain
their own versions and rules; do not add an instance version to `aptl.json` or
to legacy snapshots just to simplify dispatch.

A schema checks structure, not the entire operational contract. Pydantic field
and model validators normalize and constrain values that generated schemas may
not express. `config validate` also calls `deployment.get_backend` and catches
constructor errors through `exit_on_invalid_deployment_settings`; a valid model
with an incomplete SSH configuration can still fail validation. Scenario
admission owns operator-group membership through `backends/raes_profiles.py`,
not a fixed profile enum. Cover these existing decisions through CLI cases;
do not add a second env parser, config validator, or admission service.

JSON Schema does not describe parser behavior or Python coercion. The existing
`utils/strict_json.py` rejects duplicate members and non-finite numbers at its
security-sensitive callers; `load_config` currently uses ordinary JSON parsing.
Do not silently apply a stricter decoder to the product here. Any conflict
between accepted Python input and ADR-065's strict Go decoding needs an explicit
compatibility disposition, not a Python-only expectation or a hidden exception.

## Process, security, and persistence boundaries

ADR-065 places the testscript suite in `conformance/` in the root Go module.
Keep it test tooling with no product imports. `tools/gates/gates_test.go` is the
existing testscript example and dependency pin, not a home for CLI cases or a
reason to introduce another module. Before Go code, the implementation must
record its actual packages and imports in the required issue design front
matter, register their narrow tooling component in `architecture/model.yaml`,
and pass the existing `archcheck design` check against `origin/go-cutover`.
Regenerate the architecture diagram through `archcheck` when the model changes.
Do not grant product components access to test tooling or its dependencies.

The binary seam is one environment variable, `LILRAE_CONFORMANCE_BINARY`,
holding an absolute executable path. Resolve it before changing directories;
execute it directly with argument arrays, never as a shell expression or
`python -m aptl`. Missing configuration, an unusable executable, process failure,
and a missing case are failures in a selected conformance job. Swapping Python
for Go changes that parameter and the install prerequisite, never a case or its
expected result. Keep the checked-in corpus and schemas independent of either
binary. Lab cases use the existing `integration` build-tag boundary.

| Cross-cutting layer | Required passage |
| --- | --- |
| Host authority and authentication | Run in fresh temporary projects with isolated home, XDG, Docker configuration, and output directories. Pass only the runtime environment a case needs. No ambient provider/cloud credentials, SSH agent, user project, or `.env` discovery. Ordinary cases need no live lab; doctor may observe host tools or an unavailable daemon, so validate its report and exit relationship rather than assuming every check passes. The lab lane uses only its dedicated CI daemon and owned project. No API/MCP authentication, external export, or new listener is needed here. |
| Environment and config shapes | Keep credential values outside `aptl.json`: `ProcessEnvironmentCredentialSource`, `ProjectEnvironmentFileSource`, and `EnvironmentGrant` hold locators. Lab setup retains `core/env.py` parsing, `EnvVars`, required-value and placeholder checks, `deployment/_environment_bindings.py` admission, `_compose_environment.py` delivery, and scenario admission. Isolate `APTL_EXPERIMENT_NO_REDACT`, Python import paths, telemetry endpoints, and Docker overrides instead of inheriting operator state. |
| OS and subprocess exposure | Keep secrets out of argv, command strings, process listings, shell tracing, and environment dumps. Use synthetic values only in redaction cases, supplied through private fixture files or narrowly bound environment variables. Preserve the product's `utils/curl_safe.py` boundary for authenticated probes. Bound process lifetime and captured output; cancel and reap children and retain unconditional project cleanup on failure. Do not run destructive lab cases against an operator daemon or parallelize them on one project. |
| Redaction and diagnostics | ADR-029 and `utils/redaction.py` protect CLI free-form fields, `RangeSnapshot.to_dict`, run writes, and `core/telemetry_export.py`. Reuse `tests/fixtures/redaction_parity_corpus.json` and its expected results, not a second taxonomy. Check the raw captured result before sanitizing diagnostic output: masking actual output before comparison would hide a product leak. Redaction-case failures must report safe case IDs and field paths without echoing inputs, raw streams, schema instance fragments, or fixture files through testscript transcripts, diffs, or CI artifacts. Include failure reporting in this review. |
| Errors and streams | Preserve `LabResult`, `LabResetResult`, `BackendObservationError`, CLI exit helpers, and existing command-specific errors. No new product exception hierarchy or universal error envelope. `utils/logging.py` writes to stderr; the harness keeps stderr separate from stdout and checks numeric exits. A nonzero process result alone does not prove the expected error, and a timeout is never an expected usage failure. |
| Files and archives | `utils/pathsafe.py`, `core/lifecycle_guard.py`, `LocalRunStore`, `runstore_internals.py`, `core/archival/`, and the bundle builder/verifier own containment, no-follow access, private modes, locks, create-once writes, atomic seals, bounded verification, and read-only export. The harness observes these through CLI and files, with no imports or replacement repository layer. Keep fixtures private and contained; never extract untrusted archives or scan an operator run store. Schema-valid bytes do not prove seal validity, archive integrity, redaction, or path safety. |

Inventory `.aptl/` by owner, not as one portable state object. Session and trace
context, lifecycle policy state, workspace ownership and resource receipts,
startup reset state, operator groups, and capture authorities have different
readers and recovery duties. Their owners include `core/session.py`,
`core/telemetry.py`, `core/lifecycle_policy.py`, `core/startup_reset_state.py`,
`core/operator_group_state.py`, `deployment/_compose_resource_ownership.py`,
and `backends/raes_evidence_acquisition.py`. Distinguish compatibility-relevant
state from locks, caches, staged packs, rendered Compose, and secret-bearing
generated configuration. An implementation detail can still have observable
security or recovery guarantees. Do not freeze generated secret bytes, lock
contents, or temporary paths, or publish sanitized copies as canonical state.

Run records, run seal markers, ready-to-seal provenance, and bundle seals are
separate contracts. Today a terminal attempt can have a committed `seal.json`,
while the bundle exporter still defaults to `UnsealedClosureVerifier` and
discloses `seal-absent`. Its verifier rejects a `verified` bundle claim without
verifiable attestation material. Preserve those facts; this issue does not
connect the two seal paths. Fixtures must cover supported legacy reads as well
as current records, including incomplete runs and ambiguous or missing run IDs.
Keep local convenience exports distinct from evidence bundles and S3 uploads.

## CI, comparisons, and limits

Extend `.github/workflows/checks.yml`, `tools/ci/select_checks.py`, and
`tools/ci/go-gates.sh`; do not fork their routing or gate logic. The current
`go-tests` job installs no Python artifact, although it will discover the root
conformance package. It must receive the installed binary for the ordinary
suite. The existing `clean-install-lab-boot` job supplies the clean wheel,
out-of-tree project, product-neutral materialization fixture, dedicated daemon,
and unconditional teardown checks for lab JSON cases. Keep its independent
realization checks; `tests/fixtures/lilrae_core_only_cli.py` is a Python-specific
qualification adapter and cannot be the conformance binary.

Routing must select conformance when its corpus, schemas, contract references,
CLI/config/persistence owners, packaging, or installed assets change.
Currently a `conformance/` edit selects Go and coverage producers but not
`lab`; a documentation schema could
select only docs. Account for both gaps in the existing selector and its
`tests/test_lilrae_ci_selection.py` contracts. Preserve required status names,
selector-failure rejection, pinned actions, hash-checked wheel dependencies,
fork restrictions, and current coverage from every selected language stack.
Do not add privileged PR execution, credentials, services, suppressions, or a
remote schema loader. Use separate state for each binary and each case.

Compare parsed JSON and factual text. Exact comparison belongs only to strings
explicitly locked by references or behavior tests, such as `Aborted.`; record
that evidence in the inventory. Help wrapping, Rich tables, ANSI styling,
Python exception names, timestamps, host versions, and generated paths are not
golden output. Check options and defaults without freezing help layout. Do not
erase contractual facts through broad regex normalization or update goldens
automatically to accept a failure.
Keep integer precision and absent-versus-null distinctions in the comparison.
Preserve array order when the inventory makes it contractual; compare sets only
where order is not a contract. JSON key order and indentation do not establish
canonical bytes or digest parity; Go port 04 owns those vectors.

Preserve the gotchas: usage exits 2 with no JSON and a stderr error; declined
confirmation exits 0 and changes nothing; destructive JSON needs `--yes`;
degraded starts still exit 0; `ok` matches exit 0 for the four action envelopes.
Status remains the older snapshot, and `config show --json` remains config.
Counts, outcome consistency, stream rules, no-mutation assertions, and redaction
need semantic assertions in addition to schema validation. Failures reachable
only through Python patching are not portable cases. Missing live prerequisites
cannot count as passed lab coverage. If the installed artifact contradicts a
documented contract, expose the discrepancy rather than alter the product,
weaken the schema, or hide it with a suppression.

Keep the action helpers' free-form-field redaction distinct from recursive
snapshot redaction: redacting an entire doctor payload would mask its numeric
`counts.pass` field. Logs are not a blanket sanitization boundary.

This issue delivers the inventory, schemas, testscript cases, and their Python
CI qualification. Later digest vectors, MCP cases, and web API cases extend
the same corpus and executable seam; they need no implementation selector or
new framework. Product changes, Go CLI implementation, digest algorithms,
canonical-byte vectors, new auth/logging/persistence systems, live external
exports, and cutover are non-goals. Target `go-cutover`; keep local verification
to changed files and staged `pre-commit run`. Full suites, builds, coverage,
mutation, vulnerability scans, and whole-tree prose checks remain CI work.
