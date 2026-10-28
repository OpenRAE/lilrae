# Issue #1406 Native Evidence Test Target Preflight

Issue #1406 is the delivery contract; no requirement is attached.
This is test dependency maintenance, with no runtime architecture change. The
checkout pins `raes==7.0.0` in `pyproject.toml`, `uv.lock`, and the hashed
requirements exports; the issue's reference to 6.0.1 is historical. Compatibility
with the first backend-free release still requires execution against that
released artifact. An import replacement alone cannot establish it.

## Target and ownership decision

Prefer `raes_backend_stubs.stubs.create_stub_target()` as the inert base for the
four refresh tests. `tests/test_raes_participant_delivery.py` already uses this
factory with `dataclasses.replace()` and
`create_aptl_manifest(participant_inject_delivery=True)`. Keep a fresh target and
`AptlEvaluator(proposition_interpreter=_INTERPRETER)` per test; the evaluator
retains mutable evidence and evaluation state.

The stub supplies unused runtime components. It does not replace the evaluator,
the RAES runtime control plane, or the TechVault truth interpreter. Preserve the
participant-enabled manifest case as an evaluator-only refresh of a target with
participant capabilities. It is not a participant execution or backend
conformance test. Keep each `ExecutionPlan.target_name` and `manifest` derived
from the composed target; do not introduce hard-coded backend identity rules.

`create_aptl_runtime_target()` in `src/aptl/backends/raes.py` remains the production
composition root. It requires config, deployment backend, scenario bundle, and
planning compatibility. Pulling that setup into these tests adds unrelated
admission and deployment coupling. Do not widen its interface for this issue.

## Cross-cutting boundaries

| Layer | Canonical incumbent and required boundary |
| --- | --- |
| Contract and shape validation | Keep `raes_contracts` evidence/reference/checksum models, plans, runtime snapshots, and `raes_processor.models.ExecutionPlan`. `AptlEvaluator.bind_evidence_records()` retains its type check. No schema copies, loose replacement dictionaries, or private upstream imports. |
| Runtime admission and commit | Keep `refresh_evidence_truth()` registering the planner-produced plan and submitting evaluation through `raes_runtime.control_plane.RuntimeControlPlane`. Preserve receipt/terminal-state handling and `close()` in `finally`. Do not mock acceptance or write truth directly to the snapshot in refresh tests. |
| Participant authorization | `_raes_evidence_refresh_policy.EvidenceRefreshCrossingPolicyResolver` rejects every participant crossing during refresh. Preserve the participant-enabled manifest case without weakening that policy or adding participant credentials. |
| Replay and state ownership | `without_evaluation_state()` clears only the evaluation domain before replaying immutable CREATE operations. Preserve the initial-evaluation replay regression; neither discard realized provisioning state nor alter operation actions to bypass admission. |
| Evidence integrity and privacy | `_raes_proposition_truth.py` delegates pack semantics to `aptl_techvault.capture.TechVaultPropositionInterpreter` and checks completeness. Keep exact requirement, predicate, channel, provenance/digest, temporal binding, and missing/duplicate record assertions. Synthetic withheld records do not exercise acquisition, blob verification, or sealing. Do not claim those guarantees from these tests. |
| Errors and observability | Keep RAES `OperationState`, `Diagnostic`, `ApplyResult`, and LilRAE `EvidenceTruthRefresh`. `_raes_evaluator_engine.evaluation_diagnostic()` applies `aptl.utils.redaction.redact()`. Preserve the exact incomplete-truth diagnostic assertion; no new exception hierarchy, logging, telemetry, or raw evidence in failures. |
| Config, env, auth, and host exposure | The stub design needs no new config or env fields, HTTP/MCP auth path, secret reads, live capture adapters, subprocess argv, sockets, containers, or deployment calls. Leave strict first-party config, runtime env binding, secret redaction, and deployment policy untouched. Construction must stay inert; capabilities in a manifest do not authorize host effects. |
| Persistence | Refresh tests use in-memory `RuntimeSnapshot` state. Existing run storage, evidence archives, checksums, and publication formats remain unchanged; do not create an alternative evidence store or persistence fixture. |

## Repository and release guardrails

The repository-wide Python import boundary covers both `src/` packages
(`aptl` and `aptl_techvault`) and `tests/`. At inspection, the native-evidence
test was the only source/test importer of `raes_reference_backend`; no
`raes_backend_libvirt` importer was found. Historical ADR mentions are not
imports and do not need rewriting. Reuse the AST import-check pattern in
`tests/test_raes_namespace_cutover.py` if making the prohibition durable; avoid a
second scanning script or a text ban that rejects historical documentation.

The extensibility seam is the existing upstream target factory plus
`dataclasses.replace()` for the evaluator and optional manifest. Another manifest
variation belongs at that seam. No target provider registry, compatibility
wrapper, global fixture, or production factory option is warranted.

Use `tools/run-targeted-tests.sh` with the native-evidence test path for local
verification, and `.pre-commit-config.yaml` for staged-file hygiene and secret
scanning. `.ground-control.yaml` and `.gc/plan-rules.md` govern that scope;
`.github/workflows/checks.yml` owns full tests, coverage, and documentation gates.
The existing assertions must keep testing success, participant-manifest
acceptance, CREATE replay, and predicate-mismatch failure without skips.

Compatibility evidence must name both exact RAES versions and run this test
module in isolated environments without a sibling checkout or stale installed
concrete backend supplying imports. Select the version at the dependency
environment boundary, not with conditional imports inside the tests. The
namespace test intentionally asserts the production pin, so its version check
cannot certify an alternate-version environment. Do not relax that assertion
to obtain a compatibility result. Record unavailable release validation as
unverified, rather than inferring it from current-pin success.

## Non-goals and anti-patterns

No RAES upgrade, new backend dependency, dependency-range widening, hand-edited
lock/export files, version or changelog changes, backend replacement, or
production evaluator changes belong here. Dependency qualification continues to
use `pyproject.toml`, `uv.lock`, generated `requirements/*.txt`,
`.pre-commit-ci.yaml`, and `tests/test_hashed_requirements.py`. Do not install a
concrete backend to keep the old import alive, vendor its implementation, catch
`ImportError`, add version branches, skip failures, weaken manifest validation,
or duplicate RAES workflow/validation logic. No new ADR is needed: this applies
the existing ownership boundary rather than creating one.
