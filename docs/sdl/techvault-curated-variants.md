# APTL Research Scenario Fixtures

Use this How-to guide to change a reduced research fixture from a matching source checkout.
The [fixture reference](curated-variant-reference.md) owns the current matrix and selection limits.

## Authorities

Read the [source owner table](curated-variant-reference.md#source-owners).
Change the existing owner for the selected surface.
Keep explicit participant-profile path and digest bindings.

## Guardrails

1. Keep the fixture small enough to prove one intended realization.
2. Reuse existing node names, service aliases, networks, and runtime profile hints.
3. State what the fixture includes, omits, and proves.
4. Do not create another parser, schema, profile map, or preset table.
5. After a scenario rename, make sure that equivalent content keeps the same behavior.

## Curated variants

Read the [fixture matrix](curated-variant-reference.md).
In CI or an approved isolated lab VM, select a fixture explicitly:

```shell
lilrae lab start --scenario-path scenarios/techvault-attacker-target.sdl.yaml
```

Run the focused contract checks in that runner:

```shell
bash tools/run-targeted-tests.sh tests/test_techvault_curated_variants.py
```

Examine parse, compile, realization, selected profiles, and rename behavior.
Examine missing or configuration-disabled dependencies as failures.
Use no-start backend wiring for static proof.

For live proof, compare the observed range with the fixture's reduced matrix.
Do not substitute full-TechVault criteria or historical container counts.
Before you interpret older results, read the [curated live source record](../raes/techvault-curated-live-validation-gate.md).

## Security And Runtime Boundaries

1. Keep catalog and explicit paths within the project.
2. Keep RAES parser validation and bounded diagnostics.
3. Keep secrets and raw rendered configuration out of reports.
4. Use existing non-secret configuration and private runtime-artifact owners.
5. Let the admitted backend own ports, networks, volumes, and service dependencies.
6. Add only apparatus required by admitted evidence and scopes.

## Non-Goals

These procedures do not define a general subset catalog or qualify arbitrary software installation.
They do not change ordinary startup's acquired-pack selection.
