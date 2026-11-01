# Issue #1555: Persisted Byte and Identity Vectors Preflight

Issue #1555 is the delivery contract; there is no requirement
transition. This note records boundaries, not an implementation plan or the
scheme inventory itself. No new ADR is needed: ADR-029, ADR-044, ADR-047,
ADR-050, and ADR-065 already assign the relevant ownership.

## Contract and compatibility

Vectors describe the current Python boundary, including its limitations.
Preserve each scheme's input projection, parser, serializer options, framing,
domain/version, hash, digest spelling, truncation, and consuming record fields.
Sharing SHA-256 or RFC 8785 does not make two schemes interchangeable. Do not
consolidate product helpers or correct product behavior in this issue.

There is a real policy tension: ADR-065 requires strict Go JSON/YAML decoding,
but some Python readers accept duplicates or non-finite values. Inventory
accepted and rejected inputs per boundary; do not label all malformed inputs
as universally rejected. `utils/strict_json.py` rejects duplicate members and
non-finite constants, while ordinary `json.loads` does not. Experiment loading
has its own bounded UTF-8 and duplicate-key preflights before public RAES
validation. A parser rejection, model rejection, and serialization rejection
are different observations. Raw-byte hashing has no UTF-8 validity requirement.
Any conflict with the Go policy needs an explicit compatibility disposition
before claiming parity; neither a weaker Go security gate nor stricter Python
behavior is authorized here. Record an unresolved conflict honestly.

The source dependency authority is `pyproject.toml`, `uv.lock`, and the
hash-pinned `requirements/` exports. Inspection at `97aea59d` finds RAES
10.1.0, PyYAML 6.0.3, and rfc8785 0.1.4 in the lock. Older preflights' RAES 2.0
references and removed module paths are historical, not current pins. Obtain
RAES-owned values through public models, parsers, serializers, and
`raes_contracts.corpus`; `core/evidence_bundle/schemas.py` demonstrates public
corpus access and distribution provenance. Do not inspect another checkout,
copy its corpus/schema, or recreate a RAES DTO or serializer. Missing released
contract material is a dependency gap, not permission to approximate it.

## Canonical owners and coverage anchors

Paths below are relative to `src/aptl/` unless qualified. These are inventory
anchors, not a claim that all schemes have already been enumerated.

| Concern | Incumbents the implementation must exercise |
| --- | --- |
| Admission and planned identities | `core/experiment/{resolver,spec_loading,trial_plan,trial_plan_models,bindings,capture_plan,capture_registry}.py`: locator algorithms include SHA-512 and BLAKE3 as well as SHA-256; source-set, plan, seed, binding, and capture projections have different domains. Preserve unit separators, condition sentinels, decimal ordinals, and ID prefixes. |
| RAES and compiled runtime artifacts | `backends/{raes_repro,raes_runtime_model_artifact,lilrae_materialization_archive}.py` and the public RAES publishers they call. `compiled_runtime_model_bytes()` includes a backend schema envelope and a final LF in its digest. Its enum/set/model normalization is not ordinary `model_dump()` alone. |
| Provenance and observed state | `core/provenance/identity.py`, its providers, `core/provenance/record.py`, and `core/snapshot.py`. Preserve logical-role framing, leaf ordering, duplicate-role rejection, safe effective-config projection, and legacy bare-hex/absent return forms. Volatile observations and stable content identities remain separate. |
| Correlation, attempts, and time | `core/correlation/{identity,models,clock}.py`, `core/execution/executor.py`, `core/lab.py`, and `core/runtime/workflow_engine.py`. Planned trial, execution attempt, startup run, workflow run, trace, and session IDs are distinct. Reuse `ClockProvider`/`FixedClockProvider` where consumed; record other existing timestamp producers separately. |
| Run and evidence persistence | `core/runstore.py`, `core/runstore_internals.py`, `core/evidence/{content_store,records}.py`, and `core/archival/{layout,seal,verify,discovery_index}.py`. Mutable redacted JSON/JSONL, canonical create-once JSON, raw blobs, seal markers, and index lines have different bytes and validation. |
| Bundle and export | `core/evidence_bundle/{envelope,archive,verify,schemas}.py`, its projections, `core/exporter.py`, and `utils/deterministic_archive.py`. Bundle content root, full `bundle.json`, run seal, archive checksum, member checksum, and generated `checksums.sha256` are separate contracts. |
| Resource names and authority | `core/config.py:validate_compose_project_name`, `core/deployment/{_compose_resource_ownership,_compose_owner_labels,_compose_ownership_override,_compose_node_generation,_compose_artifact_paths}.py`, and `core/ephemeral_containers.py`. Cover logical versus workspace-scoped names, truncation, retained `aptl` prefixes/labels, generated paths, and ownership receipt bytes. Names/labels narrow discovery; receipts establish authority. |
| Seat, trust, credentials, and shipped assets | `appliance/seat/{launch_descriptor,overlay_identity,image_config,image_disk_cache,image_trust}.py`, `appliance/policy.py`, `core/{appliance_boundary,execution_boundary,_credential_sources}.py`, `core/deployment/_flag_signing_keys.py`, and `utils/mcp_packaging.py`. Keep policy/version checks, credential-descriptor digests, signatures/MACs, fingerprints, and content checksums distinct; do not infer trust from a digest. |
| Other producers and consumers | `mcp/aptl-mcp-common/src/runs.ts`, `containers/kali-capture/broker.py`, `src/aptl_techvault/`, `scripts/appliance/`, `appliance/guest/`, container helpers, and release/build scripts. Classify shared formats and externally owned formats explicitly; vendored code, ephemeral hashes, and dependency pins are not automatically new LilRAE schemes. |

The inventory must join each scheme to its actual producer, all persisted
record fields and comparison readers, vector IDs, and generated file paths or
path templates. Include algorithm selection and externally owned contracts;
the issue's call-site counts are discovery hints, not a completeness test.
Document exclusions with their owner and reason. A helper-level vector alone
does not prove that a record writer hashes the same bytes it retains.

For every generated file whose digest is stored, name its producer, storing
record/field, verifier, source inputs, encoding, LF/CRLF and final-newline rule,
and serialization/dependency version. Bind vectors to the generated bytes and
their digest, including sizes where records store them. Include compiled
models, rendered overrides/configuration, evidence/projection members,
published schema bytes, and archive/checksum outputs where applicable. Pin
synthetic inputs at existing clock/entropy/effect seams; do not mask volatile
fields after hashing. Distinguish a checksum of the bytes actually produced
from a promise that every dependency version reproduces those bytes, especially
for Parquet, compression, certificates, and other binary generators.

## Shared corpus and exact comparisons

Keep one language-neutral data corpus alongside `conformance/testdata/` cases,
under `conformance/testdata/vectors/`, consumed directly by Python tests and
later Go tests. Follow the shared-data precedent in
`tests/fixtures/redaction_parity_corpus.json`; do not inherit its raw assertion
diffs for secret-bearing cases. Link the scheme inventory from
`docs/reference/conformance-inventory.md` without duplicating either inventory.
Port 03 observes installed CLI behavior; these tests call the actual Python
scheme owners. Neither requires a new product command or service.

The variation seam is a stable scheme ID/version and case ID, with explicit
input representation, expected bytes/result or rejection stage, owner contract
version, and vector references. Keep any corpus-format version separate from
product schema and algorithm versions. Use a small closed test-only dispatch
to existing owners; fixture content cannot name arbitrary imports, commands,
URLs, or paths. Adding a case for an existing scheme is a data change; a new
scheme adds only its owner binding, not another framework or product registry.

Store exact byte expectations as hex or base64 when text transport could alter
them. Raw duplicate-key input and invalid UTF-8 must reach the owner as bytes,
not as already-parsed JSON. Represent large integers as exact decimal text and
floating-point inputs unambiguously, including negative zero and exceptional
values, rather than letting the corpus decoder round them first. JSON cannot
directly carry NaN/Infinity. Minimal test-only type tags must not become a new
runtime serialization language. Fail on unknown case shapes, missing bindings,
empty selected corpora, or unexercised inventory rows; missing dependencies or
skips do not qualify a scheme.

Capture outputs from current Python owners, check them in, and compare those
fixed expectations on every run. A test must not generate both its actual and
expected result with the same code, regenerate goldens on failure, or merely
compare two Python implementations. Check bytes as well as hashes. Preserve
dictionary projections, array order, omitted/default/null distinctions,
redaction order, digest prefixes/case, and final newlines. Check producer and
reader agreement without making them share an otherwise independent verifier.
Record `ensure_ascii`, `allow_nan`, sorting, separators, indentation, and any
default conversion at each JSON owner. Go HTML escaping and raw UTF-8 output
cannot substitute for Python's existing escaping rules.

Required discriminators include non-ASCII and supplementary-plane keys,
Unicode normalization variants, escapes/control characters, `<`, `>`, `&`,
empty/nested values, booleans versus integers, `1` versus `1.0`, signed zero,
subnormal/boundary floats, exponent-format boundaries, and safe-integer bounds
and larger integers. RFC 8785 uses UTF-16 key ordering and ECMAScript number
formatting; Python sorted compact JSON is a different scheme. Exercise number
and Unicode-domain errors at the owner that actually rejects them. Raw file
digests must preserve all bytes, even when a structured serializer rejects
those same inputs. Preserve each timestamp producer's offset, precision,
zero-fraction behavior, and accepted/rejected naive values; equal instants need
not have equal strings. No repository-wide timestamp normalization under #1511.

For YAML, name every parsed file/path template feeding a digest or decision and
its loader, typed parse result, and downstream owner. Cover the root Compose
files, generated overrides, profile/port/substrate readers, capture and OTel
configuration, certificate provenance, offline-input readers, experiment roots,
and RAES SDL at their actual entry points. Include YAML 1.1 `yes`/`on`/`0755`,
quoted forms, non-string/colliding keys, timestamps, aliases/merges, duplicate
keys, non-finite scalars, tags, and multiple documents as applicable. Preserve
types that JSON alone cannot express instead of stringifying them. The
ownership loader's safe `!reset` handling is not stock `safe_load`; PyYAML
parsing is not Docker Compose interpretation or RAES semantic admission. Do not
add a YAML compatibility parser or duplicate those validators in the harness.

## Required passage through cross-cutting layers

| Layer and canonical incumbent | Required treatment |
| --- | --- |
| Authority/authentication | Offline fixture tests need no new listener, API/MCP route, external storage, or authenticated probe. Do not read operator runs, tokens, real `.env`, home state, or another checkout. Any exercised API/MCP owner retains its existing authentication and schema gate. |
| Config and environment shapes | Construct valid `AptlConfig`/Pydantic and RAES inputs through their existing owners; generated JSON Schema alone misses semantic validators. `core/env.py`, `core/_credential_sources.py`, `core/deployment/_environment_bindings.py`, and `core/deployment/_compose_environment.py` retain locator-only durable config, explicit grants, placeholder checks, and Docker/Compose env representability. Use isolated temporary projects and explicit synthetic bindings, without ambient credentials, Docker context, telemetry settings, or `APTL_EXPERIMENT_NO_REDACT`. Canonical structured-record secret checks cannot be disabled by that flag. |
| Decode, admission, and resource limits | Reuse `utils/strict_json.py`, experiment `resolver.py`/`spec_loading.py`, `AdmissionPolicy`, owner-native model/cross-artifact validation, and bundle limits. Preserve each actual limit and rejection stage. The corpus loader only validates the test envelope; it must not pre-normalize payloads, add coercion/defaults, or replace product validation. |
| Secret classification and serialization | ADR-029 and `utils/redaction.py` plus TypeScript parity remain authoritative. Use public synthetic values; secret-shaped fixtures belong only to schemes that need them. Hashing does not make a real credential safe. Mutable writes redact; create-once structured writes reject redaction drift; `write_file`/`copy_file` are pass-through and opaque evidence needs owner policy. Compare the actual retained bytes, not a sanitized substitute. |
| OS/runtime and filesystem | Use temporary directories, incumbent effect fakes, `utils/pathsafe.py`, lifecycle ownership/locks, and `LocalRunStore` private no-follow, create-once, and sealed-write boundaries. Do not call Docker/SSH, mint real credentials, access a network, or regenerate live keys merely to capture vectors. If a subprocess is unavoidable, use the existing bounded runner and argument arrays, with no secrets in argv, shell tracing, or environment dumps. |
| Errors and observability | Preserve `AdmissionRejection`/`normalize_raes_failure`, `ProvenanceIdentityError`, store/seal/bundle errors, and existing CLI/API/MCP envelopes. Match safe codes and rejection stages rather than Python exception text. No new product exception hierarchy or universal error DTO. `get_logger()` is not automatic redaction; diagnostics must exclude raw Pydantic input/context, exception causes, and source bytes. |
| Test failure and CI output | Use safe case IDs and bounded failure facts. Prevent pytest parameter reprs, assertion diffs, chained tracebacks, captured logs, and JUnit/artifact reports from printing secret-shaped fixtures. Catch and translate expected failures at the test boundary without hiding unexpected failures. Do not dump corpus files, regenerate secrets, add a secret-scanner exemption, or suppress a real failure. |
| Persistence and export integrity | Exercise `LocalRunStore`, evidence storage, archival sealing/index verification, and bundle writer/verifier through their existing contracts. Preserve no-follow containment, atomic/no-replace publication, immutability and read-only export. Keep content roots and attestations separate: bundle identity excludes `created_at` and `seal`, whereas full bundle bytes include them. The default unsealed bundle path does not become a verified run seal. |

## Known risks and delivery boundaries

Source inspection also finds `core/evidence_bundle/projections/parquet.py`
decoding RFC 8785 bytes as ASCII in `_canonical_json()`. Non-ASCII nested refs
can therefore expose a current failure; existing projection tests use ASCII
refs. This preflight did not execute that path. Surface the discrepancy when
recording vectors; do not silently fix it, omit Unicode coverage, invent a
successful expectation, or suppress the check. A behavior correction needs its
own explicit disposition outside this behavior-preserving delivery.

Extend the existing `.github/workflows/checks.yml` Python test lane and
`tools/ci/select_checks.py` selection contracts in
`tests/test_lilrae_ci_selection.py` only where needed. A corpus-only change
must select its consumers. Currently `conformance/` selects the Go, Python,
MCP, web, and lab lanes through the existing coverage closure; a new inventory
under ordinary `docs/` would select only docs. Do not add another CI workflow
or require Docker for ordinary vectors. Python tests belong in the existing
`tests/` discovery; reuse owner tests for trial plans, provenance, correlation,
runstore, archival seals, and bundle projections instead of a parallel harness.

Account for `.gitattributes`, JSON/YAML validity hooks, trailing-whitespace and
final-newline fixers, the 500 KB added-file limit, and secret detection. Encode
malformed payloads inside valid corpus documents so hooks neither reject nor
rewrite the bytes being tested; no blanket exclusions. Keep the corpus out of
runtime assets selected by `src/aptl/_asset_manifest.py`/`hatch_build.py`.

Target `go-cutover` and retain one delivery PR. Run only selected tests through
`bash tools/run-targeted-tests.sh` and staged `pre-commit run` locally; full
suites, coverage, builds, and whole-tree prose checks stay in CI. Older dated
preflights' `pre-commit run --all-files` instructions are superseded by
`.gc/plan-rules.md`. Go test/implementation changes are later ports; any such
scope change first requires ADR-065's issue design and architecture-model gate.

Non-goals are Go implementations, production refactoring or normalization,
new schemas for RAES records, new config/validation/redaction/error services,
new seal or workflow logic, security-policy changes, cutover, publication, and
live evidence collection. This note supplies no vectors or Python tests and
does not claim the issue's acceptance criteria are met.
