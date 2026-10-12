# Issue #954 Runtime Documentation and Test Authority Preflight

Assessed 2026-10-12 at `c2ffc5ae`. This is guidance, not an implementation
plan. The supplied issue is the contract; no GRC workflow requirement or
status transition is attached. No new ADR is needed: ADR-025, ADR-029,
ADR-037, ADR-041, ADR-048 and ADR-053 already own the relevant boundaries.

## Authority and evidence boundaries

Describe the candidate's admitted and realized runtime, not a remembered
release or a YAML file's mere presence. Bind product claims to the candidate
revision, installed dependency/pack identity, scenario selection, backend and
capture/observability settings. Missing observations remain unknown.

The root `docker-compose.yml` is not wholly inert. Individual image-free
services, including Kali, are exclusion stubs; explicit project-tree scenarios
can still consume its other services. Acquired packs instead generate their
Compose model. Capture and observability Compose assets remain backend-owned
apparatus. Temporary Compose files in tests can be legitimate backend inputs.
Neither a filename search nor the issue's count of 37 files establishes which
assertions are obsolete. Preserve useful contracts while replacing their
evidence source; remove assertions whose only contract was a retired stub.

Use these distinct evidence levels:

| Claim | Canonical evidence owner |
| --- | --- |
| Authored intent and admission | `core/scenario_bundle.py`, `backends/_raes_scenario_resolution.py`, RAES parser/compiler/planner, `backends/raes_realization.py`, and `core/deployment/realization.py` (`DeploymentRealizationSpec`) |
| Image-backed lowering | `core/deployment/_compose_node_generation.py::render_realization_compose`; it omits image-free nodes and does not represent the entire running lab |
| Effective Compose services | `_compose_model_realization.py`, `_compose_runtime_materialization.py`, `runtime_materialization.py`, and the production file-set/profile/project-directory assembly, including generated overrides and selected backend apparatus |
| Image-free substrate | `backends/raes_base_substrate.py`, `raes_materializer.py`, `_compose_base_substrate.py`, and native runtime observation; absence from rendered Compose is not absence from the lab |
| Host access and ports | `core/host_ports.py`, `backends/raes_operator_access.py`, `_operator_access.py`, `_compose_port_readback.py`, runtime inventory and `cli/lab_render.py`; a relay, a node listener and a published host port are different objects |
| Capture and socket authority | `_compose_capture_apparatus.py`, `backends/raes_runtime_orchestration.py`, `runtime_authority.py`, `_compose_runtime_orchestration.py`, and `_compose_runtime_observation.py` |

Paths beginning `core/`, `backends/`, or `cli/` are under `src/aptl/`;
deployment helper basenames are under `src/aptl/core/deployment/`.

Rendered-model tests prove lowering and composition, not successful deployment.
Use native readback for running image identity, socket binds, listeners and
actual host publications. Expected values come from the authored contract or
independent security invariant; comparing a renderer to its own copied output
is not regression coverage. Negative cases must detect lost fields, unintended
publication, an undeclared socket holder and unavailable readback. Do not turn
observation failure into an empty successful inventory.

Generic machinery tests reuse the import-safe `tests/fixture_pack.py` and
`docs/testing/lab-fixture-pack.md`. TechVault product assertions retain the
installed pack and existing `tests/test_env_pack_realization.py`, static/live
gate and operator-access patterns. Do not import `tests/helpers.py` casually:
it reads project environment and can run provisioning during import. A shared
test adapter, if needed, takes a validated realization and explicit scenario
root/settings and delegates to existing production owners; it must not become
a second renderer, SDL schema, port parser or lifecycle controller.

## Required cross-cutting passage

Documentation and test changes add no runtime authority. Examples and fixtures
must still satisfy every layer below rather than bypass it for convenience.

| Layer | Required reuse and guardrail |
| --- | --- |
| Configuration and pack shapes | `core/config.py::load_config`, closed `AptlConfig` models, `ScenarioSourceConfig`, bundle containment, env-pack validation/content digests and RAES semantics own input validation. Preserve exact pack identities and the project/staging/realization-root distinction. Do not add another YAML validator or copy pack SDL into the checkout to resurrect removed paths. |
| Environment binding and credentials | `core/env.py`, `backends/_scenario_environment.py` alias/fixture validation, `backends/scenario_startup.py`, existing credential-source models and generated-artifact bindings own runtime values. Use isolated synthetic fixture values and temporary roots; no ambient operator credentials, new config keys, or secret literals in published examples. |
| Effective runtime validation | `qualify_runtime_materialization`, `effective_runtime_contract_issues`, effective stateful-model and orchestration-model checks own supported fields, mounts and authority integrity. Exercise the selected production route and complete file set. Do not weaken a gate or hand-merge YAML to manufacture a passing model. Secret-bearing Compose inspection uses the incumbent non-interpolating path. |
| Docker and OS authority | `DockerEndpointBindingMixin`, `core/execution_boundary.py`, backend subprocess runners and ownership receipts bind the daemon and native resource identity. Socket access is host-root-equivalent even with a read-only mount; spawn-template/image declarations do not sandbox the holder. Keep local socket, rootless/VM daemon, remote endpoint and outer seat boundary distinct. Reuse list argv, stdin secret delivery, bounded timeouts and owned cleanup; no secrets in argv/history, context switching, daemon-wide prune or repair of a user's running lab. |
| Network and session access | Host-port resolution/readback and operator relay proofs own remapping and loopback binding. In-range reachability does not require wildcard host publication. Capture broker custody, SSH key/host-key checks and shared MCP SSH transport remain mandatory. A relay reaching port 22 does not prove an ordinary SSH shell is supported when capture requires run/session custody. Do not disable capture, TLS or authentication to make an example work. |
| API/MCP authentication and envelopes | If examples traverse these surfaces, retain `api/deps.py` Host/session/CSRF gates, `api/schemas.py` response shapes and `mcp/aptl-mcp-common` auth/TLS/tool handlers. No new endpoint, credential handoff or error hierarchy is justified. Core failures retain `LabResult`, `StartupOutcome`, `StartupDiagnostic`, deployment exceptions and RAES diagnostics; tests distinguish unsupported, failed and unobserved from ready. |
| Logging, redaction and persistence | `utils/logging.py`, Python/MCP common redaction, ADR-029, lifecycle locks, private generated state, runstore and resource receipts remain the owners. Report bounded sanitized facts, never raw environment, inspect/config output, keys or archives. Evidence stays local/private; do not rewrite sealed runs or fetch/upload artifacts to a new service. |
| Workflow and packaging | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/run-targeted-tests.sh`, staged `pre-commit run`, asset-manifest/wheel checks, MkDocs/Vale and `.github/workflows/checks.yml` remain canonical. Targeted local checks only; full suites, prose/site gates and clean lifecycle/installed-wheel qualification belong in CI/CD. No requirement transitions or invented traceability UID for this issue. |

## Documentation guardrails and scope

Reassess each reported mismatch against the candidate: Kali already documents
the Debian/systemd substrate, relay and capture restrictions;
`docs/deployment.md` already explains Docker socket holders;
CLI-005 already dates the removed commands and updates its traces. Several
RAES records already carry historical notices. Do not overwrite those fixes
or alter audited requirement statements to make a text search green.

Current user instructions must point to existing Typer commands, installed
catalog selection and `aptl lab info` discovery. A default port is conditional,
not a promise; use actual remapped ports and runtime container identities.
Keep one socket explanation in deployment guidance and link component pages
to it. Distinguish declared pack holders (currently Orborus in the tested pack),
static configuration possibilities, admitted holders and observed mounts.
Do not advertise static socket binds as admitted or protected behavior.

The issue's stale-reference acceptance criterion applies beyond its examples:
SCN-003/SCN-009 still name removed scenario commands and OBS-003 names a
removed scenario trace. Audit current user/requirement references as well as
the listed files. Historical records may retain old text only with a prominent
dated scope/supersession notice and a current reference. Preserve original
evidence; do not globally replace historical paths with today's pack paths or
infer an original record date when only the correction date is known.

The extension seam is existing validated scenario/pack selection plus explicit
backend, profile, capture and resolved-port inputs. Another pack, an occupied
port or optional apparatus must change these inputs, not require editing a
hardcoded service matrix. Generic tests stay product-neutral; exact TechVault
facts stay pack-qualified. No docs-only port/socket registry is warranted.

Whole-repository scope includes user and requirement docs, historical RAES
records, CLI/config/catalog/bundle resolution, RAES admission and lowering,
both deployment routes, backend overlays, daemon selection, ownership, runtime
observation, capture and operator access, packaging, tests and CI/prose gates.
ADRs describing proposed hardening are not evidence it shipped: ADR-055 is
proposed, while issue #956's fidelity boundary distinguishes shared-host lab
operation from seat containment. This issue must describe that boundary without
inventing operator allowlists or claiming Docker-socket containment.

Non-goals: implementing runtime fixes, changing images/ports/socket grants,
restoring retired commands or scenario files, changing pack content, redesigning
capture or security policy, adding schemas/services/generators, running or
modifying a live lab, rewriting the #851 onboarding journey, and changing
release metadata. Proven runtime defects should be surfaced for their owning
issue rather than concealed by weakened assertions or corrected prose alone.
