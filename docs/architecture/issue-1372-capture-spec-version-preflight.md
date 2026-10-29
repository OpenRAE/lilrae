# Issue #1372 Capture Spec Version Preflight

Run capture-spec pins must come from the admitted specifications, independently
of whether a collector produced a record. Preserve canonical trial-plan bytes
for identical admission inputs. This is a contract repair within
[ADR-047](../adrs/adr-047-raes-experiment-admission-and-trial-plan-boundary.md),
[ADR-044](../adrs/adr-044-raes-aligned-run-reproducibility-record.md), and
[ADR-050](../adrs/adr-050-terminal-attempt-archival-and-atomic-seal.md); it needs
no new ADR or portable schema.

## Current boundaries and gaps

- `experiment/admission_steps.py:_resolve_one_capture_spec` validates identity,
  an authored version when present, and task scope. `_build_source_set_projection`
  records each resolved `spec_version` and artifact digest. An unversioned
  authored reference therefore still resolves to a concrete admitted version.
- That projection is **only hashed** in `experiment/admission.py`. Neither
  `TrialPlan.canonical_bytes` nor `AdmissionResult` retains its `capture_specs`
  map. Execution cannot read versions out of the existing persisted plan or
  recover them from `source_set_digest`.
- `execution/assembly.py:build_traceability` currently copies acquisition
  record references and deduplicates by spec ID. `evidence/records.py` omits
  record-level versions. `CaptureBinding` pins collector execution details;
  its `contract_version`, `implementation_version`, and `channel_ref_version`
  are different concepts from a capture specification's `spec_version`.
- Every attempt also emits the executor-owned `aptl.lifecycle` capture pin at
  version `1.0.0`, including attempts without authored captures. It is additional
  to the authored capture specs, not an admitted authoring input.
- `archival/run_record.py` invokes the RAES structure, archival datetime, and
  applicable time-model validators. Structure validation does not prove
  content-backed evidence satisfaction.

## Architecture guardrails

The authority is the resolved `ExperimentCaptureSpecModel.spec_version` used
in admission's source-set projection. Carry a stable snapshot of those admitted
identities through the existing `AdmissionResult` and `AdmittedExperiment`
handoff into assembly. Reuse public `ExperimentCaptureSpecReferenceModel`
values or admitted public models; extend the existing value transport only.
Do not add a registry, service, DTO hierarchy, metadata file format, or another
resolution pass. A frozen dataclass alone does not make a contained dict or
Pydantic model immutable: snapshot values and prevent later caller mutation
from changing an attempt's pins. Rejected admission carries no admitted pins.

Keep `CaptureBinding.binding_projection()`, trial projections, plan schema,
canonicalization, source-set projection, and identity algorithms unchanged.
Retaining admitted metadata outside the canonical projection must not change
plan bytes, IDs, or digests for the same inputs. A real change to the admitted
spec version or source bytes must still change the existing source-set digest
and derived plan identity.

The authored run pin set must equal the admitted `(capture_spec_id,
spec_version)` set, with one entry per spec, plus the existing lifecycle pin.
Use deterministic ordering. Several requirements or records can share one
spec; they do not create extra spec pins. Missing or failed captures must not
erase admitted intent, and pinning intent must not imply successful capture.
Keep `evidence_record_refs` tied to actual emitted records.

An acquisition record must resolve to an admitted spec, except for the
executor's lifecycle record. A supplied record version must agree with that
pin; an absent record version can remain absent. Unknown IDs, missing admitted
versions, conflicting versions, or collisions with the executor-owned lifecycle
identity must fail explicitly before sealing. Do not silently skip them,
default a version, or let first-wins deduplication hide disagreement.
Check admitted metadata completeness and lifecycle identity collisions at the
execution handoff before running a workload; check record agreement in assembly.

Normal execution and `ExperimentExecutor.recover_interrupted_attempt` must use
the same admitted snapshot. Recovery cannot reconstruct versions from a digest
or consult current config, the collector registry, or newly resolved files.
The recovery caller must supply the original admitted metadata; unavailable
metadata is a failure to finalize, not permission to guess historical identity.

## Cross-cutting layers to preserve

Paths below are relative to `src/aptl/` unless otherwise stated.

| Layer | Canonical owner and required behavior |
| --- | --- |
| Input and policy gates | `core/experiment/resolver.py`, `spec_loading.load_capture_spec`, `AdmissionPolicy`, and `admission_steps` own authorized bounded bytes, duplicate-key rejection, RAES model validation, identity/version/scope joins, and duplicate spec-ID rejection. `capture_mapping.bind_capture_requirements` and `CollectorRegistry` retain capability admission. Transport already-admitted values; add only the missing cross-owner joins, without a second parser or schema validator. |
| Portable reference and run shapes | Public RAES `ExperimentCaptureSpecReferenceModel`, `ExperimentRunTraceabilityModel`, and `ExperimentRunModel` own field validation and serialization. Capture refs support `ref_version` but forbid `ref_digest` and `ref_path`, including explicit null fields. Use their serialization conventions; keep resolved-byte digests in their existing internal authority. |
| Seal validation | `core/archival/run_record.py:build_experiment_run_model` retains all current public validators; `finalize_terminal_attempt` remains the single seal owner. Failed identity joins cannot yield a manifest/seal claiming valid pins. Pin equality is a narrower claim than full content validation. |
| Secrets and persistence | `core/runstore.py:LocalRunStore` and `utils/redaction.py` retain canonical create-once writes and the no-secret-drift check. Reject secret-shaped identity material rather than redacting it into a different pin. Keep record ledgers, content digests, manifest digest, seal inventory, finalization locks, and discovery index under their existing owners. |
| Filesystem and host | `utils/pathsafe.py` and the injected run store retain validated IDs/relative paths, descriptor-relative no-follow access, atomic publication, and sealed-state guards. Pin transport requires no new path, URI reader, subprocess, host probe, or network access; spec IDs and versions remain inert data. No credentials enter argv. |
| Config, env, and auth | No new setting or env binding is needed. Strict `core/config.py:AptlConfig`, `core/env.py`, deployment `_environment_bindings.py`, and API `deps.py:WebAuthSettings`/`verify_token` remain outside pin lookup. Do not source versions from env, credentials, API requests, Docker, or session state, or introduce a new endpoint. |
| Errors and observability | Reuse `core/experiment/errors.py` safe `Diagnostic`/`AdmissionRejection` handling and `backends/raes_diagnostics.py` rendering at admission boundaries. Assembly/archive failures use existing validation exceptions; do not add an exception hierarchy or convert a failure to an empty pin list. `utils/logging.py:get_logger` and executor/archive status-and-count logging remain sufficient. Never log raw Pydantic inputs, captured content, credentials, or unsanitized exception text in CLI/API errors. |
| Readers and export | `core/provenance/providers/experiment.py`, archival readers/verifiers, `core/evidence_bundle/`, `core/exporter.py`, and MCP run capture consume existing identities and stored bytes. They must not become version lookup or repair authorities. Existing sealed runs stay immutable; correcting history requires separate lineage-bearing work. |

The extensibility seam is an explicitly supplied admitted set keyed by capture
spec identity, independent of collector, requirement count, scenario, backend,
and attempt outcome. Admission already rejects multiple versions of one spec
ID. Supporting that future variation would require a deliberate admission and
identity-contract change, not last-writer-wins map behavior in assembly.

## Evidence and dependency limits

Extend existing admission, trial-plan, evidence-record, and execution/archive
fixtures. A focused test must exercise admission-to-assembled-run pin equality
using non-default versions, multiple specs, and several records sharing a spec.
Assert the full expected set including the lifecycle pin, uniqueness, and that
records may remain versionless. Lifecycle-only execution, failed capture or
recovery, missing/mismatched metadata, and unchanged canonical bytes for
identical inputs are the relevant boundary cases. The current executor fixture
has no authored captures, so its structure-only success cannot catch this bug.

The current `pyproject.toml`/`uv.lock` pin is `raes==7.0.0`. Its installed
`evidence_satisfaction._validate_supplied_evidence_sets` checks exact run
ID/version sets, while `_validate_record_capture_identity` still requires
record versions. The issue's OpenRAE/rae#1547 record-resolution behavior is
therefore a dependency condition, not a behavior this repair can assume.
Use the issue's permitted exact-pin equality test without claiming full
evidence satisfaction. A full-validator test additionally needs a released
dependency with that behavior, real lifecycle and authored capture specs,
matching records/apparatus/windows/disclosures, and explicit bounded artifact
streams. Do not monkeypatch, vendor, weaken, or duplicate the RAES validator.

Verification follows `.ground-control.yaml`, `.gc/plan-rules.md`, and
[CI verification](ci-verification.md): targeted paths through
`bash tools/run-targeted-tests.sh`, then staged-file `pre-commit run` hygiene.
`.github/workflows/checks.yml` owns whole-suite coverage, prose, and strict docs
builds. Keep the guidance linked in `mkdocs.yml`. This issue-only repair has
no formal requirement UID and no requirement lifecycle transition.

## Non-goals and anti-patterns

- No plan/digest migration, dependency upgrade, collector redesign, new config,
  env grant, controller workflow, API, schema mirror, validation framework, or
  remote service is needed to meet the issue's pin-equality acceptance option.
- Do not move capture versions into binding projections, confuse them with
  record/run/collector/channel/schema versions, or hardcode authored versions.
- Do not mutate acquisition records or sealed archives to fill the gap, remove
  lifecycle evidence to make set comparisons pass, fabricate missing captures,
  or broaden production sealing to content-backed validation without its inputs
  and a separate compatibility decision.
