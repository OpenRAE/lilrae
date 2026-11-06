<a id="install-a-scenario-pack-and-its-adapter"></a>

# Install A Scenario Pack And Its Adapter

Use this guide to select released scenario content and its runtime adapter.
Start with [LilRAE installed](installation.md) and an initialized project on an approved lab machine.
Install only packages and content from publishers your organization approves.
Adapters execute Python code; a valid content manifest alone does not authenticate a publisher.
The result is a configured pack that the catalog validates and startup can use.

## Install the pack

The CLI installation already includes the [required environment-pack distribution](pack-reference.md#installed-pack-source).
For TechVault, use that dependency in the CLI's own environment.
Do not install pack packages into an unrelated system Python.
For the source layout and version fields, see [Pack installation reference](pack-reference.md).

For third-party content, obtain the publisher's intact release directory through an approved transfer.
Place it beneath the project, for example at `releases/my-pack`.
Keep its manifest and published bytes unchanged.
Its directory name must match the declared pack identity.
LilRAE does not download or extract a configured release directory.

## Install the adapter

TechVault's adapter ships in the `lilrae` distribution.
No separate adapter installation is required for TechVault.
For a third-party adapter, install its approved distribution into the same environment as LilRAE.
For pipx, use:

```shell
pipx inject lilrae <adapter-distribution>
```

For a dedicated virtual environment, activate it and use:

```shell
python -m pip install <adapter-distribution>
```

Replace the placeholder with the publisher's package requirement.
Confirm the adapter's declared pack identity and supported release before continuing.
Use the [family adapter contract](../reference/family-adapters.md) for independently released family adapters.

## Select the pack

Open the existing `aptl.json` in the project directory.
For TechVault, set its `scenario` object to:

```json
{
  "source": "env-pack",
  "identity": "techvault"
}
```

For the third-party release directory, use:

```json
{
  "source": "env-pack",
  "identity": "my-pack",
  "pack_directory": "releases/my-pack"
}
```

Save the file.
The path is relative to the project containing `aptl.json`.
Use an ordinary directory inside that project.
See [source restrictions](pack-reference.md#configured-source-restrictions) for refused paths and conflicting settings.

## Verify and run

From the project directory, validate the configuration and inspect the selected pack:

```shell
lilrae config validate
lilrae lab scenarios
```

Expected result: the configuration validates and the catalog lists the configured identity.
The catalog includes identity, version, maturity, and digest information.
`--scenario` validates a catalog selector; it does not configure a different pack.
To change packs, edit `scenario.identity` first.

On the approved lab machine, start the selected pack:

```shell
lilrae lab start
```

Expected result: the final startup report passes the pack's required readiness checks.
When the session ends, use [project-scoped teardown](../deployment.md#manage-the-lifecycle).
Do not run startup or behavior tests on the developer workstation.

## Troubleshooting

If no `aptl.json` is found, return to the project directory or use the command's `--project-dir` option.
Startup searches the project and its parents; catalog listing reads the specified directory.

If a selector is unknown, check `scenario.identity` and repeat `lilrae lab scenarios`.
If pack acquisition fails, verify the release directory, declared identity, manifest, and SDL.
A configured invalid source does not fall back to the installed pack.

If scenario-specific startup or capture is unavailable, verify the adapter installation in the CLI environment.
Compare its entry points with the [adapter reference](pack-reference.md#adapter-entry-points).
Do not bypass acquisition or readiness gates.
