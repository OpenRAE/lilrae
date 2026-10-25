# Issue #1413 Configured Pack Source Preflight

This note guides [issue #1413](https://github.com/OpenRAE/lilrae/issues/1413),
which blocks #1220. It records design boundaries, not an implementation plan or
implemented support. The issue is the delivery contract; no Ground Control
requirement is attached. The inspected baseline is `d7a5328e`.

## Source selection decision

Extend `ScenarioSourceConfig` with one explicit, non-secret pack-directory
locator for `source: env-pack`. The initial configured source is an
already-present release directory beneath the operator's project. Acquisition
means staging and validating those bytes; the issue specifies no remote
transport, registry, or installer. Absence of the locator preserves installed
`raes_env_packs` resources as the default. A configured source that is missing
or invalid must fail, never fall back to that default.

The locator names the directory containing `pack.yaml`, its manifest, and
`sdl/<identity>.sdl.yaml`, not an SDL file or a parent directory to scan. It is
relative to the project owning `aptl.json`, independent of process working
directory. Reject an empty, absolute, traversing, control-character-bearing,
ambiguous, or symlinked path, and URL/credential/command forms. Do not expand
environment variables or `~`. Reject overlap
between the source and staging trees in either direction before copying.

This operational locator belongs only to strict first-party configuration.
It is not pack identity, publisher authentication, a catalog, an adapter, or a
portable RAES field. `scenario.root` keeps its project-tree development meaning;
do not repurpose it. Reject the new locator with `source: project-tree` and
reject ambiguous combinations with `root`. Preserve the existing explicit,
contained `--scenario-path` development override and exclusive CLI selectors.

The implementation seam already exists:

`ScenarioSourceConfig -> resolve_scenario_bundle() -> env_pack_bundle(source_pack=...) -> ScenarioBundle`

`env_pack_bundle()` also has a `package` argument, but exposing an arbitrary
Python import name in config would add code execution during resource lookup.
Do not use that as the third-party data-source interface. Another installed
distribution or offline release can later supply a directory at this same
resolver boundary without changing downstream consumers. Do not introduce a
source plugin registry, speculative provider union, or another bundle type.

## One admission and distinct authorities

Both default and configured packs remain `ScenarioSourceKind.ENV_PACK`. Source
location changes no realization or privilege decision. Reuse `ScenarioBundle`
and the upstream-validated `PackIdentity(pack_id, pack_version, set_digest)`;
never infer identity from a directory, distribution version, SDL hash, or config
claim. Env-packs owns layout, manifest, inventory, and digests; RAES owns SDL
parsing, instantiation, compilation, planning, and evidence admission.

All catalog, CLI, API, and startup callers must reach the same resolver.
`ScenarioCatalog` projects the configured pack through
`raes_env_packs.catalog.build_catalog`; it does not enumerate directories or
every installed pack. Keep its existing one-entry contract and DTOs.
`AdmittedScenarioStart` retains one bundle and one admitted execution through
apply, retry, observation, and evidence. No reacquisition on retry or mutation
of staged content to make a pack compatible.

Content location and executable adapters stay separate. Reuse exact
pack/version/digest/backend compatibility and installed entry-point discovery
in `pack_interaction_discovery`, startup, runtime-parameter, capture, planning,
and verifier seams. Installed Python is trusted executable code. A pack cannot
install or import an adapter from its contents. Preserve each seam's existing
absence behavior; no TechVault fallback or automatic semantic-verification pass.

These decisions apply ADR-025, ADR-029, ADR-047, and ADR-053 and the
[#880](issue-880-techvault-env-pack-consumption-preflight.md),
[#951](issue-951-fresh-env-pack-start-preflight.md), and
[#980](issue-980-pack-adapter-install-seam-preflight.md) boundaries. They supply
the public source-selection decision deliberately deferred by
[#985](issue-985-owned-lab-fixture-preflight.md). Historical references to a
future identity-only selector do not prohibit a bounded operational locator;
they still prohibit using location as semantic identity or authority.

## Required cross-cutting passage

These are obligations for the intended design, not claims that all current
call sites already satisfy them.

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Config: `core/config.py`, `AptlConfig`, `ScenarioSourceConfig`, `load_config`, CLI `_common.resolve_config_for_cli` | Keep `extra="forbid"`, typed fields, canonical identity validation, and centralized source/field compatibility checks. Shape validation must work without network, copying, or importing a selected package. Do not duplicate config parsing in CLI/API/backends. `config show` dumps the model, so the locator must contain no credentials. |
| Filesystem ingress: `utils/pathsafe.py`, `core/_pack_staging.py`, `scenario_bundle.env_pack_bundle` | Reuse descriptor-relative no-follow traversal and bounded `copy_pack`: 4,096 members, 1 GiB, depth 64 at this baseline. Validate the original path before normalization hides dot/empty components. Share any needed lexical policy through the existing path owner rather than cloning a path parser. Preserve private, separate per-invocation staging, ordinary-file checks, installer-hardlink-to-private-copy behavior, bytecode-only exclusions, and removal of failed acquisitions. |
| Pack validation and later reads: `_validate_staged_pack`, `_refuse_pack_compose_model`, `raes_env_packs` public gates | Run `validate_pack` and `validate_pack_content_manifest` on the staged copy, preserve upstream limits, and require the selected SDL. Reject a root `docker-compose.yml`. Do not regenerate a manifest to bless invalid bytes. Later artifacts use `resolve_pack_artifact` and bundle-contained readers with digest verification; no reads from the original source after admission. |
| RAES admission: `raes.admit_raes_scenario`, `_raes_admission_helpers`, artifact availability, manifest and realization validators | Reuse parser/instantiator, import-lock, compiler/planner, capture and capability gates, runtime parameters, and typed realization. Valid pack bytes do not prove that their requirements can be realized. Keep bundle input, operator project, and backend realization roots separate. |
| Operator secrets and env shapes: `core/env.py`, `_credential_sources.py`, `_scenario_environment.py`, `deployment/_environment_bindings.py` | Operator `.env` stays project-owned. Pack-local `.env` is never config, interpolation input, or a credential source. Preserve placeholder/name/uniqueness checks, pack/consumer/variable-scoped `EnvironmentGrant`, declared value classifications, generated-output bindings, single-line env-file validation, private delivery, and startup denial of `DOCKER_TRANSPORT_KEYS`. No ambient environment forwarding or new secret schema. |
| Content and effective deployment: `raes_content_source_policy`, `DeploymentRealizationSpec`, stateful/service policies and Compose validation | Preserve forbidden-source policy independently of authored sensitivity, exact artifact/output/consumer joins, least-privilege mounts, crypto validation, port/host binding policy, and readback. The source locator cannot authorize a host mount, Docker socket, privilege, or root Compose fragment. Keep SSH Compose's `supports_local_artifacts=False`; a local source is not remote staging support. |
| HTTP authority: `api/main.py`, `api/deps.py`, BFF/session middleware, scenario/lab routers | Existing `verify_token`, validated `WebAuthSettings`, Host/Origin/CSRF/session gates, and server-owned project selection remain in force. No source-install/upload endpoint or request-controlled host path. Scenario list/detail remain bounded projections using `api/schemas.py`, not raw config or pack manifests. |
| Host/OS execution: `DeploymentBackend`, existing subprocess and secret transports | Directory acquisition needs no subprocess or network. Do not add pip, git, curl, archive pipelines, `shell=True`, or host execution of pack scripts. Subsequent admitted execution retains fixed commands and validated arguments; secret material goes through existing stdin/private-file transports, never argv. `utils/curl_safe.py` remains the incumbent for credential-bearing curl calls if separately needed. |
| Errors and observability: `EnvPackError`, `PathContainmentError.reason`, RAES diagnostics, `_raes_start_failure`, `LabResult`, `get_logger`, `utils/redaction.py` | Translate expected lookup/copy/validation failures at the acquisition boundary to bounded `EnvPackError` messages, including failures before the current staging `try` block. Preserve catalog `ValueError` translation, CLI nonzero failure, detail API 404/502, and list API's existing empty-list degradation. An empty list is not admission success. Use safe identities, phase/outcome, counts and timing; no raw parser/Pydantic inputs, absolute paths, payloads, env, subprocess output, or exception chains in public output. Redaction alone does not remove paths. Add no exception/result/logging hierarchy. |
| Persistence and provenance: `ScenarioBundle.details`, `raes_repro.RunRecordInputs`, `LocalRunStore`, provenance `safe_config_projection`, startup/reset receipts | Record the admitted pack version/set digest separately from adapter provenance and image identity. Reuse existing redaction and contained/atomic persistence. Keep source/staging paths and generated/secret bytes out of run identity, snapshots, traces and API DTOs. Do not widen the safe config allowlist to a whole-model dump or add a pack database/cache ledger. |
| Packaging and delivery: `_asset_manifest.py`, `hatch_build.py`, `core/assets.py`, lockfiles, appliance input/qualification owners | Do not overlay site-packages, alter `sys.path`, vendor third-party release bytes, or add them to product asset roots or generic Docker build contexts. Preserve pinned contract-library dependencies and existing offline closure checks. Source selection does not certify an appliance profile or install images/adapters; delivery must consume the same verified bundle when it supports that source. |

## Concrete gotchas and workflow boundaries

- `_pack_staging.copy_pack` already rejects source symlinks/special files and
  bounds work before manifest trust. Do not resurrect historical `copytree`
  advice or replace checked handles with `resolve()`/prefix-check/reopen logic.
  The staging destination still uses path-based `mkdir` and cleanup in
  `scenario_bundle.py`; before exposing configured directories, ensure
  `.aptl/staged-packs`, invocation parents, and deletion remain contained and
  owned even with pre-existing or swapped symlinks. Ignored state is not a
  filesystem security gate. Extend `pathsafe` where needed.
- A source containing its output can recursively ingest the copy. Reject
  source/staging overlap before work, including reserved runtime-state inputs.
  Never sweep another invocation's staging by age. Read-only catalogs clean up
  their own copies; runtime inputs survive for their consumers' lifetime.
- A new config validator's fixed message is insufficient if callers print
  Pydantic's rejected input alongside it. `_common._load_config_or_exit` currently
  prints `str(exc)`; new locator failures must reach CLI/API/log boundaries as
  bounded, input-free diagnostics. Reuse `redact` and `is_secret_shaped_value`
  rather than inventing another credential detector. Do not sanitize a locator
  into a different executable path or treat redaction as validation.
- `tools/check_pack_boundary.py` imports every installed adapter and calls
  `env_pack_bundle(staging, pack_id)` with the default package for every owner.
  A separately sourced pack therefore needs attention beyond startup. Keep this
  canonical check and its pre-commit hook; give its required owner packs explicit
  source resolution through the same seam, without silently skipping unresolved
  claims, loading pack code, or assuming the one active catalog covers all owners.
  Preserve its value-free findings and `tests/test_pack_boundary_policy.py`.
- `docs/getting-started/installing-packs.md` previously implied installing any
  third-party distribution made its bytes selectable. That is unsupported at
  this baseline. Delivery documentation must show the actual release-directory
  layout, source selection, separate adapter installation, and failure behavior.
  Never describe metadata integrity as publisher authenticity: a self-consistent
  manifest is not an independent signature or approval to execute a pack.
  A directory is also not a release pin: record the observed version/digest,
  and compare any identity required by an existing profile or policy against
  the validated `PackIdentity`. Do not add implicit `latest` resolution.

Reuse `tests/fixture_pack.py` and the real owned pack in
`tests/fixtures/packs/materialization-envelope` for generic tests. Existing
`test_scenario_source_config.py`, `test_scenario_bundle.py`,
`test_scenario_catalog.py`, `test_api_scenarios.py`, and CLI tests cover the
relevant seams. Delivery evidence must exercise configured third-party bytes
through normal config/catalog/admission without patching resource lookup or
upstream validators, demonstrate independence from `raes_env_packs` content,
and cover invalid inputs, corruption, overlap, symlinks, concurrency, cleanup,
and safe diagnostics. Preserve released-TechVault compatibility and adapter
qualification tests separately; a fixture pass cannot replace them.

Follow `.ground-control.yaml`, `.gc/plan-rules.md`, `docs/CODING_STANDARDS.md`,
`tools/run-targeted-tests.sh`, and staged `pre-commit run`. Full tests, coverage,
prose, builds, installed-wheel and clean-lab qualification belong to existing
CI/CD gates in `.github/workflows/checks.yml`. Keep `aptl` import roots, existing
config names and entry-point groups; new identifiers follow ADR-062 and commands
use `lilrae`. A requirement-free issue needs no invented requirement UID or
status transition.

## Non-goals

No remote download, archive extraction, package installation, signing/trust
service, multi-pack catalog, new portable schema, source plugin framework,
adapter redesign, semantic verifier, dependency upgrade, rename migration,
remote-host transfer, or appliance-profile expansion. The next acquisition
variation belongs behind `resolve_scenario_bundle` and its existing
`source_pack` directory parameter, with an explicit transport/trust decision;
realization, content consumers, catalog DTOs and adapter selectors stay unaware
of the transport. Evaluate the existing `appliance/download.py` transport before
adding a downloader; its appliance cache/error contracts and seat-image signing
policy are not automatically pack contracts. This preflight changes guidance
only and does not unblock #1220 or claim #1413 delivered.
