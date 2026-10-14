# Issue #1234: PyPI Distribution Transition Preflight

Issue #1234 is the authoritative contract; there is no formal requirement.
This note constrains design before implementation. It changes no packaging,
version, release, account configuration, or runtime behavior.

## Decision Boundary

Deliver the existing complete project as `lilrae` after a final `aptl-labs`
release. Keep `aptl`, `aptl_techvault`, both current commands, every `aptl.*`
entry-point group, extras, dependencies, bundled assets, and runtime identities.
The distribution metadata name changes; the executable namespace does not.
New installed-provider provenance must truthfully say `lilrae`; retained records
continue to say whichever distribution actually produced them.

[ADR-062](../adrs/adr-062-lilrae-name-and-naming-convention.md) and the
[#1232 preflight](issue-1232-lilrae-naming-preflight.md) describe the currently
retained distribution. Implementation must record a narrow successor decision
for that clause and coordinate the README/install notice with #1232, without
accepting proposed [ADR-054](../adrs/adr-054-lilrae-core-and-experience-ownership.md).
#1229 remains the migration record. Reconcile #1215 by identifying this issue
as the concrete distribution cutover; extraction and feature separation stay
deferred. A renamed wheel is not evidence of a smaller or separated product.

## Release And Installation Invariants

The final legacy artifact must contain its own prominent README notice, new
repository and PyPI links, migration instructions, and rollback guidance.
`pyproject.toml` publishes `README.md`; changing the repository README later
does not change an uploaded artifact. Do not advertise the replacement as
available before it is verified. The legacy release must be published before
the name switch reaches a release candidate. Never build two distribution
identities from one candidate or maintain two active release pipelines.

`docs/releasing.md`, `.release-please-manifest.json`, and
`release-please-config.json` own version selection and the single `vX.Y.Z`
tag stream. Retain that stream across the name change: use the computed next
legacy version and a subsequent replacement version, without resetting to
`1.0.0` or duplicating a tag. Exact versions belong to reviewed release
candidates, not this note. The issue's `build:` title does not trigger a
release under current policy; release eligibility must be resolved through
the existing Conventional Commit/release-please process. Do not hand-edit
versions or `CHANGELOG.md`, or fake a functional change to force a release.

Both distributions own the same import files and scripts. Supported migration
removes the old installation before installing the new one in the same
environment; rollback removes the new installation before reinstalling a
pinned legacy version. A direct `pip install -U lilrae` over `aptl-labs` is
unsafe. Installing both then uninstalling either can remove shared files.
Do not use a redirect/metapackage, automatic uninstall hook, or dependency
from one distribution to the other.

Document pip virtual-environment and pipx migration separately, preserving
selected extras, interpreter choice (Python 3.12+), and existing project state.
pipx isolates package environments but its exposed commands still collide;
remove the old pipx installation before exposing the new commands. Resolve
PATH/stale launchers and use the intended interpreter for metadata checks.
Do not repair collisions with `--force`, privileged/system Python installs,
or deletion of `.aptl`, `aptl.json`, keys, runs, or lab volumes. An isolated
replacement can be verified before switching the user's command exposure.

## Canonical Owners And Required Passage

| Layer | Incumbent and guardrail |
| --- | --- |
| Packaging shape and compatibility | `pyproject.toml` owns the distribution name, scripts, extras, entry points, Python constraint, and Hatch package list. Preserve both packaged import trees and dependency constraints. Validate wheel METADATA, entry points, contents and sdist metadata; do not rename imports, provider selectors, or CLI registration. |
| Bundled assets and secret exclusion | `hatch_build.py`, `src/aptl/_asset_manifest.py`, and `core/assets.py` share the dependency-free asset manifest, full-build marker, editable/minimal-container boundaries, git-location environment stripping, and sdist walk exclusions. Reuse these; no second manifest, new glob over local state, or secret-store reads. Prove the sdist rebuild still bundles the same assets without `.git`. |
| Dependency and version consistency | `uv.lock`, `.pre-commit-ci.yaml` UV lock/export hooks, and `requirements/*.txt` own hash-pinned closures. Regenerate through their existing tooling; do not hand-edit exports or broadly upgrade dependencies. Update release-please's legacy-name TOML selector with the metadata name and preserve its `src/aptl/__init__.py` version annotation. `tests/test_version_consistency.py` and `test_hashed_requirements.py` already guard these relationships. |
| Runtime metadata and extension validation | `core/snapshot.py` currently calls `version("aptl-labs")`; the replacement must report its installed version rather than silently become `dev`. Keep the existing `SoftwareVersions.aptl_version` field. `backends/scenario_startup.py`, the other discovery modules, and `validation/scenario_verification_discovery.py` already derive provenance from installed metadata and reject malformed/ambiguous providers. Preserve their contracts and rejection; never pick the first of duplicate registrations or relabel provenance as legacy. |
| Persistence and cleanup authorization | `core/startup_reset_state.py`, `core/lifecycle_cleanup.py`, and `backends/_scenario_startup_runtime.py` own canonical, hashed, no-follow cleanup records and reset authority. Keep the closed legacy `aptl-labs` receipt classifier unchanged. Persisted pack resets require exact installed provenance or an explicitly supported reset action version, plus exact pack identity. Existing declarations must be assessed; a rename grants no reset authority. Exercise old pending receipts after migration; do not rewrite historical bytes, widen authority, or create a name-alias registry. |
| PyPI authorization | The existing `publish` job in `.github/workflows/release-please.yml` owns `environment: pypi`, job-scoped `id-token: write`, pinned actions, and OIDC publication. Both projects require the exact publisher tuple `OpenRAE` / `lilrae` / `release-please.yml` / `pypi`. Verify actual project ownership and environment protections; source YAML does not prove account configuration. Correct the obsolete `Brad-Edwards` / `aptl` instructions in `docs/releasing.md`. No long-lived PyPI token fallback or permission broadening. |
| Supply chain and publication errors | Preserve hashed tooling, no-isolation builds, locked-runtime SBOM generation, attest-before-publish ordering, and release attachment. The current bundle filename contains `aptl-labs`; distinguish distribution-derived filenames from stable labels such as `sbom/aptl.cdx.json`. Require exactly one expected wheel and sdist, agreeing on name/version, in the upload set. Keep attestation/SBOM files out of the PyPI package set. Fail on disagreement, authentication failure, or partial publication; never silently skip an existing artifact or infer PyPI success from a GitHub tag. |
| Host and offline consumers | `scripts/appliance/build-seat-image.sh` hardcodes `aptl_labs` wheel selection and a legacy hash requirement; `appliance/guest/provision-offline.sh` hardcodes the same glob. Preserve exactly one selection, hashes, offline `--no-index`, separate app/dependency targets, and fixed `aptl` launchers. `appliance/versioning.py:aptl_wheel_version()` already has a prefix parameter; reuse the seam and bounded version validation rather than invent a parser. Seat publication remains independent of Python release cuts. |
| Config, environment shapes, and runtime auth | `core/config.py:AptlConfig`, `core/env.py:EnvVars`, placeholder/config validators, generated configuration owners, `api/deps.py:WebAuthSettings`/`verify_token`, and BFF/session/MCP security gates retain their current names and shapes. The distribution name is not an env prefix, Compose project name, credential source, backend selector, or auth principal. No config migration, alias fields, new listener, or policy bypass. |
| OS exposure, errors, and observability | ADR-029, `utils/redaction.py`, `utils/logging.py:get_logger()`, domain errors, `LabResult`/`StartupDiagnostic`, typed API responses, and common MCP handlers remain canonical. Keep credential values out of argv, logs and evidence; use existing environment bindings for credentials and quoted shell arguments for validated metadata. Preserve bounded reason codes and error envelopes, with no raw validator input or backend stderr leakage. Keep logger/telemetry identities; add no migration exception tree or telemetry service. |
| Documentation and quality workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`, `.pre-commit-ci.yaml`, `.github/workflows/checks.yml`, and `mkdocs.yml` remain authoritative. Update current installation examples and recovery messages, including `core/assets.py`, without rewriting historical fixtures/evidence. Reuse documentation journey, version, supply chain, assets, snapshot, lifecycle-cleanup, installed-verifier, and seat-build tests. No requirement UID/status/traceability is fabricated for this issue. |

The extensibility seam is distribution metadata, separate from executable and
persisted identity. Derive artifact selection and hash requirement names from
validated project/wheel metadata; pass a normalized prefix at existing parser
boundaries. Release-please's declarative selector must match the same name.
Do not introduce a runtime brand toggle, configurable publisher destination,
global naming registry, or compatibility matrix for two active installations.

## Evidence And External State

Existing installed-artifact tests and the clean-wheel lifecycle job in
`checks.yml` are the precedents. Verification must run outside checkout import
paths and without editable installs/PYTHONPATH masking missing wheel content.
Published wheel and sdist evidence must identify name, version, source commit,
hashes, interpreter and dependency closure. Exercise both import roots, both
commands safely, provider discovery, bundled-asset initialization, clean
installation, uninstall-first migration, rollback, and absence of legacy
metadata/duplicate providers. Do not run mutating service commands as help
smokes. Sdist presence on PyPI is not proof it installs correctly.

Keep candidate manual QA in `docs/testing/smoke-test-plan.md` and
`docs/releasing.md`; publishing currently rebuilds artifacts, so candidate
evidence cannot claim published byte identity. Post-publication verification
is separately required for both releases. Bind the publish build to the
release tag/commit rather than a moving branch checkout, and verify that
artifact metadata agrees with that release. Bind workflow values through
environment variables before quoted shell use, including back-merge titles;
do not extend the existing direct tag interpolation in the back-merge script.
Full suites, strict MkDocs, Vale,
and clean lab gates remain CI/CD-owned; local tests use explicit paths through
`tools/run-targeted-tests.sh` and staged-file `pre-commit run`.

An existing project uses a [registered trusted publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/);
an uncreated project can use a [pending publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
which does not reserve its name. This inspection does not establish current
PyPI ownership, publisher configuration, name availability, or release status.
Archive only after both required publications and replacement verification
succeed. [PyPI archival](https://blog.pypi.org/posts/2025-01-30-archival/)
retains installable historical artifacts and blocks new uploads; it is not
deletion or yanking. Record the transition evidence before archival. Failed
replacement publication leaves legacy available and unarchived; recovery uses
the existing release process, not overwritten artifacts or deleted history.

## Non-Goals

No repository-wide rename, second import namespace/CLI, feature removal,
adapter extraction, service/controller/DTO/schema refactor, data migration,
runtime resource rename, new packaging backend, alternate release pipeline,
dependency overhaul, or rewrite of historical records. This preflight performs
no release merge, account mutation, upload, publication, archival, or external
data transfer.
