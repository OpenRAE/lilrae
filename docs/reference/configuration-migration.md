# Migrate project configuration

A new workspace has no selected scenario.
Set `scenario.identity` and its source before starting the lab.
The original TechVault adapter remains bundled with LilRAE.
RPT's PurpleTeam adapter is a separate, independently maintained package.

Old `containers` topology booleans are no longer runtime settings.
Use the explicit migration command on an existing project:

```sh
lilrae config migrate --project-dir ./lab
```

If the old configuration omitted its scenario identity, provide the intended identity:

```sh
lilrae config migrate --project-dir ./lab --scenario your-pack-id
```

The command validates the conversion before writing.
It holds the existing project lifecycle lock through validation, backup, and replacement.
Another migration, start, stop, or reset cannot change the project at the same time.
It saves the exact original bytes as `aptl.json.bak` and replaces the configuration atomically.
It preserves unrelated settings and explicit scenario selections.
It never migrates during load, startup, API access, or doctor checks.
A second run on the converted configuration makes no change.
A conflicting backup or ambiguous input stops the conversion.

`containers.profiles` selects bounded operator groups from the admitted scenario.
An omitted selection uses the admitted scenario's groups.
An explicit list does not enable groups absent from that scenario.
Migration preserves disabled groups rather than silently enabling them.
The old `mail` and `reverse` services are retired.
A configuration that enabled either requires an explicit supported replacement before migration.
Retiring the service definitions does not delete existing Docker volumes.
The optional reverse MCP requires an explicitly configured target; its example target is disabled.

A selected startup adapter can declare `minimum_max_map_count`.
Startup and doctor apply that validated minimum to the selected engine's host.
The minimum applies even when the adapter requests no host-tool checks.
A scenario without that requirement causes no kernel probe.
Compose merge features use their shared qualified version floor.
The floor applies to emitted `!reset` or `!override` features, without a product-name trigger.
Image-override preflight uses the same rendered text as the writer and checks before artifact generation or image operations.
Doctor explains that condition when reporting an older Compose version.

The boundary check derives owner identities and module names from installed provider metadata.
`.gc/pack-ownership.json` records specific retained compatibility occurrences.
Each record names its file, symbol, owner, purpose, exact line digest, and permitted count.
A new identifier line or duplicate occurrence fails the check.
Credential, hostname, and account facts cannot use identifier exceptions.
The profile ownership decisions remain in the #1121 architecture preflight.
