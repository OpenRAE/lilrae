# Issue #1367: Distribution Cutover Preflight

The supplied #1367 issue is the contract; no GRC workflow platform requirement is
attached. This note supplements the [parent preflight](issue-1234-pypi-transition-preflight.md),
whose cross-cutting guardrails remain applicable. It is design guidance, not
an implementation plan or evidence of publication.

## Boundary and canonical owners

Change the Python distribution to `lilrae` for the release following
`aptl-labs` 7.0.0. The issue identifies the unreleased breaking fix #1269 as
the reason that release is 8.0.0. Retain the single release-please version/tag
stream; do not manually bump versions or `CHANGELOG.md`, reset numbering, or
make a `build:` change trigger releases by inventing a functional commit.
ADR-062's successor clause is limited to distribution identity and its current
user-facing wording; it does not accept the proposed product split in ADR-054.

| Layer | Required incumbent and passage |
| --- | --- |
| Package and build shape | `pyproject.toml` owns name, Python constraint, both `src/aptl` and `src/aptl_techvault` packages, scripts, extras, and `aptl.*` entry points. Preserve these contracts apart from name. `hatch_build.py`, `_asset_manifest.py`, and `core/assets.py` remain the shared build/materialization boundary, including tracked-file selection, secret/state exclusions, sanitized Git environment, full-build marker, and no-Git sdist fallback. Container builds also consume the bundled project metadata; retain their minimal-build behavior. |
| Lock and release shape | `.pre-commit-ci.yaml` owns the pinned UV lock/export hooks and hashed `requirements/*.txt`; use the specific hooks, not the whole-tree CI configuration locally. Avoid unrelated dependency upgrades. `release-please-config.json` must select the one renamed root lock package and retain the `src/aptl/__init__.py` updater. Its `package-name: aptl` is a release component identity, not the wheel's metadata name. `.release-please-manifest.json` and `docs/releasing.md` remain version/process authorities. |
| Installed version and evidence | CLI `--version` reads `aptl.__version__`, maintained by release-please; `core/snapshot.py` reads installed distribution metadata. They must agree in an installed artifact. Keep `SoftwareVersions.aptl_version`, catch only `PackageNotFoundError` for the existing source-only `dev` fallback, and never report `dev` when `lilrae` metadata exists. No legacy-name fallback chain, new version service, or renamed snapshot field. |
| Provider shapes and reset authority | Existing `backends/*_discovery.py`, `backends/scenario_startup.py`, and `validation/scenario_verification_discovery.py` validate installed providers and retain actual metadata provenance. Keep selectors and ambiguity rejection. `startup_reset_state.py`, `lifecycle_cleanup.py`, and `_scenario_startup_runtime.py` own canonical receipt parsing, hashes, safe persistence, and exact pack/reset authorization. Preserve the closed legacy classifier and historical bytes; a renamed distribution grants no new reset authority. An unavailable legacy reset stays a bounded diagnostic under existing rules. |
| Offline guest and host OS | `appliance/versioning.py:aptl_wheel_version(prefix=...)` and `is_appliance_version()` are the existing bounded parsing seam. `build-seat-image.sh` owns application wheel/hash requirement generation; `provision-offline.sh` owns archive shape/size/type admission and hash-enforced installation. Require exactly one matching wheel and matching name/version/hash requirement; zero, duplicate, or tampered inputs fail. Keep `--no-index`, `--no-deps` for the app, separate app/dependency targets, and fixed `/opt/aptl` launchers. `aptl-wheel-requirements.txt` is a payload interface filename, not distribution metadata. Preserve base/system-package pins and seat build-record/signature/trust gates; Python publishing stays independent of seat publishing. |
| Workflow auth and shell boundary | `.github/workflows/release-please.yml` retains pinned actions, `environment: pypi`, job-scoped OIDC/attestation permissions, hashed tooling, SBOM, and attest-before-publish ordering. Bind workflow outputs through `env:` and quoted expansions, including the complete back-merge title; environment binding prevents shell-code interpolation but does not replace metadata/path validation. Keep `GH_TOKEN` in the environment, never argv, shell tracing, logs, or artifacts; add no PyPI token fallback. Account-side `lilrae` trusted-publisher authorization requires external verification under the established release process. |
| Runtime config and auth shapes | `core/config.py:AptlConfig` and its strict nested models, `core/env.py:EnvVars`/placeholder validation, startup environment-binding contracts, and `api/deps.py:WebAuthSettings`/token checks retain their current shapes. No `LILRAE_*` aliases for existing `APTL_*`, new credentials, listeners, principals, config fields, or renamed Compose resources. Existing BFF/MCP validation and auth continue unchanged. |
| Error envelopes and observability | Reuse domain errors, startup reason codes/diagnostics, typed API/MCP envelopes, `utils/logging.py:get_logger()`, and `utils/redaction.py` (ADR-029). Change recovery prose to the installable distribution without changing error types, telemetry identities, or exposing raw validator values/backend stderr. Hash or selection failures remain fatal; no broad exception-to-`dev` conversion or migration exception hierarchy. |

The extensibility seam is **distribution metadata separate from runtime
identity**. The host hash writer already reads `[project]`; derive its name and
normalized wheel prefix there, keeping filename normalization distinct from
the requirement's metadata name. Reuse the existing parser's prefix parameter
and explicit guest artifact selection. Release-please's declarative selector
must match the root metadata. No brand registry, configurable publication
destination, additional runtime config, or duplicated wheel/version parser is
needed for this single successor distribution.

## Gotchas and verification boundaries

The parent identified two existing release hazards still present in this
checkout: publish checkout follows a moving branch rather than the release
tag, and `gh pr create ... || echo` treats every back-merge failure as
"already up to date." Candidate provenance must bind to the release commit;
authentication/network failures must not count as successful workflow work.
Retain these as release review concerns, not a reason to add a second workflow.
Keep attestations outside the PyPI upload set and distinguish the new bundle
filename from stable labels such as `sbom/aptl.cdx.json`.

Reuse `test_version_consistency.py`, `test_version.py`, `test_snapshot.py`,
`test_hashed_requirements.py`, `test_hatch_build_hook.py`, `test_assets.py`,
`test_seat_image_build.py`, `test_appliance_release_workflow.py`, installed
provider/cleanup tests, and `test_docs_user_journey.py`. Existing tests do not
prove all acceptance criteria: the seat test asserts the old glob, and
`aptl_wheel_version()` currently has no repository call sites. Update current
behavior assertions and cover the parser directly; leave historical fixtures
unchanged. Require meaningful zero/multiple-wheel and hash-mismatch cases,
wheel and sdist name/version/content contracts, and installed CLI/snapshot
agreement outside checkout/PYTHONPATH masking. Asset equivalence means the same
asset set and runtime contract, not byte identity of intentionally changed
bundled metadata or messages. Reuse the clean-wheel lifecycle job in
`checks.yml`; retain minimal-container and sdist-rebuild coverage.

Current install/upgrade guidance includes README, docs home/installation,
secondary operator guides, asset recovery text, and `aptl_techvault` package
documentation. Preserve uninstall-first pip and pipx migration, pinned
rollback, extras/interpreter choice, and state. Do not advertise an unpublished
successor as verified, use `--force` to hide command collisions, or rewrite
old reviews, ADR history, evidence, and fixtures by global replacement.

Local verification uses explicit tests through `tools/run-targeted-tests.sh`
and staged-file `pre-commit run`; full tests, prose/docs gates, and clean lab
checks remain CI/CD-owned. No requirement UID, status, or traceability is
fabricated. #1234 owns post-publication clean install, migration, rollback,
CLI smoke evidence and archival. Source inspection cannot verify PyPI account
state or publication, and this preflight authorizes no external mutation.

## Non-goals

No issue implementation, package/import/CLI aliases, runtime rename, schema
or persistence migration, feature extraction, dependency overhaul, alternate
build backend, second release pipeline, publishing, archival, or data transfer.
