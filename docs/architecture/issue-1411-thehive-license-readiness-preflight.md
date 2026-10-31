# Issue #1411: TechVault After TheHive Trial Expiry

Status: decided. The owner chose to remove TheHive and Cortex from the TechVault
SOC stack. [ADR-063](../adrs/adr-063-remove-thehive-and-cortex.md) records the
decision. This note keeps the preflight investigation and the candidates it
reviewed. It does not authorize license procurement.

## Finding And Decision For Review

The supplied observations describe a persistent entitlement failure, not a
Cortex startup failure. Source inspection supports this chain:

1. `aptl_techvault/evidence/_techvault_native_cortex.py` executes the exact
   analyzer, waits for its report, then polls TheHive `/api/v1/status`.
   Its projection returns no result without a healthy Cortex connector.
2. `CortexEnrichmentSource` in `evidence/techvault.py` maps that missing result
   to `CollectorStatus.SOURCE_UNAVAILABLE`. Its validated success payload
   requires both a fresh successful analyzer report and connector status `OK`.
3. `capture_registrations.py` explicitly offers both facts against both node
   references. `capture.py` and `evidence/proposition_truth.py` bind that offer
   to `cortex-enrichment-readback` and its exact proposition.
4. `core/lab.py::_step_acquire_required_native_evidence()` requires
   `SEALED_READY` acquisition and successful RAES evidence evaluation. Guest
   readiness publication follows these gates. The first-boot service exits on
   lab-start failure; the host receives no successful readiness response and
   eventually stops the VM through its existing failure path.

These are three separate claims: entitlement to use a feature; live service
and integration behavior; and fulfillment of the admitted scenario/evidence
contract. None proves the others. A successful Cortex job does not prove
TheHive can use Cortex. A connector health response does not prove case writes
or the complete investigation workflow. A running VM or visible desktop does
not prove scenario readiness.

Recommend preserving the full TechVault workflow and existing state through
an operator-approved, vendor-supported entitlement **only if** its terms,
duration, quotas, instance binding, and offline operation satisfy the supported
installation lifetime. Do not label an annual renewal a permanent fix. If that
condition cannot be met, the owner must agree a scenario dependency change
before implementation. There is no automatic reduced-function fallback.

| Candidate | Review condition |
| --- | --- |
| Activate an appropriate entitlement in the existing installation | Preferred for preserving the full workflow and data. Confirm permitted business/training use, all required features and quotas, per-seat/clone activation, validity period, and operation without runtime portal access. A finite entitlement needs an explicitly accepted renewal/recovery policy; otherwise it does not satisfy the issue's durability outcome. |
| Change the scenario's licensed dependency | Required alternative if a suitable durable entitlement is unavailable. Review a supported replacement or an explicitly narrower scenario, including case management, Shuffle workflows, participant tools, desktop guidance, evidence meaning, and data compatibility. Cortex-only operation cannot inherit full TechVault qualification. |

Before agreement, record which candidate is selected, its supported lifetime
and connectivity, who supplies/maintains any entitlement, and how an already
failed preserved seat is recovered without reset. Do not purchase, register,
upload an instance challenge, or contact the vendor on the user's behalf as
part of this preflight.

## Vendor Evidence And Remaining Uncertainty

Public vendor guidance checked on 2026-10-30 states:

- TheHive 5.3 and later initially receive a 14-day trial, then become read-only
  without a valid license. Cortex itself does not need a license. Licenses
  carry validity/expiration dates and user, organization, instance, Cortex,
  and MISP quotas. See [About licenses](https://docs.strangebee.com/thehive/installation/licenses/about-licenses/).
- Current [Community Edition guidance](https://strangebee.com/thehive-community-edition/)
  limits use to non-commercial settings. The vendor's
  [5.3 announcement](https://strangebee.com/blog/thehive-5-3-is-out-and-buzzing-for-even-more-efficiency/)
  describes a renewable one-year Community license. Neither source establishes
  a perpetual entitlement.
- [Activation](https://docs.strangebee.com/thehive/installation/licenses/license/)
  uses an instance challenge, the vendor portal, and a key applied to TheHive.
  This does not establish permission to redistribute an activated image or
  clone one entitlement across seats, nor prove renewal works offline.

These sources are product guidance, not the actual entitlement agreement or
proof of the affected image's behavior. No affected VM was inspected or
modified. Confirm its immutable image identity, installed TheHive build,
pack/backend identity, sanitized native license/quota state, and the failing
connector before approving a remedy. Do not infer them from the checkout's
legacy `docker-compose.yml` tag. Canonical delivery consumes the acquired pack
through `ScenarioBundle`; this checkout's adapter qualifies the exact
version/digest pair in `aptl_techvault/pack_identity.py`.

## Canonical Owners And Required Passage

Paths below are relative to `src/` unless qualified otherwise. The approved
design must pass each applicable layer; changing a local probe is insufficient.

| Layer | Existing owner and guardrail |
| --- | --- |
| Pack bytes, identity, and portable meaning | `aptl/core/scenario_bundle.py`, `_pack_staging.py`, env-packs `validate_pack()` / `validate_pack_content_manifest()`, and `aptl/utils/pathsafe.py` own acquisition and containment. RAES parsing, strict runtime models, `RuntimeManager`, `raes_realization_envelope.py`, and exact-concern observation own admission and truth. Consume the admitted artifact and declarations; do not edit staged SDL, copy topology into Python, rewrite digests, or substitute checkout assets. A changed evidence requirement needs an authored pack release and exact adapter qualification. |
| Adapter selection and startup | `aptl/backends/scenario_startup.py`, `_scenario_environment.py`, scenario service/startup policies, and `scenario_capture_discovery.py` validate compatibility, scripts, bindings, and contribution shapes. Keep TheHive-specific behavior in the qualified `aptl_techvault` adapter and existing seed owners (`scripts/seed-prime.sh`, `thehive-apikey.sh`, `cortex-apikey.sh`). Preserve core startup ordering, account realization, native evidence, and one RAES runtime owner; do not add a second boot/retry controller or a product-name branch in generic core. |
| Configuration and environment | `AptlConfig`, `EnvironmentGrant` in `aptl/core/_credential_sources.py`, `core/env.py` parsing/placeholder checks, deployment `_environment_bindings.py`, `_compose_environment.py`, and `_realization_primitives.py::environment_file_line()` own config shape and delivery. A new variable must be declared, classified, and explicitly sourced for its consumer before mutation. Respect startup seed and capture runtime key allowlists and forbidden Docker transport keys. Ambient environment presence grants nothing. Keep config as non-secret locators; do not add an untyped license/options bag, fixture license key, broad process-env forwarding, or bypass flag. Do not force a key through an env-file format that cannot carry its bytes exactly. |
| Authentication and authority | Reuse declared administrator account resolution (`aptl_techvault/account_environment.py`, `_compose_application_accounts.py`) for any approved activation operation. Native readback keeps its runtime service identity; Cortex's initializer and `read`/`analyze` connector credentials remain distinct in `_cortex_service_credentials.py`. A license is not an API credential and grants no operator authority. Add no participant activation tool or unauthenticated route. If operator API surfaces are touched, `api/deps.py::verify_token`, `WebAuthSettings`, and `api/middleware/bff.py::BFFMiddleware` retain Host/session/CSRF enforcement. Seat desktop access remains its separate ADR-061 contract. |
| Secret transport, files, and OS exposure | ADR-029, `aptl/utils/curl_safe.py`, `scripts/aptl-env.sh::aptl_curl_config()`, backend stdin execution, `core/credentials.py`, and contained file helpers own secret-safe transport/storage. Treat license keys and activation material as operator-private data. Keep bytes out of host/guest argv, URLs, shell tracing, Docker command/env dumps, logs, evidence, and errors. Use protected files/stdin and cleanup, not `curl -H <token>`, `docker exec -e NAME=value`, or shell evaluation. Never generate a substitute for a vendor-issued key or embed one in pack content, wheels, golden disks, or CI artifacts. |
| Network, TLS, and resource ownership | `published_url()` and generated CA resolution in `techvault_native_support.py`, SOC CA configuration, `DeploymentBackend`, admitted publications/ACLs, and appliance boundary policy own endpoints and effects. Retain TheHive CA verification and the admitted Cortex transport. Resolve the selected owned guest resource; no daemon-wide repair, host Docker socket, new public port, arbitrary URL, TLS bypass, or automatic vendor egress. Local and SSH transports share backend operations. Operator-mediated activation must respect the offline seat contract and approved data-transfer boundary. |
| Evidence validation and persistence | Reuse `CortexEnrichmentSource`, its payload validators, `SourceResult`, `CollectorRegistration`/capture matching, `CapturePlan`, `CollectorStatus`, the evidence coordinator and `_persist.py`, `ExperimentEvidenceRecordModel`, and `LocalRunStore`. Preserve time windows, limits, source references, requiredness, redaction, checksum/sealing, and proposition matching. Missing, malformed, stale, unauthorized, or unavailable sources must not become `OK`, `EMPTY_OK`, or true evidence. Do not use best-effort `core/collectors.py` to satisfy required capture. |
| Diagnostics and observation | Reuse `curl_safe.curl_request()` / `CurlOutcome` when transport/HTTP distinctions are needed, existing provider errors, RAES `Diagnostic`, `LabResult`/`StartupDiagnostic`, `SeatLauncherError`, `get_logger()`, and `redact()`. Preserve the collector failure and add only bounded, observed reason context through existing envelopes. Distinguish entitlement missing/expired/quota-denied from auth rejection, TLS, transport, malformed status, analyzer failure, and transient connector refresh. Unknown state stays unknown. Never infer licensing from every connector failure or leak HTTP bodies, validation inputs, commands, or exception text. Normalize sensitive native failures before core's broad exception logging. Keep API/CLI/web projections aligned; no new exception hierarchy or log-text classification. |
| Guest/host readiness and image trust | `core/lab.py`, `appliance/guest/aptl-appliance-first-boot`, `appliance/seat/readiness.py`, lifecycle, boundary gates, and signed image/config selection own readiness. Keep fresh nonce/seat/instance/generation/descriptor checks and normal access revocation. A license diagnostic must not bypass required evidence or become a forged/stale guest readiness response. CI image qualification and `appliance/guest/scan-golden.sh` remain release boundaries. A fresh trial boot is insufficient evidence of durability. |

## Preservation And Recovery Boundaries

Preserve the outer qcow2 overlay and its retained immutable backing image,
guest Docker data, application state, and project `.env`/generated credentials,
CA material, and run/evidence store. Relevant SOC storage includes TheHive
case/attachment data, Cassandra, indexes, and Cortex jobs; shared Elasticsearch
also serves Cortex. Preserve other lab and desktop data, not just TheHive files.
Inventory the actual admitted mounts before claiming retention. Application
process restart, container recreation, Compose teardown, and seat reset have
different persistence effects; unmounted container state can be lost.

`seat stop` and failed-start cleanup retain the overlay.
`appliance/seat/image_update.py::update_seat_image()` calls reset for an existing
seat. Therefore `lilrae seat update`, `seat reset`, `seat recover`, lab
`start --clean`, and `stop --volumes` are not recovery defaults for this issue.
Do not replace backing images underneath existing overlays, rewrite signed
metadata, clear license databases, rotate working identities, or reseed cases
to restart a trial. Reinstallation, clock manipulation, and downgrading to an
older release to evade expiry are outside the supported approach.

Use existing seat/project mutation locks, owner checks, private atomic writes,
and vendor-native persistence. Do not create a parallel entitlement ledger or
cached healthy marker. Repeated recovery must preserve the current valid
entitlement and data; an interrupted or uncertain activation needs native
readback before retry. Backups must cover consistent application/database state
and the retained backing chain, stay in approved storage, and have a verified
restore route. A new image cannot repair old overlays by itself.

The existing `appliance/seat/maintenance.py` rescue route is an offline shell
for a stopped overlay. It does not supply a running TheHive activation UI/API.
Any candidate must demonstrate a controlled administrator recovery route for
the already-failed seat without publishing it as ready, weakening participant
privileges, or depending on the normal successful boot it is trying to restore.
This remains an agreement condition, not a claim of existing online recovery.

## Extensibility, Verification, And Non-Goals

The seam is the existing exact-qualified startup/capture adapter plus admitted
service/integration identity and operator-selected credential source. Bind
checks to the selected connector and required capabilities/quotas, not a tier
name or global `licensed` boolean. A second permitted connector or a changed
entitlement must not require editing portable content to insert a customer
key. License keys/state remain instance-local; genuine authored workflow
changes still require a new pack identity and qualification. Reuse narrow
typed extensions to the existing context only when an approved design needs
information it currently lacks.

Current probe limitations matter to that design. `connector_projection()`
searches nested mappings for an `OK` Cortex context; do not treat an arbitrary
subtree or another connector as proof for the selected integration. Native
HTTP currently collapses many failures to `None`, so `source-unavailable` alone
cannot diagnose licensing. Also, 30 connector attempts with 30-second requests
plus sleeps can exceed the registration's 300-second budget. The owner must
respect the existing capture deadline across all operations. Longer host
timeouts and repeated analyzer jobs cannot repair deterministic license denial.
Enforce response byte/structure bounds as well as saved-payload limits;
post-parse `bounded()` checks alone do not bound an HTTP download.
Keep startup-generated analyzer/seed activity distinct from participant work.

Qualification must distinguish valid supported entitlement, expired/missing
entitlement, insufficient quotas, healthy standalone Cortex with a denied
connector, temporary connector refresh, and unrelated auth/TLS/transport or
malformed responses. It must prove truthful outcomes, bounded work, secret
canaries, repeated/interrupted recovery, preserved modified lab data, and
unchanged containment. Exercise a preserved seat beyond the real trial boundary
and offline restart, rather than changing a production clock or claiming mocks
prove expiry behavior. Any finite entitlement also needs evidence of the
agreed renewal/expiry behavior.

Canonical focused tests include `tests/test_techvault_evidence_sources.py`,
`test_techvault_native_evidence.py`, `test_raes_native_evidence_truth.py`,
`test_raes_evidence_acquisition.py`, and seat readiness/lifecycle/maintenance
tests. Use acquired-pack fixtures (`tests/techvault_pack.py`) for canonical
content; legacy Compose source-text tests alone do not qualify delivered seats.
`.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`, and
`docs/architecture/ci-verification.md` govern checks: targeted local tests and
staged `pre-commit run`; installed-lab, full-suite, and image qualification in
CI/CD. Compose/Dockerfile/`config/` changes select the existing clean-lab gate
on disposable test state, never on a preserved user's seat.

Non-goals are implementing or deploying a remedy; buying or activating a
license; vendor account automation; resetting or upgrading installations;
changing scenario meaning or evidence requiredness without agreement; a new
license service, schema authority, validator, exception tree, or workflow
engine; and broader SOC hardening or replacement. No requirement/status links,
issue closure, release claim, or change to accepted ADRs follows from this note.
