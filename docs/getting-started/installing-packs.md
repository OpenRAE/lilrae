# Install a scenario pack and its adapter

LilRAE does not contain the scenarios it runs. A scenario has two parts, and you
install each one:

1. **The pack.** A RAES environment pack holds the scenario content: the SDL
   document, assets, detection content, and seed data. TechVault is a pack.
2. **The adapter.** A Python package that provides the scenario-specific
   behavior for the pack's identity: serving, capture, startup, runtime
   parameters, verification, and participant smoke plans. The generic
   materializer in `src/aptl` does not branch on scenario names. The adapter
   supplies all scenario-specific behavior through entry points.

You must install both. The pack without its adapter realizes generically, but
its scenario-specific startup, verification, and capture do not run.

## Install the pack

The default scenario source is `env-pack`. LilRAE resolves the pack from the
installed `raes-env-packs` distribution by identity. It reads
`resources/packs/<identity>/sdl/<identity>.sdl.yaml`, stages the pack into
private project state, and validates it with the env-packs gates before use.

Install the distribution that carries the pack:

```shell
pip install "raes-env-packs>=6.5.1,<7"
```

LilRAE supports env-packs 6.5.1 and later 6.x releases.

TechVault ships in `raes-env-packs` as two packs: `techvault` (the environment)
and `techvault-participant-study` (the environment plus authored red and blue
participants).

For a third-party pack, place the publisher's release directory beneath your
project and configure `scenario.pack_directory`. Keep its published bytes and
manifest intact. The directory must be named for the pack's declared identity:

```text
project/
  aptl.json
  releases/
    my-pack/
      pack.yaml
      associated-artifacts.json
      sdl/my-pack.sdl.yaml
      ... other released files
```

LilRAE reads this directory as data, stages a private copy, and applies the same
env-packs validation gates as for the installed default. Installing a separate
Python distribution alone does not select its pack data. Select its release
directory explicitly; do not overlay `raes_env_packs`. Acquisition performs no
download, installation, or archive extraction. A valid content manifest proves
byte integrity, not publisher authenticity. Adapter installation is separate.

## Install the adapter

The adapter registers entry points in these groups, keyed by the pack identity:

| Entry-point group | Purpose |
| --- | --- |
| `aptl.pack_backend_interactions` | Serving provider |
| `aptl.scenario_capture` | Capture provider |
| `aptl.scenario_startup` | Startup provider |
| `aptl.scenario_runtime_parameters` | Runtime parameters |
| `aptl.scenario_planning_compatibility` | Planning compatibility |
| `aptl.scenario_verifiers` | Verifier |
| `aptl.evidence_payload` | Evidence collectors |
| `aptl.participant_mcp_smoke_plans` | Participant MCP smoke plans |
| `aptl.participant_desktop` | Participant desktop consoles, logins, guide and hostnames, as SDL references |

The TechVault adapter is `aptl_techvault`. It ships inside the `lilrae`
(LilRAE) distribution, so a LilRAE install already has it. You do not install it
separately.

A third-party pack supplies its own adapter distribution. Install it with pip.
Its entry points must name the pack's identity (for example `mypack.aptl`).
After install, confirm the entry points resolve:

```shell
python -c "from importlib.metadata import entry_points as e; print([ep.name for ep in e(group='aptl.scenario_startup')])"
```

For an independently released family adapter, use the
[public family contract](../reference/family-adapters.md).
The adapter qualifies an exact family release and backend once.
Each admitted trial carries its own snapshot and provenance through that contract.
Family trials require all six primary capabilities from one compatible distribution.
Ordinary installed legacy adapters do not satisfy that qualification.

## Select the pack

The active scenario is an operator decision. It lives in `aptl.json`:

```json
{
  "scenario": {
    "source": "env-pack",
    "identity": "techvault"
  }
}
```

- `source: env-pack` resolves the pack from the installed distribution by
  identity. This is the default.
- `identity` names the pack. A new project has no selected identity.
  Set it explicitly before starting a pack-backed scenario.

To select the third-party release above:

```json
{
  "scenario": {
    "source": "env-pack",
    "identity": "my-pack",
    "pack_directory": "releases/my-pack"
  }
}
```

`pack_directory` names the pack root relative to the project containing
`aptl.json`, independently of the shell's working directory. Absolute paths,
symlinks, dot/traversal or empty path components, environment or home expansion,
and `.aptl` runtime-state sources are refused. It cannot be combined with
`scenario.root` or `source: project-tree`; those fields remain the explicit
development surface. Missing or invalid configured bytes fail acquisition;
they never fall back to an installed pack. Omit `pack_directory` to use the
installed default again. Source locations do not become pack identity or run
provenance, and pack-local `.env` files do not supply operator configuration.

The backend never switches the scenario at runtime. You select it before
`lilrae lab start`.

The repository's pack-boundary check uses the configured source for its active
owner pack. When additional installed adapters claim separately sourced packs,
give each owner its source explicitly:

```shell
uv run python tools/check_pack_boundary.py . --pack-directory my-pack=releases/my-pack
```

Repeat `--pack-directory ID=PATH` for additional owners. Every installed owner
still needs an admissible pack; unresolved claims fail the check.

## Verify and run

List the configured pack. The catalog projects the pack named in `aptl.json`:

```shell
lilrae lab scenarios
```

The command prints the identity, version, status, digest, and description. Start
the lab:

```shell
lilrae lab start
```

`lilrae lab start` uses the configured identity. The `--scenario` option selects
another identity, but only one that the catalog already lists. The catalog lists
the configured pack, so `--scenario` cannot select a pack that `aptl.json` does
not configure. To run a different pack, set `scenario.identity` in `aptl.json`.

## Troubleshooting

- **`No aptl.json was found in <directory>`**. The command ran outside a lab
  project. `lilrae lab start --scenario` reads the nearest `aptl.json` at or
  above the project directory. `lilrae lab scenarios` reads only the project
  directory itself. Run the command in the project, or pass `--project-dir`.
- **`Unknown scenario id '<x>'. Available scenarios: <y>`**. The identity is
  not the configured pack. Set `scenario.identity` to `<x>` in `aptl.json`, then
  run `lilrae lab scenarios` to confirm the catalog lists it.
- **`env-pack source not found for '<x>'`**. Check the configured release
  directory and its identity. With no `pack_directory`, install the distribution
  that carries `resources/packs/<x>/`.
- **Acquisition rejects unsafe source or budget**. Check for symlinks, runtime
  state in the source, or overlapping source/staging trees. Missing or corrupt
  manifests and SDL are also refused by the normal pack gates.
- **The lab realizes, but scenario-specific startup or verification does not
  run**. The adapter is missing. Install the adapter distribution and confirm
  its entry points name the pack identity.
