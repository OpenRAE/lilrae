# Issue #1422: Wazuh Dashboard Config Readability Preflight

The supplied issue is the contract; no GRC workflow platform requirement is attached.
The fix belongs to the artifact-delivery path used by the failing run. Preserve
the dashboard's non-root execution and the admitted configuration. Existing
ADRs 025, 028, 029, 031, 034, 037, and 051 cover the boundaries; no new ADR,
permission framework, or configuration schema is needed.

## Current Evidence and Decision Boundary

This checkout already addresses two causes of unreadable bind-mounted files:

- `core/credentials.py` renders dashboard `wazuh.yml` atomically as `0644`
  inside `0700` host directories, verifies POSIX modes, and rejects generated
  symlink chains. This is ADR-028's deliberate container-readability exception.
- `deployment/_compose_content_mounts.py` explicitly sets non-sensitive inline
  and pack files to `0644`, independent of the boot process's umask. Sensitive
  files remain `0600`; executable artifacts and extracted directories have
  their own mode rules. `tests/test_env_pack_realization.py` already covers
  these distinctions under umask `077`.

The issue supplies no failing pathname, image identity, or run diagnostics.
An `EACCES` report alone does not establish which of those paths failed or
whether the deployed build includes these protections. Do not repeat an
existing chmod fix without identifying the failed read, effective process
UID/GID, source artifact, resulting mount, and modes/ownership of the file and
its **container-visible** ancestors. Record metadata and a bounded failure
reason, never config bodies, environment dumps, or private keys. Distinguish
POSIX access failure from ACL/SELinux denial, Docker file sharing, and a wrong
source type; do not disable a security control to distinguish them.

Keep these config identities separate:

| Consumer path | Existing authority and delivery |
| --- | --- |
| `/usr/share/wazuh-dashboard/config/opensearch_dashboards.yml` | Dashboard server/OpenSearch configuration. The repository baseline is `config/wazuh_dashboard/opensearch_dashboards.yml`; a realized pack supplies its own declared content. |
| `/usr/share/wazuh-dashboard/data/wazuh/config/wazuh.yml` | Wazuh plugin's manager API connection configuration. The repository renderer is `sync_dashboard_config()` with canonical output `RENDERED_DASHBOARD_RELPATH`; a pack's declared placement has its own provenance. |
| `/usr/share/wazuh-dashboard/certs/*` | Certificate artifacts owned by `core/certs.py`, typed stateful realization, and their certificate validators. Config readability does not authorize certificate rotation or a new trust policy. |

`docker-compose.yml` documents the older dotted service and overlapping plugin
file/named-volume mounts. It is not the canonical input for scenario startup:
`base_compose_file()` generates the base model from the admitted realization.
The dashboard implementation profile and digest-pinned image live in
`backends/_raes_backend_implementation_catalog.py`. Editing only the root
Compose file or the checked-in template cannot repair pack-owned delivery.

## Required Cross-Cutting Passage

| Layer and canonical incumbents | Required design behavior |
| --- | --- |
| Pack integrity and content shape: `core/scenario_bundle.py`, `_pack_staging.py`, `backends/raes_content_realization.py`, `_raes_content_spec.py`, `DeploymentContentRealization`, and env-packs `resolve_pack_artifact()` | Keep the admitted identity, digest, destination, source kind, and sensitivity. Preserve source/destination containment, output symlink refusal, archive filtering, and member checks. Read pristine pack bytes from `scenario_root`; stage generated content under `realization_root`. Do not rewrite pack bytes, weaken digest checks, or substitute checkout files. |
| Artifact permissions: `core/credentials.py::{_render_secure,_canonical_generated_path,_ensure_secure_dir,_enforce_mode}`, `_compose_content_mounts.py::{_pack_content_mode,_declared_ownership,_ownership_spec}`, and `tests/test_owned_content_install.py` | Repair the actual producer/consumer contract. Public config must be readable by the image's actual reader without making it writable. Retain sensitive `0600` policy and ADR-028's narrowly scoped `0644`/`0700` generated-config exception. A new secret-bearing write must be protected from its first byte and fail on unenforceable required permissions. `_atomic_write_secure()` finishes at `0644`; its name does not make it a general `0600` secret writer. |
| Runtime selection and effective model: `_raes_backend_implementation_catalog.py`, `_compose_node_generation.py`, `_compose_runtime_config.py::{compose_literal,compose_readback}`, `_compose_model_realization.py`, `runtime_materialization.py::effective_runtime_contract_issues()`, and `_runtime_materialization_effective.py` | Carry only admitted runtime selections. Preserve literal `$` handling and pre-start `config --no-interpolate` model validation. Entry-point, mount, group, capability, namespace, and security-option changes must satisfy the existing authority checks and RAES observation/disclosure; a hand-edited generated override is not a contract change. Do not add a dashboard service definition in `_compose_stateful_services.py`. |
| Durable config and environment: strict `AptlConfig`, `core/env.py`, `_environment_bindings.py`, `_realization_primitives.py::environment_file_line()`, and `_compose_environment.py::write_sourced_environment()` | No new user setting is needed for deterministic file readability. Keep dotenv parsing, required/placeholder checks, explicit pack/node/variable grants or qualified adapter sources, and env-file shape validation. Do not copy credentials into generated YAML or satisfy value-less bindings from ambient environment names. Keep sourced env files owner-only. |
| OS/runtime and deployment: `DeploymentBackend`, its shared runner, resource ownership checks, and `core/hostenv.py` | Verify the consumer's effective identity, not merely the image's configured user or the host owner. Keep host UID, container UID, file mode, mount access, and parent traversal distinct. Use backend-scoped inspection/execution, bounded timeouts, and metadata-only probes. Reuse Docker-mode classification for platform-specific behavior; do not assume Docker Desktop or a remote daemon sees local POSIX paths and modes. Preserve existing unsupported-remote refusals. |
| Authentication, transport, and secrets: API `WebAuthSettings`/`verify_token`, `BFFMiddleware`, ADR-029, `utils/curl_safe.py`, and `utils/redaction.py` | This repair adds no auth route or grant. Preserve operator bearer/session/Host/CSRF gates, dashboard/indexer/manager credentials, loopback publications, and TLS trust. Any verification using credentials must use existing safe transport or stdin/file delivery, never secrets in host/guest argv or shell text. Config, expanded Compose, inspect, and log output can contain secrets; do not forward them wholesale. |
| Lifecycle, errors, evidence: `core/lab.py`, `_compose_realization.py`, `_compose_service_health.py`, `_compose_stateful_readiness.py`, `LabResult`, `StartupDiagnostic`, `LabActionResponse`, `get_logger()`, shared `redact()`, and `LocalRunStore` | Keep rendering/model validation before startup and required readiness fail-closed. A required dashboard config read failure is fatal, not a cosmetic warning. Use existing results and diagnostics with safe stage/path/mode/error-class metadata. `get_logger()` does not automatically redact message bodies or tracebacks. Redact before CLI/API/log/trace/persistence boundaries; retain artifact identities/digests rather than config bytes. Add no exception hierarchy, workflow, or evidence ledger. |

## Guardrails and Extensibility

- A single-file bind exposes that file without exposing its host parent tree;
  ADR-028's `0700` host parent therefore does not require widening for the
  container. A directory bind instead exposes its descendants, whose directory
  traversal modes matter. Docker's ability to mount a path does not prove the
  application can read it. A read-only mount does not grant read permission.
- Preserve the generic content mode seam `_pack_content_mode(sensitive,
  executable=...)`. Consumer-specific ownership belongs in the existing typed
  `runtime.filesystem_inventory` path/owner/group/mode and selected backend
  implementation profile, consumed by `_declared_ownership()`. The manager
  already uses `OWNED_CONTENT_INSTALLER`; the dashboard profile does not.
  Copying that root-capable installer into a non-root profile does not establish
  that it can execute. A sensitive non-root delivery need must retain its
  classification and use a qualified existing ownership/delivery seam; it must
  not globally turn sensitive content into `0644` or run the dashboard as root.
- Preserve image-owned sibling files when placing directory artifacts. Preserve
  declared writable plugin state separately from immutable content. Confirm
  the pinned image's entrypoint behavior before changing mount writability;
  blanket read-only mounts can break an entrypoint that rewrites its config.
- Regeneration must converge from restrictive stale modes without mutating
  source assets or foreign-owned files. Atomic replacement changes the inode;
  an existing single-file bind can retain the old one. Let the established
  lifecycle recreate/rebind as needed; do not use an in-container chmod as the
  durable fix or delete named volumes to make verification pass.
- Avoid `chmod -R`, `0777`, host/root helper repairs, global umask changes,
  hardcoded dashboard UID assumptions, blanket ACL/SELinux bypasses, added
  capabilities, image upgrades, and raw Docker calls beside the backend. Do
  not replace a typed runtime/ownership contract with a filename or node-name
  allowlist. Keep the next image version or another non-root config consumer
  expressible through the same existing metadata and profile boundaries.

## Evidence Required of the Implementation

Focused tests must retain existing public/sensitive/executable mode, umask,
containment, symlink, digest, directory-merge, and owner-installation contracts.
Extend the relevant incumbent tests for the demonstrated failure; a host
`stat()` or mocked process alone does not prove container readability.

Acceptance needs the effective dashboard mounts and a successful config read
by the pinned image's real reader, plus dashboard startup/UI readiness and a
repeat start with retained state. Manager/indexer authenticated readiness
does not prove dashboard readiness. Exercise the affected host/runtime path,
including restrictive boot umask and host/container UID differences. A live
trial may proceed only through the normal successful realization path; do not
add a retry loop or lengthen timeouts to mask deterministic `EACCES`.

Reuse `tests/test_credentials.py`, `tests/test_env_pack_realization.py`,
`tests/test_owned_content_install.py`, stateful/model/observation tests, and the
existing live dashboard smoke surface as applicable. Run targeted local tests
through `tools/run-targeted-tests.sh` and staged `pre-commit run`. CI owns full
suites and clean lifecycle validation. The generic installed-wheel boot gate
uses `materialization-envelope`, so its success alone does not exercise Wazuh;
dashboard-specific runtime evidence remains necessary. Preserve asset exclusions
in `.gitignore`, `_asset_manifest.py`, `hatch_build.py`, and `core/assets.py` if
delivery assets change; generated secrets must never enter the wheel.

## Non-Goals and Boundaries

No runtime code is changed by this preflight. The implementation is limited to
restoring dashboard config readability and proving the affected delivery path.
It does not redesign RAES schemas, environment binding, auth, TLS, certificate
ownership/rotation, persistence/reset semantics, remote deployment, general
permissions recovery, startup outcome taxonomy, or live-trial orchestration.
No dependency/image change, new service, public exposure, data upload, or
change to unrelated failures is implied by this issue.
