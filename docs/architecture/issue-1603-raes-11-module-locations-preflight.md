# Issue #1603: Released RAES dependency adoption

The maintainer selected RAES 10.6.0 and environment packs 7.2.2.
These releases replace the originally anticipated RAES 11 target.
Both releases are published on PyPI.
The [design](issue-1603-released-module-design.md) describes the release contract and data flow.

## Repository assessment

The integration branch now includes the #1017 migration.
It already imports the relocated public RAES symbols.
It also uses the upstream `ExperimentArtifactParent` validation wrapper.
Do not repeat those changes or add compatibility imports.
The remaining change restores dependency floors and qualifies the 7.2.2 pack identities.

The existing release policy keeps major-version ranges in project metadata.
The lock and hashed requirements exports hold the exact qualified versions.
Use the configured `uv-lock` and `uv-export` arguments.
Do not add an index, VCS dependency, editable upstream source, or manual hash.
The structural adapter fixture must accept the same release set.

## Security and architecture boundaries

- Reuse pack validation, manifest checks, and contained staging in `core/scenario_bundle.py`.
- Keep upstream typed contracts, canonical digests, parsing, and admission checks.
- Preserve participant authorization and exact pack/backend provider selection.
- Reuse `DeploymentBackend` for effects and the native readback interfaces for observations.
- Keep credential environment grants, private files, bounded process controls, and redaction.
- Preserve canonical storage identities and immutable archive seals in `LocalRunStore`.
- Follow [ADR-064](../adrs/adr-064-layered-architecture-and-code-conventions.md) for dependency directions.
- Follow [ADR-066](../adrs/adr-066-runtime-readback-reports-realized-state.md) for observed runtime state.

Do not restore the removed planning, ordering, or content-attestation bridge.
Do not add local schema, digest, or validator substitutes.
Package versions, pack content identities, and runtime observations remain separate facts.

## Verification boundaries

The namespace test resolves upstream modules and symbols in source, tests, and tools.
It includes deferred annotations and function-local imports.
Pack tests qualify both published TechVault identities and reject altered identities.
Existing participant, experiment, evidence, and archive tests cover the affected consumers.
CI owns full suites, installed artifacts, Sonar, and installed-lab qualification.
No new service, data destination, host permission, or architecture layer is needed.
