# Issue #1411: TechVault After TheHive Trial Expiry

Status: design preflight, aligned with the accepted owner decision in
[ADR-063](../adrs/adr-063-remove-thehive-and-cortex.md). Remove TheHive and Cortex;
TechVault will have no case-management tool. Licensing is no longer the proposed
remedy. This note adds preservation and qualification boundaries, not an
implementation plan or evidence that removal has shipped.

## Finding And Remaining Decision

The supplied observations describe an entitlement failure. Source inspection
supports the failure chain: `_techvault_native_cortex.py` requires both a fresh
successful analyzer report and healthy TheHive connector; `CortexEnrichmentSource`
returns `SOURCE_UNAVAILABLE` without that readback. The capture registration and
proposition interpreter bind both facts to `cortex-enrichment-readback`.
`core/lab.py::_step_acquire_required_native_evidence()` requires sealed acquisition
and successful RAES evidence evaluation before guest readiness publication.
First boot fails and the host eventually stops the guest through its normal
failure path. A successful Cortex job, usable case management, fulfilled scenario
contract, and running VM are different claims.

ADR-063 selects removal with a new authored pack release, tracked there as
env-packs issue #536, and accepts the loss of the case-management UI in the new
stack. It does not supply a data-preserving transition for expired
seats. Its consequence that old cases/jobs become inaccessible must not be read
as permission to delete their storage. The issue's data-preservation requirement
still applies. Before implementation of that transition, agree how an already
failed seat reaches supported operation, how retained data can be restored or
accessed, and what interrupted-transition recovery guarantees cover. New-image
success alone cannot close that gap. Do not invent a migration mechanism here.

Owner decision (2026-10-31): an expired seat moves to the new image through the
existing seat update, which resets its overlay. Before the reset, an operator
reads the retained files that they need through `lilrae seat rescue`. No other
migration path is added. The troubleshooting guide documents this procedure.

No affected VM was inspected. Record its immutable image, installed application
build, pack/backend identity, and sanitized failure state before claiming an
observed diagnosis or recovery. The checked-in legacy Compose tag does not
identify an installed seat. Vendor licensing rationale remains in ADR-063; this
preflight adds no new entitlement or legal determination.

## Required Contracts And Security Layers

Paths in the table are relative to `src/` unless qualified otherwise. These are
existing boundaries the design must pass, not new validators to build.

| Layer and canonical owners | Required passage for the removal design |
| --- | --- |
| Pack acquisition and identity: `aptl/core/scenario_bundle.py`, `_pack_staging.py`, env-packs `validate_pack()` / `validate_pack_content_manifest()`, `aptl/utils/pathsafe.py` | Admit the released pack through bounded, no-follow staging and its content manifest. A revised scenario requires a new version/digest qualification in `aptl_techvault/pack_identity.py`. Never edit staged SDL, rewrite hashes, widen compatibility to accept unknown bytes, or fall back to checkout assets. |
| Semantic admission and native observation: RAES parsing/runtime models, `RuntimeManager`, `aptl/backends/raes_realization_envelope.py`, implementation catalog and `raes_runtime_attestation.py` | Remove nodes, relationships, accounts, artifacts, propositions and evidence demands in the authored pack. Realize and observe that admitted meaning. Keep one RAES runtime owner. Unsupported old/new combinations fail before mutation; deleting a local collector cannot waive an old pack's demand. |
| Adapter shapes: `aptl/backends/scenario_startup.py`, `_scenario_environment.py`, `scenario_startup_policy.py`, `scenario_service_policy.py`, `scenario_capture_discovery.py`, `participant_desktop.py` | Keep reference resolution, tuple/set types, uniqueness, key bounds, forbidden Docker transport keys, script containment and declared service checks. Remove obsolete account, service, generated-output and capture references together. An account removed from SDL still named by `AccountCredentialFixture` fails startup; dangling desktop refs fail publication. Retain unrelated startup capabilities and native evidence. |
| Config and environment: `aptl/core/config.py::AptlConfig`, `_credential_sources.py::EnvironmentGrant`, `core/env.py`, deployment `_environment_bindings.py`, `_compose_environment.py`, `_realization_primitives.py::environment_file_line()` | Keep strict non-secret config and explicit pack/consumer grants, classifications, generated dependencies and byte-safe env delivery. Stop supplying removed credentials to seed, capture and MCP consumers. Ambient environment presence grants nothing. Retaining a private old `.env` for restoration does not authorize forwarding its obsolete keys. Environment-name labels detect changed bindings and may trigger container recreation; retention must cover that effect. |
| Authentication and MCP: `aptl/backends/_raes_participant_transport.py`, `aptl/core/participant_desktop.py`, `aptl/workbench/profiles.py`, common MCP config/tool validation | Remove the case-management server and its advertised tools, credentials, smoke operation and endpoint bindings consistently. Keep native authentication for remaining SOC services and exact participant environment allowlists. Do not repurpose `cases_*` as MISP/Shuffle tools. Any touched operator API still passes `api/deps.py::verify_token`, `WebAuthSettings` and `BFFMiddleware` Host/session/CSRF controls. Seat desktop access remains ADR-061's separate contract. |
| Secret transport and OS exposure: ADR-029, `aptl/utils/curl_safe.py`, repository `scripts/aptl-env.sh::aptl_curl_config()`, backend stdin execution, `core/credentials.py`, contained/private file helpers | Any retained-service or recovery command keeps secrets out of argv, URLs, shell tracing, Docker command/env dumps, logs and error text. Use protected files/stdin with cleanup. Preserve private `.env`, CA and generated credentials for retained state; do not print or bundle them into migration reports or images. No activation keys, vendor portal automation or new outbound processing are needed. |
| Runtime ownership, TLS and network: `DeploymentBackend`, admitted publications/ACLs, `techvault_native_support.py::published_url()` / generated CA resolution, `core/soc_ca.py`, seat boundary policy | Operate only on verified project-owned guest resources through the selected local/SSH backend. Remove obsolete publications and certificate consumers without rotating the shared CA or breaking MISP/Shuffle trust. Keep remaining TLS verification and VM/host containment. No host Docker socket, daemon-wide prune, extra public recovery port or TLS bypass. Changed signed image/config bytes require normal admission and qualification. |
| Evidence shape and persistence: `SourceResult`, `CollectorStatus`, `CollectorRegistration`, `CapturePlan`, evidence coordinator / `_persist.py`, `ExperimentEvidenceRecordModel`, `LocalRunStore`, TechVault `evidence/proposition_truth.py` | Remove the obsolete demand and its offer/source/interpreter only for the newly qualified contract. Remaining sources keep exact scopes, source refs, windows, requiredness, quotas, redaction and sealing. Missing/malformed/stale/unauthorized evidence cannot become `OK`, `EMPTY_OK` or true. Preserve old records, hashes, provenance and contract identity; do not reinterpret old runs under the new pack or rewrite sealed evidence. Best-effort `core/collectors.py` is not required capture. |
| Errors and observability: provider errors, RAES `Diagnostic`, `LabResult` / `StartupDiagnostic`, `SeatLauncherError`, `get_logger()`, Python/TypeScript shared `redact()` | Report bounded failure codes and safe identity/status context through existing envelopes and CLI/API/web projections. Never expose native response bodies, credentials, validation inputs, commands or raw exception text. `source-unavailable` alone does not prove license expiry. Retained MCP APIs reuse common `api-handlers.ts` validation and redacted/bounded failures; no new exception tree, log-text classifier or parallel readiness report. |
| Guest/host readiness: `aptl/core/lab.py`, repository `appliance/guest/aptl-appliance-first-boot`, `aptl/appliance/seat/readiness.py` and lifecycle | Publish readiness only after the remaining admitted native evidence and boundary checks pass. Keep fresh nonce, seat, instance, generation and descriptor checks, gateway checks and failure cleanup. A desktop, removed container or cached success marker proves no scenario readiness. No optional-evidence flag or longer timeout can repair the old contract. |

## Whole-Repository Dependencies And Reuse

The canonical service list is the acquired pack, not `docker-compose.yml`.
Within this repository, the following consumers also see the change:

- `aptl_techvault/startup.py`, `account_environment.py`, `serving.py`, `capture.py`,
  `capture_registrations.py`, `evidence/`, `participant_desktop.py`,
  `participant_smoke.py` and `build_cache.py` own qualified TechVault behavior.
  Keep their exact pack identity consistent. `CORTEX_OBSERVABLE` is also used
  by retained SQL-injection evidence and telemetry; removing its enrichment
  consumer must not break that scenario fact or the Suricata/Wazuh validators.
- Backend `_raes_backend_implementation_catalog.py`,
  `_raes_backend_generated_artifacts.py`, `_raes_image_policy.py`,
  `raes_runtime_attestation.py` and deployment account, service-index,
  credential and artifact owners carry product-specific realization facts.
  Retire obsolete facts without deleting generic account/index/secret machinery
  used by other services. A datastore image name alone does not prove exclusive
  ownership of its implementation profile or persisted data.
- Repository `scripts/seed-prime.sh`, `seed-shuffle.sh`, TheHive/Cortex scripts,
  `config/`, legacy Compose/scenarios and examples must agree with supported
  delivery. Shuffle's current workflow requires TheHive credentials even though
  the integration is disabled at first boot. Remove that dependency and its
  claims; keep Shuffle/MISP and the remaining workflow behavior truthful.
- `mcp/mcp-casemgmt`, `mcp/build-all-mcps.sh`, `.mcp.json.example`, workbench
  profiles/bookmarks, participant narratives and desktop handoff consume the
  removed capability. Core collector/CLI/kill lists also name it. Retire active
  references without deleting user-authored unrelated MCP configuration.
  Retained MCP servers continue using `mcp/aptl-mcp-common`; changing common code
  requires targeted consumer checks and CI qualification of every consumer.
- `pyproject.toml` / `uv.lock`, the image catalog and build-input closure,
  repository `scripts/appliance/`, `appliance/guest/provision-offline.sh`,
  `scan-golden.sh` and `.github/workflows/checks.yml` govern installed payloads.
  No removed server binary, credential requirement or stale image preload should
  be needed for a newly built seat. Workshop/reference docs, current feature
  claims, MkDocs navigation and smoke expectations must reflect no case tool.
  Historical ADRs, requirement records and run evidence remain historical.

Reuse these owners; do not add a second service inventory, license schema,
configuration validator, seed controller, evidence writer or migration framework.
`tools/check_pack_boundary.py` and `.gc/pack-ownership.json` remain the repository
ownership gate; no new product-name condition in generic orchestration.

## Preservation And Recovery

Preserve each existing qcow2 overlay and its immutable backing chain, guest
Docker/application data, other lab and desktop data, project `.env`, generated
credentials/CA material and run store. Inventory actual mounts and writable
container state before claiming retention. Cases/attachments, Cassandra,
Elasticsearch indexes shared by TheHive/Cortex and Cortex jobs need consistent
retention; stopping a process, recreating a container, deleting a volume and
resetting a seat have different effects. Do not use orphan cleanup as migration.

`seat stop` and failed-start cleanup retain the overlay. In contrast,
`appliance/seat/image_update.py::update_seat_image()` resets an existing seat;
`recover_seat()` also resets it. Therefore `lilrae seat update`, `seat reset`,
`seat recover`, lab `start --clean` and `stop --volumes` are not preservation
routes for #1411. A replacement signed image serves new seats; it does not
repair existing overlays. Never replace backing bytes underneath an overlay,
rewrite signed metadata, clear license databases or reseed to restart a trial.

Use existing seat/project mutation locks, ownership checks and private atomic
writes. Any agreed transition must be repeatable, detect partial completion,
retain evidence of failure and have a tested restore route. Backup bytes stay
in approved local storage and include consistent application/database state and
the backing chain. Retaining inaccessible files alone must not be advertised
as restored case-management functionality.

`appliance/seat/maintenance.py` provides a locked, stopped-overlay rescue shell,
not a running application recovery service. An expired seat cannot depend on
successful normal first boot to reach its repair route. The recovery route and
access to retained historical data remain unresolved; the removal decision
itself does not need to be reopened.
Do not add participant admin authority or declare the failed seat ready to
make recovery reachable.

## Extensibility And Qualification

The existing seam is the exact pack version/digest plus its selected startup,
capture, serving and desktop contributions. The authored contract decides
capabilities; no global `licensed`, `legacy` or `skip_cortex` switch belongs in
core. A later case-management option would be another authored release with
qualified contributions and evidence meaning, not an alias for removed tools.
If old/new support is agreed, qualify complete identity pairs and preserve
historical record readers; do not broaden independent version/digest lists into
unqualified combinations. Preservation policy must explicitly distinguish new
seat creation from transition of an existing seat.

Evidence must show new installed seats start and restart offline without a
trial-dependent service, while every remaining native requirement still fails
truthfully on missing or invalid evidence. Existing expired seats require a
separate demonstrated preservation/recovery result, with modified user data,
interruption/retry and restoration checks. Do not manipulate production clocks
or claim fresh trial boot or mocks prove durable recovery. If the old collector
is retained for compatibility, its 30 connector attempts with 30-second requests
can exceed the 300-second registration budget; all work must respect the shared
deadline, and HTTP byte bounds must apply before parsing, not only to saved JSON.

Canonical evidence includes acquired-pack fixtures (`tests/techvault_pack.py`),
TechVault startup/desktop/MCP and native-source tests, RAES admission/truth tests,
and seat persistence/readiness/lifecycle/maintenance tests. Remove obsolete
expectations, retain failure-path coverage and secret-canary checks. Legacy
Compose source-text tests alone do not qualify shipped seats.
`.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml` and
[CI verification](ci-verification.md) select targeted local tests and staged
`pre-commit run`; full suites, installed-wheel clean-lab and actual signed-image
qualification belong to CI/CD and the established image release process.
Clean-lab teardown runs only on disposable qualification state.

## Non-Goals And Implementation Boundary

This issue run investigates and records the reviewed direction. It does not
implement removal, publish an image, edit another repository, activate or buy
licenses, migrate/reset seats, introduce a replacement case product, or claim
recovery works. No trial renewal, clock manipulation, downgrade, optional
required evidence, fabricated health or automatic reduced-function fallback.
No new service, schema authority, exception hierarchy or workflow engine.
Further source changes need an agreed delivery contract covering both pack
adoption and preserved-seat recovery. No requirement UID/status, issue closure,
merge, procurement or external data transfer is authorized by this note.
