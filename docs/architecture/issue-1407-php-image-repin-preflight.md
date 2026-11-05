# Issue #1407 PHP image repin preflight

This is a design boundary record for the supplied #1407 contract, inspected on
2026-10-22. It does not change pins, qualify images, or prescribe an
implementation sequence. No new ADR is needed: ADR-025, ADR-028, ADR-029,
ADR-034, ADR-048, ADR-051 and ADR-053 already own the relevant boundaries.

## Artifact and version authority

Keep this a reviewed catalog and Compose refresh using the existing registries.
The issue supplies these candidate repository identities; this preflight has
not independently inspected their manifests, platforms or packages:

| Component | Intended application | Candidate registry digest |
| --- | --- | --- |
| `ghcr.io/misp/misp-docker/misp-core` | MISP 2.5.50 | `sha256:4860a903a31f59ff6f3c95403ef705965ff3d58e3c30f4ac1b31a2d44e1d95d3` |
| `roundcube/roundcubemail` | Roundcube 1.6.20, Apache variant | `sha256:60601760a965be491bc5d3fc2da498153b85fed2d80fc903a4582ef71220e435` |

MISP's `profile_id`, exact semantic selector version and `source_version` in
`_raes_backend_implementation_catalog.py` must agree with the released pack's
MISP 2.5.50 declaration. `_raes_backend_generated_artifacts.py` dispatches cache
credential and server TLS delivery by that profile ID. A rename that loses those
artifacts is a security regression even if the new container starts.
`docker-compose.yml` must carry the same MISP repository digest. A focused
cross-file contract assertion should prevent the two authorities drifting;
do not create another pin manifest or a runtime registry resolver to unify them.

Roundcube's authored selector is `roundcube / 1`, not an OCI tag or a precise
application patch version. Preserve that supported selector in
`_lilrae_source_image_catalog.py`; change the reviewed backing distribution,
lookup provenance and digest. Do not rename the selector to `1.6.20`, invent an
alias for arbitrary patches, or add runtime mechanics to a source-only record.
The supplied digest was obtained through `1.6.x-apache`; provenance must record
the lookup actually verified, not assume that `1.6.20-apache` resolves identically.

Tags, application versions, PHP package versions, registry index/manifest
digests, Docker configuration IDs and pack-content digests are separate facts.
Pin by registry digest, corroborate the actual container image and platform,
and measure PHP independently. A pinned index must resolve to a fixed child
image on each platform being qualified; do not claim untested architectures.

The [PHP OOM advisory](https://github.com/php/php-src/security/advisories/GHSA-w8hw-w9fx-j79w)
and [stale-state advisory](https://github.com/php/php-src/security/advisories/GHSA-6wmf-4rv5-p3rp)
require patched PHP; application authentication and configuration tuning do not
replace the fix. Use branch-specific thresholds from the issue, not one global
numeric minimum. Distribution backports require package-level evidence against
both advisories, not rejection based solely on the upstream version string;
the [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-109618)
and [Ubuntu tracker](https://ubuntu.com/security/CVE-2026-109618) document such
fixed packages. The two proposed images are expected to contain PHP 8.4.27.

## Cross-cutting passage

Paths below are under `src/aptl/` unless otherwise qualified. These incumbents
remain the owners; no replacement schemas, exception hierarchy or workflow is
needed.

| Layer | Canonical incumbent and required outcome |
| --- | --- |
| Authored contract and admission | `backends/raes_image_realization.resolve_node_image`, `_raes_image_policy`, `_raes_backend_implementation_profiles` and `raes_backend_implementation` retain exact matching, unique compatible catalog selection, immutable reference syntax, provenance and OPEN authority for each selected concern. Closed/authored exact artifacts are never silently upgraded or rescued with Compose, cache or `latest` fallbacks. |
| Runtime and config shapes | RAES `RuntimeConfiguration.model_validate`, `BackendImplementationProfile`, `SemanticRuntimeSelector` and `core/deployment/realization.py` remain the typed path. Retain `value_from`, classification and provenance on environment bindings. `core/config.py`'s `AptlConfig` and `EnvironmentGrant` remain authoritative; no new image override knob, pass-through config or duplicate PHP policy schema. |
| Environment grants and transport | `core/deployment/_environment_bindings.py`, `_compose_environment.py` and `_realization_primitives.environment_file_line` validate named consumers, explicit sources and exact env-file transport before mutation. Keep `ADMIN_KEY` operator-sourced, generated `REDIS_PASSWORD` value-free in the plan, and `BASE_URL` derived from the authored setting. Do not inherit host secrets or substitute image defaults for a missing binding. |
| Generated files and persistence | `_raes_backend_generated_artifacts.py`, `core/deployment/_misp_cache_credential.py`, `_misp_server_tls.py`, `_compose_stateful_realization.py` and `core/credentials.py` retain producer contracts, contained generated paths, atomic writes, restrictive permissions, read-only consumer mounts and `reuse_valid` semantics. The existing SOC bundle remains the TLS producer. No new credential store, inventory tree or tracked runtime config. |
| Authentication, TLS and OS exposure | Preserve MISP API-key use, authored cache authorization, CA-verified external clients, loopback publication, network placement, mounts and existing privilege boundaries. Verify the replacement image still reads the delivered cert/key and cache settings. The in-container healthcheck's `-k` is not permission to disable external TLS verification. CLI/API/MCP auth contracts stay unchanged. |
| Process boundary | `DeploymentBackend` and its existing Compose/local/SSH execution paths own Docker operations. Public pins and `php -v` are safe operands; credentials must not enter shell strings, argv, `--requirepass`, curl headers or URLs. Authenticated checks reuse `utils/curl_safe.py` or existing typed clients, not inline secret-bearing commands. |
| Identity and runtime observation | `core/deployment/_docker_image_identity.py`, image realization/fetch helpers, `backends/_lilrae_catalog_image_observation.py` and `raes_runtime_attestation.py` retain independent readback and platform checks. Repository digest evidence is correlated through the actual container configuration ID; a tag, cached image name, label or `PHP_VERSION` environment value alone is insufficient. |
| Errors and observability | Reuse `backends/raes_diagnostics.py`, bounded `aptl.provisioner.image-policy-rejected` reasons, `LabResult`, `utils/logging.py` and `utils/redaction.py`. Keep validation exceptions, registry credentials, raw inspect environment, generated config and API responses out of CLI/API error envelopes, logs and telemetry. Do not add a special exception or logging path for these CVEs. |
| Evidence and archives | Preserve `core/snapshot.py`'s `RangeSnapshot.to_dict()`, `core/runstore.py`'s `LocalRunStore` redacting writes and existing source-image/reproducibility projections. Store bounded non-secret identity, platform, package/version, timestamp and outcome facts. Semantic inventory capture remains RAES-owned under the installed RAES inventory skill, not a new LilRAE capture framework. |
| Lifecycle and host ownership | `core/lab.py`, lifecycle locking/policy, `DeploymentBackend`, project ownership/inventory and `scripts/ci/assert_project_teardown.py` own startup and cleanup. Exercise the selected scenario through `aptl lab start`, then the issue-required `aptl lab stop -v` in the qualification project. Preserve the normal destructive confirmation/policy boundary; verify project-owned containers and volumes are absent, never use daemon-wide pruning. |

## Release coupling and evidence integrity

OpenRAE/env-packs#491 is a compatibility dependency, not optional follow-up.
This checkout pins `raes-env-packs==6.2.1` and `raes==6.0.1` in
`pyproject.toml`. Consume a released pack that declares the new MISP version,
with `uv.lock` and generated hashed `requirements/*.txt` kept consistent through
the existing dependency/export workflow and `tests/test_hashed_requirements.py`.
Do not patch installed packs, vendor their SDL, or rewrite old 2.5.44 declarations
inside the backend to make the new profile match. If the compatible release is
unavailable, record that blocker rather than weakening admission.

`backends/raes_runtime_attestation.py` admits exact TechVault and study pack-set
digests and exact canonical concern projections. A new pack identity or MISP
runtime version can invalidate both gates. Any refreshed attestations must be
derived from the reviewed released content with the existing canonical
projectors and corroborated runtime, including each affected pack variant.
Do not accept all pack versions, copy old projection hashes onto new content,
change historical identity records to describe new bytes, or confuse a passing
PHP probe with authority to disclose unrelated runtime concerns.

The current `tests/fixtures/lilrae_source_image_inventory_v6_3_1.json` records
released source/runtime facts with release, revision and extraction method. It
contains `roundcube / 1`, no MISP entry and neither old image digest. Do not
fabricate a fixture update merely because the issue lists it as affected.
Preserve its historical provenance; a new release capture needs its actual
release/revision and corresponding coverage expectations.

New pins also need truthful per-record provenance. MISP currently inherits
`_CATALOG_BASELINE`, an old repository revision that cannot supply the new pin.
Roundcube's `_source()` currently stamps every record `resolved:2026-10-15`.
Use the existing `provenance_refs` field for the new lookup and evidence. The
small extensibility seam is a per-record lookup date/provenance argument to the
existing `_source()` helper, retaining historical defaults for unchanged rows.
Do not restamp the whole catalog or add a second provenance schema.
`source_catalog_revision` already fingerprints changed policy via RAES canonical
JSON; retain that calculation rather than invent a manually maintained revision.

## Qualification obligations and limits

The acceptance criterion covers all LilRAE image pins containing PHP, not just
the two named components. Review catalog, Compose/overlays, Dockerfile bases and
pack-selected artifacts for other PHP-bearing images. Record inspected coverage,
fixed or not-applicable results and unresolved findings; names and source text
alone cannot prove package absence. Reuse current image-scanning/evidence paths
without building a runtime vulnerability scanner or broadly refreshing unrelated
dependencies. Additional affected pins fall under the security acceptance
criterion; unresolved evidence prevents a repository-wide clean claim.

In the running MISP and Roundcube containers, capture `php -v` and the serving
PHP implementation/package evidence: CLI PHP alone may differ from PHP-FPM or
mod_php. Correlate each probe to the selected image/platform. Check actual
application behavior as well: MISP's authenticated API, database/cache binding,
authored HTTPS identity and sync consumer; Roundcube's webmail/authentication and
declared mail/database integration where present. Healthy processes, login-page
HTTP 200s, image metadata and mocked tests do not establish these outcomes.
MISP's existing data/config/database volumes can mask entrypoint changes or
trigger application migrations. Clean disposable qualification is required;
do not claim in-place migration or rollback safety without separate evidence.

Reuse focused tests in `tests/test_raes_backend_implementation.py`,
`test_misp_redis_realization_contract.py`, `test_raes_runtime_attestation.py`,
`test_lilrae_source_image_catalog.py`, `test_docker_image_identity.py` and the
environment-binding tests. Relevant behavior includes the renamed profile's
generated artifacts, rejection of incompatible declarations, attestation refusal
on mismatched pack/projection/image identity, and Compose/catalog pin agreement.
`tests/test_supply_chain_pinning.py` checks Dockerfile inputs, not PHP patch
levels or equality of these Compose/catalog pins.

`.ground-control.yaml`, `.gc/plan-rules.md`, `tools/run-targeted-tests.sh` and
`.pre-commit-config.yaml` govern local checks: targeted tests and staged-file
`pre-commit run`; full suites and whole-tree checks belong to CI. The issue also
requires a live affected-service qualification and teardown. The current
`.github/workflows/checks.yml` clean boot uses the generic materialization
envelope, and its `trivy-image` matrix excludes upstream-only images. Green CI
alone therefore does not prove this fix; preserve measured affected-service
evidence alongside CI results. Extend incumbent verification seams if needed,
not a second lifecycle workflow or a blanket scan suppression.

## Non-goals and anti-patterns

No implementation occurs in this preflight. The eventual fix does not redesign
RAES schemas, source selection, authentication, generated credentials, storage,
network topology, controllers/DTOs or error handling. It does not introduce a
new registry/service, custom rebuilt distribution, startup-time package upgrade,
PHP configuration workaround, automatic `latest` refresh, global minimum-version
parser, or a blanket exception for deliberately vulnerable lab targets. No
external pack editing, new hosting or evidence uploads are authorized by this
note. Preserve historical evidence and do not edit generated realization output
to disguise a contract mismatch.
