# Issue #1242: Workspace capture harvest boundary

Architecture guidance for issue #1242; not an implementation plan. The issue
body and acceptance criteria remain the delivery contract. This note clarifies
how ADR-041/042 capture custody fits the receipt-based ownership boundary from
issue #964 and the current backend. It does not change ADR status.

## Decision

The maintainer did not adopt the receipt and native-ID binding below. The
harvest keeps the workspace-scoped name that lab start derives from the
ownership record. Docker names are unique on one daemon. Only a principal with
daemon access can create a container with that name. That access already
permits direct changes to the capture volume and the run evidence, so a
native-ID binding adds no protection against it. A replacement container with
the same name belongs to the same workspace, and the run-scoped copy path
records `aptl.capture-harvest.session-missing` for a stale session.

The delivered changes are these:

- The harvest copies only from a declared capture sidecar. It never falls back
  to the workload container.
- The mcp-red configuration names the sidecar only through
  `LILRAE_MCP_CAPTURE_CONTAINER`. An unresolved or invalid name records
  `aptl.capture-harvest.container-unresolved` and runs no `docker cp`.
- The harvest permission pass does not follow symbolic links.

The sections below record the original preflight guidance.

## Current state and material gaps

The inspected branch already contains `kali_capture_container()` in
`src/aptl/core/mcp_ingress.py`, the `LILRAE_MCP_CAPTURE_CONTAINER` binding,
its red-only TypeScript config override, and
`capture-harvest-failure.json` records. Build on these; do not implement a
second resolver or failure format. The binding currently derives an external
name from `WorkspaceOwnership.load()` and `container_name()`. It does not
verify a resource receipt or bind the subsequent copy to that native object.

`mcp/aptl-mcp-common/tests/captures.test.ts` includes recorded Docker responses
from a created, never-started scratch container and a filesystem copy fixture.
Those are useful regression fixtures, not proof of a live Kali session harvested
through the actual launch path. This preflight does not run a lab or establish
the issue's live acceptance criterion.

The config audit finds fixed container fields in red (`aptl-kali`,
`aptl-kali-capture`) and reverse (`aptl-reverse`). The other six shipped
`mcp/*/docker-lab-config.json` files use HTTP APIs. The reverse field is not
merely display text: `resolveCaptureContainer()` falls back to `container_name`
for SSH targets. Determine whether that target actually supports captures;
do not assign Kali's sidecar to it or call an unresolved expected capture a
successful no-op. HTTP service URLs and SSH host/port bindings are separate
contracts, not container-name aliases to replace wholesale.

## Decisions and reuse

- **Python deployment owns resource identity.** Reuse `WorkspaceOwnership`,
  `ResourceReceipt`, `ComposeResourceResolutionMixin`, and the public
  `ContainerOpsBackend.container_inspect()` boundary. Names and labels narrow
  discovery; neither grants permission to read evidence. Resolve the semantic
  capture selector against receipts for the selected workspace/project/daemon,
  verify the native object, and perform copy against its full native ID. Reject
  absent, conflicting, ambiguous, or unverifiable ownership without copying
  another candidate. Do not translate the workspace naming algorithm or parse
  receipt files independently in TypeScript. Loading for observation must not
  manufacture missing ownership state.
- **Keep the existing management-to-MCP binding.** `mcp_ingress.py`,
  `lab.py`'s config sync, `GuestAdmission.launch()`, and
  `_raes_participant_transport.py` are the incumbent producers and filters.
  Carry only the verified target and the necessary daemon binding across this
  seam. Make any change from a name to a native-ID value explicit in the existing
  config contract, validation, and tests; do not quietly redefine a public field
  or add an alias. A precomputed name alone is not completion of this boundary.
  Revalidate authority before use and bind the target to the session's admitted
  run so replacement or a later lab start cannot redirect an old session.
- **Keep one per-session harvester.** `captures.ts` owns copy and its durable
  outcome; `tools/handlers.ts` owns MCP result envelopes, with
  `tools/timeout-harvest.ts` preserving timeout/remote-close ordering. Resolution
  failure must reach the evidence-writing boundary even if no copy is attempted.
  Preserve `harvest_warning`, command results, and session cleanup. Best-effort
  delivery does not mean successful capture, and does not relax required
  capture admission or finalization.
- **Keep evidence concepts distinct.** `runs.ts` and `LocalRunStore` own run and
  session paths. The current broker produces `frames.jsonl` and `metadata.json`;
  it does not produce the historical global audit/process-accounting harvest.
  Session copy is not the full-run transcript export. Reuse
  `_raes_transcript_export.py` for quiesce/census/export reconciliation and the
  existing archival boundary for completeness and sealing. Do not infer a valid
  transcript from an existing directory, a zero exit code, or a failure record.

## Cross-cutting gates

| Layer and canonical owner | Required boundary |
| --- | --- |
| Runtime authority: `_compose_resource_ownership.py`, `_compose_resource_resolution.py`, `_docker_endpoint_binding.py` | Verify the receipt/native ID and the selected daemon, including replacement races. Keep workspace ID, effective Compose project, backend attempt, semantic container selector, run ID, and session ID distinct. Labels alone and first-match Docker discovery are insufficient. |
| Auth and access: `workbench/guest_binding.py`, workbench role profiles and credential broker | Preserve `GuestAdmission.authorize()`, caller/role/server grants, current deployment binding, private management files, and per-server locks. The target comes from management state, never a tool argument, forwarded SSH environment, or participant-authored value. No new API, endpoint, token, or Docker socket mount in Kali. |
| Config parsing: `aptl/core/config.py`, common `config.ts`, `_compose_capture_config.py` | Preserve strict `AptlConfig` shapes; runtime identity needs no durable user option. Use the canonical capture selector and existing `LabConfig` field. `JSON.parse(...) as LabConfig` is not full runtime validation. Validate the effective target for all accepted sources, including static config and direct harvest callers, without a second inconsistent grammar. The current env-only regex is syntax checking, not authorization. |
| Environment transport: `lab.py`, `mcp_ingress.py`, `_raes_participant_transport.py`, `GuestAdmission._service_environment()` | `APTL_HP_*` carries decimal ports only; never place a container ID/name there. Preserve the red-only runtime allowlist, credential aliases, `APTL_MCP_DISABLE_DOTENV`, and generated config privacy. Guest launch explicitly supplies `DOCKER_HOST`; host participant filtering currently does not admit that key. A custom daemon binding must traverse the appropriate trusted filter without forwarding ambient environment wholesale. Keep existing names under ADR-062. |
| Host execution: common `captures.ts`, backend Docker endpoint binding | Retain absolute `/usr/bin/docker` or a trusted absolute override and argument arrays, never shell interpolation or PATH fallback. Keep target/source root out of participant control; validate delimiters/option-like values. Copy must use the daemon verified by the producer, not an ambient Docker context. Currently `HarvestOptions.env` selects the binary but is not passed as `spawn`'s environment. Do not mistake it for endpoint binding. Bound subprocess lifetime and diagnostic buffering using existing timeout conventions and measured margins; failures must settle cleanup. Put no credentials in argv. |
| Evidence paths: common `runs.ts`, `runstore.py`, `utils/pathsafe.py` | Preserve the OBS-003 ID contract (safe characters and no `..`), explicit session-bound run, admitted run-store base, and standalone `_unbound` meaning. Keep directories 0700 and files 0600 from creation. Validate parents and reject symlink escapes; `wx` protects only the final file, and recursive `chmod` can follow a copied link. The current TypeScript writer does not inherit Python's descriptor-relative containment or finalization lock merely by sharing its layout. |
| Failures and redaction: common `captures.ts`, `tools/handlers.ts`, `redaction.ts`; Python deployment errors, `LabResult`, `StartupDiagnostic`, `capture_diagnostic()` | Extend the existing bounded harvest outcome, not an exception hierarchy or parallel evidence schema. Preserve missing-container, missing-session, and copy/transport failure distinctions; ownership uncertainty is not confirmed absence. Write the named failure in the intended run/session evidence even when resolution fails. Persist no raw Docker stderr, inspect document, environment, credentials, or transcript. Redact/bound operator diagnostics too; raw stderr logging is an existing exposure to address on the touched path. If persistence fails, return failure and retain an operator-visible warning; never claim durable evidence was written. |
| Finalization: `_raes_transcript_export.py`, `LocalRunStore.finalization_lock()`, `core/archival/seal.py` | Finish or reject late harvest before the archive seal; a separate pre-write seal check is not atomic exclusion. Preserve expected-session census and broker reconciliation. Retry/duplicate close must not overwrite another session or erase a previous failure silently. A capture failure artifact is diagnostic evidence, not evidence that required capture succeeded. |

## Whole-repository surface and extensibility

The affected surface includes the eight shipped MCP configs and
`.mcp.json.example`; generated private `.mcp.json`; native lab startup;
guest management and host participant profile rendering; common config,
SSH/session lifecycle, harvest and redaction modules; Python deployment
ownership and Docker endpoint binding; run storage and archival consumers;
`docker-compose.capture.yml` and `containers/kali-capture/broker.py`; and
the local Docker executable, socket/context, filesystem and process lifecycle.
`tools/check_pack_boundary.py` governs edits to pack-facing config. Do not
move pack-owned facts into generic core while repairing runtime resolution.

The extension seam belongs at the existing backend-to-MCP runtime binding:
an admitted semantic capture source resolves to a verified native target on a
bound daemon for a run/session. The copy boundary already accepts a target,
capture root and run ID. Keep these explicit trusted inputs so a second
capture-capable SSH target or a non-default local daemon does not require
forking the harvester. Do not introduce a generic discovery registry or a new
provider framework for this issue. A guest-side target stays guest-side;
an outer host must not copy from its own Docker daemon using a guest name.

## Gotchas and proof obligations

- Managed MCP startup with a missing/stale binding must not silently use
  `aptl-kali-capture`, guess a workspace prefix, select the only running match,
  or fall back to the workload. `container_name` fallback is not proof that a
  target implements capture. API-only absence is different from failed resolution.
- Config sync is conditional and catches errors as capability warnings;
  prove the binding on the actual startup route. Existing MCP processes do not
  reload rewritten `.mcp.json`. Preserve session/run identity across restart,
  trace rotation, one-shot execution, timeout, close-one and close-all.
- Test foreign same-name/same-label objects, two workspaces, wrong daemon,
  missing/corrupt receipt, ambiguous candidates, replacement after resolution,
  invalid bindings, denied copy, missing source, unsafe paths, duplicate close,
  and evidence-write failure. Use the existing ownership, native ingress,
  guest binding/management, participant delivery, common config/harvest/handler,
  transcript export and broker tests rather than another test harness.
- Live acceptance requires a real broker session through the supported MCP
  launch route, its finalized session artifacts in the configured run archive,
  and a named missing-container failure in that same evidence layout. Record
  only bounded local provenance and outcomes, not secrets or payload logs.
  A Docker error fixture or seeded host file does not satisfy this criterion.
- Follow `.ground-control.yaml` and `.gc/plan-rules.md`: targeted Python/Vitest
  tests and staged `pre-commit run` locally. CI rebuilds all common-library
  consumers; Compose/container/config changes also require the clean-lab gate.
  No fabricated requirement UID or requirement status transition is needed.

## Non-goals

No issue implementation in this preflight. No new service, database, discovery
schema, auth flow, exception tree, capture format, run layout, or workflow
engine. No naming migration, scenario/RAES schema changes, broader MCP config
rewrite, auditd restoration, SIEM forwarding, weakened capture isolation, or
mounting evidence into Kali. Do not turn this fix into a general archive or
deployment rewrite; use their existing boundaries and surface any unresolved
integration gap rather than claiming the new path satisfies them.
