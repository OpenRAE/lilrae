# Scenario Authoring Boundary

Use RAES SDL to author scenarios.
LilRAE no longer gives a local scenario language or parser.
[ADR-035](../adrs/adr-035-raes-sdl-adoption.md) records that decision.

## Companion repositories

1. Use [OpenRAE/rae](https://github.com/OpenRAE/rae) for SDL schema, semantics, tools, and runtime contracts.
2. Use [OpenRAE/env-packs](https://github.com/OpenRAE/env-packs) for environment-pack structure, templates, schemas, validation, and authoring guidance.
3. Install a pack through the [pack installation guide](../getting-started/installing-packs.md).
4. Examine its acquired identity with `lilrae lab scenarios` in the approved lab environment.
5. Validate changes through [static validation](../raes/scenario-validation.md).
6. Use [live validation](../raes/live-validation.md) for deployment evidence in CI or an approved isolated VM.

These upstream links are documentation routes.
They do not authorize runtime acquisition or establish a trust root.
Deployment, lifecycle, credential, and evidence guidance for the LilRAE backend remains APTL-owned.

## Selection and limits

The configured `ScenarioSourceConfig` selects an acquired pack.
`resolve_scenario_bundle()` validates its SDL and associated artifacts.
The installed pack catalog gives operator metadata.
The RAES parser validates the selected SDL before runtime handoff.

An explicit `--scenario-path` selects a project-contained development input.
It does not replace a missing or invalid acquired pack automatically.
Use the [research fixture guide](techvault-curated-variants.md) only from a matching source checkout.

The retired local-SDL pages keep stable links for historical ADRs.
They are not alternate schema or runtime authorities.
See [runtime handoff](runtime-architecture.md) for the current relationship between admission and execution.
