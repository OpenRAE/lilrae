# Configuration migration reference

See [migrate project configuration](migrate-configuration.md) for the procedure.

The command validates the conversion before it writes.
It holds the existing project lifecycle lock through validation, backup, and replacement.
Another migration, start, stop, or reset cannot change the project at the same time.
It saves the exact original bytes as `aptl.json.bak` and replaces the configuration atomically.

It keeps unrelated settings and explicit scenario selections.
It never migrates during load, startup, API access, or doctor checks.
A second run on the converted configuration makes no change.
A conflicting backup or ambiguous input stops the conversion.

`containers.profiles` selects bounded operator groups from the admitted scenario.
An omitted selection uses the admitted scenario's groups.
An explicit list does not enable groups absent from that scenario.
Migration keeps disabled groups. It does not silently enable them.

The old `mail` and `reverse` services are retired.
A configuration that enabled either requires an explicit supported replacement before migration.
Service-definition removal does not delete existing Docker volumes.
The optional reverse MCP requires an explicitly configured target. Its example target is disabled.

A selected startup adapter can declare `minimum_max_map_count`.
Startup and doctor apply that validated minimum to the selected engine's host.
The minimum applies even when the adapter requests no host-tool checks.
A scenario without that requirement causes no kernel probe.

Compose merge features use their shared qualified version floor.
The floor applies to emitted `!reset` or `!override` features, without a product-name trigger.
Image-override preflight uses the same rendered text as the writer and does its checks before artifact generation or image operations.
Doctor explains that condition when it reports an older Compose version.

The boundary check derives owner identities and module names from installed provider metadata.
`.gc/pack-ownership.json` records specific retained compatibility occurrences.
Each record names its file, symbol, owner, purpose, exact line digest, and permitted count.
A new identifier line or duplicate occurrence fails the check.

Credential, hostname, and account facts cannot use identifier exceptions.
The profile ownership decisions remain in the #1121 architecture preflight.

## Earlier section links

These links keep earlier heading targets after the rewrite.

- <a id="migrate-project-configuration"></a>[Migrate project configuration](migrate-configuration.md#migrate-project-configuration)

## Scenario and provider selection

A new workspace has no selected scenario.
`scenario.identity` and its source must be selected before startup.
The original TechVault adapter remains bundled with LilRAE.
RPT's PurpleTeam adapter is a separate, independently maintained distribution.
Old `containers` topology booleans are not current runtime settings.
The explicit migration interface converts supported older configuration without implicit changes during ordinary loading.
