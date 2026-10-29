# Issue #1402: Command Rename Preflight

The supplied [issue #1402](https://github.com/OpenRAE/lilrae/issues/1402) is the
delivery contract; no GRC requirement is attached. This note records
design guardrails, not an implementation plan or evidence of working releases.
The [distribution preflight](issue-1367-distribution-cutover-preflight.md)
continues to govern packaging and release security.

## Command boundary and compatibility policy

The primary commands are `lilrae` and `lilrae-misp-suricata-sync`. Retain `aptl`
and `aptl-misp-suricata-sync` as compatibility entry points to their respective
existing implementations. There is one Typer app in `cli/main.py` and one sync
service in `services/misp_suricata_sync/main.py`. A compatibility launcher may
emit a notice and delegate; it must not reproduce commands, parse their options,
spawn the replacement through a shell, or change exit/signal behavior.

Emit one fixed deprecation notice to stderr per legacy executable invocation,
including eager help/version and invalid usage. Emit it at the entry boundary,
before Typer parsing, without import-time side effects, Python warning filters,
logging configuration, or process-global "already warned" state. A root callback
alone misses eager exits. Do not infer legacy invocation from the Typer app's
name or an embedding process's `sys.argv`. Canonical help and version branding
is `lilrae` for both CLI names; version remains `aptl.__version__`, maintained by
release-please. Library imports and direct app use have no legacy notice unless
they deliberately enter the compatibility launcher.

Use `LILRAE_SUPPRESS_APTL_DEPRECATION=1` to suppress only these legacy-launcher
notices. Other values leave the notice enabled. This is a new, process-local
presentation control, not a credential, config field, dotenv hydration entry,
or alias for an existing `APTL_*` variable. No new settings model or general
boolean-parser framework is needed. Notice text contains the replacement and
removal release, never argv, paths, environment values, or caught exceptions.
Keep replacement/removal metadata together at the launcher boundary; the two
legacy executables need no independent deprecation frameworks.

**Recommended removal target: 10.0.0**, retaining aliases through 8.x and 9.x.
This is a proposed release policy for the delivery ADR, not a claim that a
removal issue exists or that a release has shipped. Before #1402 is complete,
its ADR must reference a real, separate removal issue with this target (or an
explicitly selected replacement target). No removal issue was supplied to this
preflight. Do not fabricate its number, and do not silently substitute the
next major release. The delivery filed
[#1403](https://github.com/OpenRAE/lilrae/issues/1403) with the 10.0.0 target.
Removal must include generated-artifact migration, not just script deletion.

ADR-062 needs a narrowly scoped command successor clause, as #1367 added for
distribution identity. Preserve its historical statements and supersede only
the command/help/recovery wording affected here. The CLI name does not rename
the `aptl` import root, `aptl.*` plugin groups, `aptl.json` or its fields,
existing `APTL_*` variables, `.aptl`, Compose project/resources, RAES backend
identity `aptl`, schema IDs, protocol selectors, managed-entry markers, auth
identifiers, run records, evidence, release component, or quality-gate keys.
In particular, an executable path stored in an `aptl_executable` field can point
to `lilrae`; that field does not become a new serialized `lilrae_executable`.

Adding the commands is a `feat:` release. Removing aliases requires a separate
later major release. `docs/releasing.md`, `.gc/plan-rules.md`, release-please
configuration and its manifest remain authoritative: no manual version bump or
feature-branch CHANGELOG edit. Put the explicit removal target in the releasing
commit's changelog input (the squash PR title is the established entry source),
and verify that the generated CHANGELOG names it before release. A PR-body-only
notice does not establish that acceptance criterion. Current planning rules
that say to retain the `aptl` CLI need the same narrow successor reference;
their prohibitions on renaming other existing interfaces still apply.

## Cross-cutting passage and canonical owners

| Layer and incumbents | Required design passage |
| --- | --- |
| Packaging and assets: `pyproject.toml`, `hatch_build.py`, `_asset_manifest.py`, `core/assets.py` | The installed distribution stays `lilrae`; script metadata exposes both primary and legacy names. Retain packages, extras, plugin groups, bundled-asset selection and secret/state exclusions. Do not create an alias distribution/import package, second app, alternate build path, or install-time PATH repair. Script metadata changes are not dependency upgrades. Preserve lock/export consistency under `.pre-commit-ci.yaml`. |
| CLI controllers and results: `cli/main.py`, `cli/_common.py`, `cli/{doctor,lab,lifecycle}.py`, `core/lab.py` | All names reach the same handlers and orchestration/confirmation/lifecycle guards. Reuse `emit_json_result`, `JSON_SCHEMA_VERSION`, exit codes 0/1/2, config resolvers and existing exception translation. JSON `command` values such as `lab start` remain executable-independent. Legacy stdout must equal primary stdout for equivalent input, including JSON failures; notice is stderr only. Do not add a deprecation field, change error envelopes, or bypass `--yes`/JSON prompt refusal. |
| Config and environment: `core/config.py:AptlConfig`, `validate_compose_project_name`, `core/env.py:EnvVars`, `backends/raes_stateful_realization.py`, deployment `_compose_stateful_realization.py` | Existing strict nested models, env-name/value/placeholder checks and generated-artifact output/consumer/delivery validation remain authoritative. The command spelling changes neither admitted config nor realized environment contracts. Keep suppression local to launchers; no new lab-env alias, duplicate validator, schema, state root or persistence migration. |
| Web auth and exposure: `cli/web.py`, `api/deps.py:WebAuthSettings`, `api/session.py`, `api/middleware/bff.py`, `web/Dockerfile.api` | A renamed executable must still enter `web serve`, which sets the existing per-process secret environment and single-worker contract. Preserve token/placeholder validation, constant-time bearer checks, session cookie/header/domain labels, Host/Origin/CSRF/WebSocket gates and listener policy. Do not replace the container command with raw uvicorn. No new auth surface or token-in-argv channel. |
| Guest SSH admission: `workbench/preparation.py:TransportPreparation`, `dispatch.py:restricted_key`/`_policy_path`, `guest_binding.py:GuestAdmission`, `cli/mcp_access.py` | Supply the managed absolute executable path through the existing `aptl_executable` seam. Keep strict request shapes, safe literal path validation and `shlex.join`; a `lilrae` path passes without relaxing the allowlist. Preserve `aptl-mcp-v1` selectors, restricted key options, generation/role/grant/host-pin admission, per-call revocation and bounded cleanup. Never use arbitrary PATH or user input as a new execution authority. MCP stdout remains protocol-only even through a legacy launcher. |
| Client config and persistence: `workbench/access_clients.py`, `client_files.py`, `appliance/seat/access_clients.py`, `utils/pathsafe.py`, existing atomic writers | Native host configs launch pinned SSH, not the CLI. Preserve their command/args shapes, server IDs, management markers, private modes, no-follow containment, managed-entry ownership, concurrent-edit detection and generation rules. Update owned generated artifacts through their owners; never bulk-edit private state or overwrite manual entries. A command rename grants no permission to rotate keys, replace instances, or rewrite historical bindings. |
| Offline supply chain and OS: `scripts/appliance/build-seat-image.sh`, `appliance/guest/provision-offline.sh`, first-boot/scan/qualification scripts, seat image trust and release validators | The offline installer separately creates `/usr/local/bin` launchers around `/opt/aptl/app/bin` scripts; pip metadata alone cannot migrate them. Keep separate dependency/app targets, hash-enforced no-index installation, archive admission, fixed interpreter/PYTHONPATH, quoted argv and `exec`. Preserve guest users, directories, systemd restrictions, boundary/signature/qualification gates and non-root container users. New artifacts expose both names; compatibility launchers must retain legacy invocation identity so notices are not lost. |
| Errors, logs and evidence: existing `LabResult`/startup diagnostics, `WorkbenchConfigurationError`, seat errors, typed API/MCP envelopes, `utils/logging.py`, `utils/redaction.py` | Reuse existing failure mappings, redaction and logger/telemetry identities (ADR-029). The notice is a deterministic stderr presentation event, not a new logging service or exception hierarchy. Change actionable recovery prose only; do not expose raw Pydantic inputs, backend stderr, service credentials or binding contents. Keep run/evidence schemas and historical bytes. |
| Sync daemon: `services/misp_suricata_sync/{main,config}.py`, `containers/misp-suricata-sync/Dockerfile` | Both service names enter the same `main()`, preserving integer exit status, strict env parsing, placeholder/TLS validation, logging, retries and SIGTERM/SIGINT handling. Keep the Compose service/container identity, rule volumes, reload socket and IOC tags. Migrating the ENTRYPOINT must not rename any of those contracts. |

The extensibility seam is **executable identity separate from runtime identity**:
entry points select only compatibility presentation; the existing transport
parameter selects the trusted executable. Changing a future removal target or
adding another approved client must not require editing domain models, RAES
adapters or protocol schemas. Do not introduce a brand registry, runtime name
toggle, executable discovery framework, new DTO/repository, or lifecycle engine.

## Whole-repository consumers and upgrade gotchas

The generated-artifact inventory must distinguish owners from their outputs:

- `appliance/access_service.py` currently resolves `shutil.which("aptl")` and
  falls back to `/usr/local/bin/aptl`; `preparation.py` embeds that value in guest
  `authorized_keys`. Prefer the new managed launcher for newly generated policy.
  Existing policy remains usable through the retained alias. Host `.mcp.json`
  and `.codex/config.toml` continue to invoke SSH; their IDs and selectors stay.
- Offline provisioning writes main and sync launchers; first boot, golden-image
  scan and seat qualification invoke the old main path. New images must agree
  on launchers and calls. Already signed images retain their bytes and aliases;
  migrate by the existing image replacement/enrollment lifecycle, not in-place
  signature bypass or rewriting grants. Before removal, regenerate owned guest
  policy and upgrade/replace affected images; document any version-pinned legacy
  image behavior explicitly.
- `web/Dockerfile.api` and the sync Dockerfile invoke executables. Compose's
  `aptl-misp-suricata-sync` container name is a different identity and stays.
  `scripts/aptl-range.service` invokes `scripts/provision-range.sh`; check the
  called script as well as unit text. Qualification's existing `APTL_SEAT_CLI`
  override stays, with its default following the new executable.
- Active provisioning, continuity and active-response test scripts, seed tools,
  `.github/workflows/checks.yml` clean-wheel lifecycle, shell completion output,
  current validation/recovery messages and web/API help may carry executable
  instructions. Migrate active calls or explicitly retain them under alias
  coverage. Process matching such as `pkill -f 'aptl lab start'` must be reviewed
  with the invoked command; never broaden it into a generic process killer.
- README, docs home, getting-started, current reference/troubleshooting/operator
  guides and release/manual-QA instructions need consistent examples and a
  migration section. Include script changes, the exact suppression setting,
  removal behavior (old commands cease to be installed), completion regeneration,
  and recovery from stale PATH/pipx exposure. Verify clean `pipx install lilrae`
  exposes all intended scripts; do not use `--force` to hide collisions or
  recommend installing legacy and successor distributions together.

Do not globally replace `aptl`: imports, config filenames, container names,
auth identifiers and protocol selectors occur beside user-facing commands.
Accepted ADR history, closed reviews, requirement history, dated workshop
captures (`tools/workshop/arsenal-2026/*.txt`), recorded QA and evidence remain
unchanged. Current templates/procedures are distinct from captured outputs.

## Verification contracts and non-goals

Reuse `tests/test_cli.py` for CLI behavior/JSON/exit contracts,
`test_version{,_consistency}.py`, `test_lab_init_cli.py`,
`test_docs_user_journey.py` (its reference parser hardcodes `aptl `),
`test_mcp_access{,_cli,_clients}.py`, `test_appliance_access_service.py` and
`test_seat_image_build.py`. Direct `CliRunner.invoke(app, ...)` does not exercise
installed console-script wrappers. Require real installed entry-point coverage
for both names, help/eager version, usage/config failures, exactly one notice,
silencing, repeated invocations in one interpreter, exit parity and separate
stdout/stderr JSON assertions. Exercise both sync launchers without starting
an uncontrolled live daemon.

Reuse built-artifact test conventions and the clean-wheel lifecycle job in
`checks.yml`: exercise `lilrae` outside checkout/PYTHONPATH masking, retain
explicit legacy-alias proof, and verify packaged script metadata, offline
launcher paths and guest forced-command generation. Include unavailable primary
executable handling under the documented compatibility policy; never silently
select a different interpreter or arbitrary executable. A mocked `which()` or
help-only source test cannot prove pipx exposure or post-upgrade MCP access.
Dockerfile/config/Compose changes require focused local contracts and CI's clean
lab gate. Actual seat qualification and publication remain separate release
gates; static shell assertions cannot establish a working signed image.

Local implementation checks use explicit affected test paths through
`tools/run-targeted-tests.sh` and `pre-commit run` on staged changes. Full suites,
coverage, whole-tree lint/prose and clean lifecycle gates remain CI-owned. This
documentation-only preflight needs file hygiene, not runtime suites, and claims
no CI result. Do not invent requirement UIDs or traceability for this run.

Non-goals: issue implementation, alias removal now, runtime/schema/config/auth
renames, storage or evidence migration, package split, service redesign,
dependency overhaul, release-pipeline duplication, historical rewrites,
publishing, image rebuilding, external issue creation or data transfer.
