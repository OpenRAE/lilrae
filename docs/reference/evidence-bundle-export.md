# Portable Evidence Bundle Export

The evidence bundle exporter packages a run's research evidence into a portable archive with a description of its contents.
A third party can validate this archive without APTL imports.
The exporter is the EXP-008 counterpart to `lilrae runs export`. It packages a verified artifact closure, a machine-readable inventory, exact published RAES schemas, and optional projections with loss disclosures. It does not scan arbitrary run-directory content.

Export is packaging and projection only. It performs no statistical analysis, no
claim selection, and no publishability certification, and it is never the first
redaction boundary. Redaction happens upstream at the persistence boundary
(ADR-029).

## Build a bundle

See [Export and verify an evidence bundle](evidence-bundle-operations.md#build-a-bundle).

## Verify a bundle

See [Export and verify an evidence bundle](evidence-bundle-operations.md#verify-a-bundle).

## Bundle layout

```
<run_id>.evidence-bundle.tar
  bundle.json                              # aptl-evidence-bundle/v1 envelope
  backend/run-manifest.json                # APTL/backend-owned evidence
  backend/run-provenance.json
  backend/correlation.json
  evidence/records/<record_id>.json        # canonical RAES evidence records
  evidence/blobs/<sha256>                   # referenced raw observation bytes
  schemas/experiment-core/...-v1.json       # exact published RAES JSON Schemas
  projections/jsonl/evidence-records.jsonl  # optional, loss-accounted
  projections/parquet/evidence-records.parquet
  projections/ocsf/mcp-side-ocsf.jsonl
```

Each regular file except the envelope has one inventory row. The row records bundle path, logical role, canonical-or-derived classification, source reference, contract or mapping version, SHA-256 digest, size, and media type. The row also records applicable sensitivity, redaction, and loss disclosures. The
envelope never lists itself: a checksum surface does not include or rewrite
itself.

## The `aptl-evidence-bundle/v1` envelope

The envelope is the one APTL packaging schema the bundle adds. It never restates
a field a RAES artifact already owns. An inventory row references the canonical
artifact. It does not copy that artifact's fields. The envelope carries bundle and resource-limit profiles, seal state, inventory, and data dictionary. It also carries projection descriptors, validation disclosures, and limitations.

The data dictionary references the included RAES JSON Schema for each canonical
artifact. For a projection, it records the source contract and field, target field and physical type, and null and missing treatment. It also records timestamp and integer encoding, nested-reference handling, mapping identity and version, and every known loss.

## Determinism

Two exports of the same run produce identical archives, aside from explicitly
excluded creation metadata. Inventory and packaging metadata use RFC 8785
canonical JSON with normalized `sha256:<hex>` identities and deterministic
ordering. The archive is an uncompressed USTAR with normalized member metadata
(owner, mode, and modification time) and members sorted by bundle path. The
reproducible root identity excludes wall-clock creation time. The default build
records no creation metadata at all, so its bytes are fully reproducible.

## Projections

The exporter always keeps canonical source records and their references. Projections
are optional, derived, and admitted only through a closed, versioned mapping:

- **JSONL** emits one RFC 8785 canonical JSON object per row. It keeps missing, null, unavailable, withheld, and redacted values. It also keeps string identifiers, exact timestamps, and nested references.
- **Parquet** keeps identifiers as strings even when digit-shaped, keeps
  timestamps as their exact source instant, encodes nested references as
  canonical JSON, and uses exact `int64`. Any integer outside `int64` becomes
  an exact decimal string with a declared loss disclosure rather than a
  floating-point value.
- **OCSF-aligned** keeps `mcp-side/ocsf.jsonl` verbatim. It includes the LilRAE mapping, taxonomy version, and source tool-call references. It is aligned through the mcp-red taxonomy, not
  certified OCSF-conformant.

An unknown projection format fails closed.

## Security posture

The exporter reads every source file through descriptor-relative, no-follow, one-open containment.
It rejects symlinked components and path-traversal components. Code-owned bundle paths derive from validated identifiers and content digests. Raw filenames, URIs, media types, and Unicode spellings do not become archive paths.

Resource bounds apply before allocation. They cover entry count, member size, total size, path length and depth, and decompression ratio. The verifier never extracts to disk. The shared ADR-029 redactor masks secret-shaped values in generated bundle metadata.
It never rewrites canonical bytes.

## Run store permissions

See [Export and verify an evidence bundle](evidence-bundle-operations.md#run-store-permissions).

## Seal state and partial runs

The bundle has a separate interface for seal verification.
The current default closure verifier reports the bundle as
`UNSEALED` with an explicit `seal-absent` limitation. A `ready-to-seal`
provenance state, a `SEALED_READY` disposition, a run manifest, or a
`checksums.sha256` file is never treated as a verified seal.

Partial, failed, invalid, and inconclusive runs remain exportable. Capture outcomes, provenance limitations, missing references, redaction, and loss disclosures remain intact. Export does not make a run complete, successful, or publishable. A missing referenced source becomes a
stable `missing-source` limitation rather than a substituted or fabricated
artifact.

## Export options

| Option | Meaning |
| --- | --- |
| `--projection`, `-p` | Select `jsonl`, `parquet`, or `ocsf`. Repeat for multiple projections. |
| `--output-dir`, `-o` | This option selects the destination directory, default `./exports`. Existing bundles are never overwritten. |
| `--verify`, `--no-verify` | Enable or disable local self-verification after the export write. Self-verification is enabled by default. |

## Output and source permissions

A bundle output directory must be outside the run tree, owned by the caller, and inaccessible to group and other users.
It must be a real directory rather than a symlink.
The exporter creates a missing directory with mode `0700` and never overwrites an existing bundle.

The ordinary tar.gz exporter also creates missing output directories with mode `0700`.
Its archives use mode `0600`. A repeated export replaces them atomically.
Readers of an already open archive keep its original bytes.
It creates a missing output directory only after the run passes the checks that can refuse the export, such as seal verification.
A refused export leaves no new directory.

The configured source store is `run_storage.local_path`, default `./runs` relative to the project.
The local store creates directories with mode `0700` and files with mode `0600`, independent of umask.
New parent directories receive mode `0700`.
Copied artifacts keep bytes and timestamps, but not source modes.

Each write removes group and other permissions from its owned run, namespace or locks directory, and written file.
Existing roots and other entries keep their modes.
These POSIX modes do not apply on Windows.
Permission restrictions do not replace redaction before persistence.

## Verification contract

The verifier streams bounded archive members. It does not extract them.
It recomputes member digests, sizes, inventory membership, and the reproducible root identity.
It uses the standard library and JSON canonicalization library.
It does not authenticate an external attestation.

The exporter currently writes `unsealed` bundles.
The verifier rejects every `verified` seal claim because the bundle contains no verifiable attestation material.
A successful integrity check does not establish completeness, scientific validity, or permission to publish.
Missing Parquet support records `projection-unavailable` and does not fail canonical export.
