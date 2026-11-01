# Issue #1556: RAES and env-packs Go boundary preflight

The supplied issue is the delivery contract. This note constrains the consumer
inventory and the upstream links; it is not that inventory or an
implementation plan. LilRAE is downstream of RAES and env-packs. It conforms to
the Go API that they set, and it makes no request or change to their issues.
Inspection at `bf8edd67` found
`uv.lock` selecting RAES 10.1.0 and env-packs 7.0.0. Historical release pins in
the [#845 preflight](issue-845-raes-hard-rename-preflight.md) describe that
cutover, not the Go contract.

No new ADR is needed. ADR-035, ADR-046, ADR-047 (including its released-contract
successor clause), ADR-051, ADR-053, and ADR-065 already establish the ownership
boundary. ADR-054 remains proposed; it is not evidence of an accepted ownership
transfer. The [family adapter contract](family-adapter-contract.md) and
[public adapter reference](../reference/family-adapters.md) define the existing
extension obligations.

## Capability authority and inventory coverage

RAES owns SDL, portable contracts, compilation, planning, runtime progression,
participant lifecycle, canonical identities, and backend conformance. Env-packs
owns pack structure, content identity, artifact resolution, and catalog
semantics. LilRAE owns authorized acquisition, apparatus policy, backend effects,
native observations, protected persistence, and public result projections.
An unavailable Go capability is an upstream dependency, never permission to
implement its semantics locally.

The inventory must reconcile every import occurrence in `src/`, including
function-local imports, `TYPE_CHECKING`, aliases, module imports, and re-exports.
Use syntax inspection without importing or executing product modules; the AST
walk in `tests/test_raes_namespace_cutover.py` is the existing example.
Follow module aliases to the attributes actually consumed, and distinguish
import occurrences, unique names, and capabilities. The eight Python import
roots in the issue do not imply eight independently versioned distributions:
`pyproject.toml` and `uv.lock` own the actual release graph.

Group by capability, with source locations and consuming LilRAE areas as
evidence. Record the operations and result/error behavior needed by callers,
not only symbol spelling. Include constructors, validators, serializers,
constants, protocols, corpus/resource access, and private attribute dependencies.
For stored or adapter-visible types, distinguish runtime objects, canonical
bytes, persisted envelopes, safe projections, and public callback signatures.
An import list alone establishes none of these contracts.

Keep the inventory a readable architecture document, with evidence tied to its
source revision and dependency versions. It needs no new inventory language,
plugin registry, service, database, or permanent workflow. Tests and tooling
outside `src/` inform conformance and ownership; they do not replace the required
source coverage or silently expand its denominator.

## Public extension points and ownership seams

- `backends/raes_planning_compat.py:AptlRuntimeManager` wraps apply, inventory
  refresh, and evaluation to retain native evidence. Its planning path compiles
  and plans once using the committed snapshot, admitted compatibility decision,
  profile, availability, and run scope. `_runtime_value_limits` temporarily
  changes RAES module globals, including private `_VALUE_LIMITS`. The Go port
  uses the configuration and the hooks that RAES Go sets for this behavior, and
  it is blocked until they exist. Do not reproduce this global mutation, lock,
  inheritance, or hidden-state embedding in Go. The existing pending reference
  `OpenRAE/rae#1285` is evidence to check, not proof of a Go contract.
- `backends/raes_participant_driver.py:AptlParticipantControlPlane` uses private
  `_target` and `_reject_submission` access. Its solicitation enters RAES's
  participant operation executor so durable operation state precedes provider
  execution; failure, idempotency, and request fingerprints remain governed.
  The Go port uses the operation extension point that RAES Go sets with those
  guarantees, and it is blocked until it exists. It adds no callback that runs
  before admission and no local operation-state machine.
- Do not stop at the two classes highlighted by the issue.
  `backends/raes_participant_runtime.py:AptlParticipantRuntime` also extends
  RAES `BaseParticipantRuntime`. Separate LilRAE provider mediation, budgets,
  installed bindings, and bounded effects from RAES admission, commit, history,
  and concurrent-action semantics. The Go port keeps that split in the seam
  that RAES Go sets.
  The namespace test checks private imports; it does not detect private
  attribute access or certify the entire API surface as public.
- `backends/raes_repro.py:runtime_snapshot_record_payload` now uses public RAES
  serialization and value-free credential projection. The #845 note's private
  serializer warning is historical. Preserve the current public capability,
  rather than asking for or copying an obsolete private function.
- ADR-065's future public `adapter/` signatures may use their own types and
  public RAES types, never inaccessible LilRAE `internal/` types. Keep the six
  qualified family capabilities, exact atomic pack/family/backend matching,
  detached trial inputs, and core-owned storage/redaction. Compile-time
  registration changes delivery, not those admission rules. Pack acquisition
  cannot install executable adapters or select code paths from pack text.

The variation seams are public upstream hooks and per-runtime options, plus
the existing target/profile, corpus-root, and backend-witness inputs. A larger
admitted pack needs a bounded runtime option, not a process-global override.
A new pack/backend release qualifies through existing identity and capability
selectors; it must not require TechVault-specific branches in shared code or
another portable model. RAES Go sets the exact Go signatures.

Paths in the following table are relative to `src/aptl/` unless stated otherwise.
These are behavioral owners to preserve, not a Go package layout to transliterate.

## Required passage through cross-cutting layers

The #1556 deliverable is documentation and issue relationships. It adds no
runtime input, listener, config field, credential source, or privilege. Its
evidence contains source references and safe identities, not live snapshots,
environment values, credentials, or customer artifacts. Repository inspection
does not authorize uploads, new services, or upstream publication of source.
The intended Go boundary must preserve each layer below.

| Layer and canonical incumbent | Required contract |
| --- | --- |
| Authentication and public projections: `api/main.py`, `api/deps.py`, `api/middleware/bff.py`, `api/schemas.py`, `api/scenario_projection.py`; shared MCP server | Existing HTTP callers retain bearer, Host, session, and same-origin mutation checks before resolution or effects. MCP retains advertised JSON Schema validation before dispatch, without coercion or inserted defaults. Upstream models do not become HTTP DTOs, MCP responses, or a new remote RAES service. CLI operator authority does not authorize another listener. |
| Configuration: `core/config.py`, `utils/strict_json.py`, ADR-025/065 | Preserve closed first-party config shapes, discriminated source kinds, bounds, placeholders, and semantic backend checks before mutation. External owner-defined inputs follow that owner's contract. The API inventory adds no config schema or compatibility alias. Strict decoding includes duplicate keys, exact names, trailing data, UTF-8, numeric fidelity, and missing/null/zero distinctions; a Go struct alone is insufficient. |
| RAES parsing and validation: `core/experiment/{spec_loading,resolver,admission_artifacts,policy,apparatus,bindings}.py` | Preserve byte/count/depth and allocation limits, duplicate-key/single-document hardening, authorized reference resolution, identity joins, and apparatus policy. Use RAES public loaders, semantic/compiler/planner checks, and sealed-plan validation before effects. JSON Schema shape validity does not prove semantic validity, authorization, backend feasibility, or trial admission. |
| Published schemas: `core/evidence_bundle/schemas.py`, RAES corpus APIs | RAES's published `contracts/schemas/` are normative upstream artifacts, not a new local schema directory. Reuse exact schema bytes, dialect, `$id`, version, checksum, and provenance. ADR-065 selects `jsonschema/v6`; resolve references from the pinned local corpus without ambient HTTP/file fetching. Stored RAES documents can be schema-validated without a local RAES model. Preserve explicit unavailable-schema limitations; a missing required admission schema/API cannot become success. |
| Pack and filesystem acquisition: `core/scenario_bundle.py`, `core/_pack_staging.py`, `core/scenario_catalog.py`, `utils/pathsafe.py` | Retain env-packs validation, exact content inventory/digests, contained bounded byte reads, fresh owned staging, symlink/hardlink/special-file refusal, and cleanup ownership. Preserve the catalog's source revision and explicit as-of date. Hash and parse the same resolved bytes. No failed acquisition falls back to checkout content, no pack supplies a root Compose model, and no network discovery is added. Go contained access follows ADR-065's `os.Root` rule while preserving these refusal guarantees. |
| Secrets and environment: `core/_credential_sources.py`, `core/env.py`, deployment `_environment_bindings.py`, `_realization_primitives.py`, `utils/placeholders.py`, ADR-029/052 | Preserve exact pack/consumer/variable grants and authored/generated/operator/adapter source distinctions. Read only granted process variables. A declared variable grants no ambient host access. Validate source availability and Docker versus Compose env-file representability before effects. Keep value-free credential result projections and reject secret-bearing executable admission inputs; later redaction cannot repair them. |
| OS, transport, and runtime effects: `DeploymentBackend`, deployment ownership/endpoint helpers, `core/lifecycle_guard.py`, `core/soc_ca.py`, `utils/curl_safe.py` | One boundary owns daemon/transport selection, project/workspace/resource ownership, locks, bounded operations, and readback. Retain TLS verification, SSH identity pins, loopback defaults, and appliance/execution-boundary policy checks. Library calls propagate cancellation and report residual resources. Any conformance process uses trusted fixed argv, no shell, bounded captured output, and no secrets in argv. No raw Docker passthrough, credential-bearing URL, ambient resolver, or second apply after failed/unknown effects. |
| Errors and observability: `backends/raes_diagnostics.py`, `core/experiment/errors.py`, `core/lab_types.py`, `utils/{logging,redaction}.py`, `core/telemetry_export.py` | Reuse structured RAES diagnostics and existing bounded result/exit/HTTP/MCP error projections. Normalize upstream failures once; exclude rejected values, raw exception payloads, private paths, and Pydantic `input`/`ctx`/`url`. Go wraps errors with `%w` and adds a sentinel/type only when a caller acts on it. ADR-065's explicit `slog` and shared redaction protect stderr logs, access logs, command results, persisted text, and exported spans. Keep logs off MCP stdout; telemetry is not evidence. |
| Persistence and identity: `core/runstore.py`, `core/archival/`, `core/evidence/`, `backends/{raes_repro,lilrae_materialization_archive}.py` | Preserve contained private writes, per-run finalization locks, create-once canonical records, seal immutability, and read-only export. RAES `RunMaterializationArchive` supplies portable bytes/validation; LilRAE still owns protected publication and seal enforcement. Use owner-defined canonicalization and the existing serialization vectors; never redact signed/canonical bytes into a different valid-looking record. Secret-bearing canonical input is rejected. Keep RAES `RuntimeSnapshot` separate from LilRAE `RangeSnapshot` and retain schema-aware historical reads. |

## Conformance and upstream links

The current backend claim is `aptl`, target version `0.1.0`, profile
`full-remote-control-plane`, owned by `backends/identity.py` and
`create_aptl_manifest()`. The current RAES backend suite is
`raes_conformance.conformance.run_target_conformance` plus the published
`raes conformance backend --profile full-remote-control-plane` corpus check.
`validation/_gate_checks.py:check_backend_conformance`,
`validation/_gate_raes_cli.py`, `tests/test_raes_backend.py`, and the
`RAES scenario validation gate` in `.github/workflows/checks.yml` are the
incumbents. Tests also exercise `provisioning-only` and
`orchestration-evaluation`; do not replace the full claim with a smaller profile.

Static checks currently defer only the two realization-envelope `no-witness`
codes identified in `_gate_checks.py` to live lab qualification. This is not
proof of live conformance or permission to add suppressions. The Go port
conforms to the suite and corpus release, the profile and contract coverage,
the backend witness and registration seam, and the static and live harness
obligations that RAES sets.
Missing runners, unknown gaps, or failed constructive/readback cases cannot
count as passing. The Go backend must be the system under test; a Python backend
passing on its behalf establishes no Go conformance.

Keep three evidence surfaces distinct: upstream RAES backend conformance,
the installed LilRAE black-box suite in `conformance/` from Go port 03, and the
persisted-byte/identity vectors recorded in
[serialization schemes](../reference/serialization-schemes.md) from Go port 04.
Reuse all applicable surfaces. None replaces the others or authorizes copying
the upstream schema/corpus into a separately maintained LilRAE oracle.

Each capability needs a real upstream owner issue. A Go port uses only a
released RAES or env-packs Go API, with the errors, limits, cancellation,
canonical serialization, and corpus delivery that its owner sets. Capability identity is stable when package paths
change; Python module paths are evidence, not proposed Go package boundaries.
Keep distribution, module, schema/profile, authored artifact, pack/family,
plan/entry, snapshot, capture, and attempt identities separate.

Go ports 16 through 22 must link their required owner issues and carry native
blocked-by relationships for unresolved capabilities. An umbrella Go milestone,
prose link, merged source change, or this preflight does not establish a usable
released dependency. Do not invent upstream issue numbers or claim an
upstream contract from repository inspection. This preflight makes no upstream
writes.

## Repository scope and non-goals

Reuse `.ground-control.yaml` (`base_branch: go-cutover`), `.gc/plan-rules.md`,
`architecture/model.yaml`, `tools/cmd/archcheck`, `.gc/pack-ownership.json`, and
`tools/check_pack_boundary.py`. This documentation issue needs no speculative
Go components or module allowlists. Later code-bearing ports declare actual
dependencies through ADR-065's design/model checks; application-owned consumer
interfaces and entry construction keep upstream adapters out of orchestration
policy. Public RAES types used by plugins need explicit module permissions.

Keep `pyproject.toml`, `uv.lock`, requirements locks, root/tool `go.mod` files,
installed asset selection, SBOM/dependency gates, and
`tools/ci/select_checks.py` with `.github/workflows/checks.yml` as their existing
authorities. Reuse namespace, pack/family admission, credential-canary,
diagnostic, archival, and static/live tests. A historical comment or passing
import test cannot substitute for current contract evidence. Local checks stay
change-scoped with `tools/run-targeted-tests.sh` and staged `pre-commit run`;
whole-tree, full-suite, and installed-lab qualification remain in CI/CD.

This preflight adds guidance only. #1556 delivers the inventory, the upstream
links and blocked-by relationships, and the named conformance obligations
against `go-cutover`.
It changes no product behavior, schema, stored bytes, package pin, capability
claim, extension version, or requirement lifecycle. It builds no RAES/env-packs
code, local semantic/model/exception mirror, compatibility facade, scheduler,
plugin sandbox, conformance runner, or new workflow. Existing ownership and
security controls are constraints on the Go port, not optional follow-up.
