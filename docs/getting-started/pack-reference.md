# Pack Installation Reference

A pack supplies SDL, assets, detection content, and seed data.
Its adapter supplies scenario-specific runtime behavior through Python entry points.
Generic realization alone does not establish that adapter startup, verification, or capture is available.
Use [Install a scenario pack](installing-packs.md) for the procedure.

## Installed Pack Source

The default source is `env-pack`.
The current LilRAE dependency is `raes-env-packs>=7.2.4,<8`.
An installed pack is read from `resources/packs/<identity>/sdl/<identity>.sdl.yaml`.
Acquisition stages a private copy and applies environment-pack validation gates.
TechVault includes the `techvault` and `techvault-participant-study` packs.

A configured third-party release has this shape:

```text
project/
  aptl.json
  releases/
    my-pack/
      pack.yaml
      associated-artifacts.json
      sdl/my-pack.sdl.yaml
```

## Configured Source Restrictions

`scenario.pack_directory` names a project-relative pack root.
Absolute paths, symlinks, dot components, traversal, empty components, home expansion, and environment expansion are refused.
Sources under `.aptl` and overlapping source/staging trees are refused.
The field cannot be combined with `scenario.root` or `source: project-tree`.
Invalid configured bytes fail acquisition without fallback.
Omitting `pack_directory` restores the installed source.

A separately installed Python distribution does not automatically select its pack data.
Pack-local `.env` files do not supply operator configuration.
Source locations do not become pack identity or run provenance.
A content manifest proves byte integrity, not publisher authenticity.

## Adapter Entry Points

| Group | Responsibility |
| --- | --- |
| `aptl.pack_backend_interactions` | Serving |
| `aptl.scenario_capture` | Capture |
| `aptl.scenario_startup` | Startup |
| `aptl.scenario_runtime_parameters` | Runtime parameters |
| `aptl.scenario_planning_compatibility` | Planning compatibility |
| `aptl.scenario_verifiers` | Verification |
| `aptl.evidence_payload` | Evidence collection |
| `aptl.participant_mcp_smoke_plans` | Participant MCP smoke plans |
| `aptl.participant_desktop` | Desktop consoles, logins, guide, and hostnames through SDL references |

The TechVault adapter package is `aptl_techvault`, inside the `lilrae` distribution.
Entry-point names follow each group's contract; some include a suffix such as `.aptl`.
Independently released family trials require all six primary capabilities from one compatible distribution.
Legacy adapter installation does not establish that qualification.
See the [family adapter contract](../reference/family-adapters.md).

## Contributor Boundary Check

The existing pack-boundary check uses the active owner's configured source.
Additional installed owners require explicit sources when their packs are separately supplied:

```shell
uv run python tools/check_pack_boundary.py . --pack-directory my-pack=releases/my-pack
```

The option can be repeated as `ID=PATH`.
Every installed owner still needs an admissible pack.
