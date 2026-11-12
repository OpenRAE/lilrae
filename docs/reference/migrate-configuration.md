# Migrate project configuration

Use this How-to guide for an existing project.
The [migration reference](configuration-migration.md) owns conversion, backup, selection, and refusal contracts.

## Convert an existing project

1. Select the exact project directory.
2. Examine [scenario and provider selection](configuration-migration.md#scenario-and-provider-selection).
3. Examine the intended scenario identity and supported adapter installation.
4. Run the explicit migration command:

```shell
lilrae config migrate --project-dir ./lab
```

If the old configuration omitted its scenario identity, give the intended identity explicitly:

```shell
lilrae config migrate --project-dir ./lab --scenario your-pack-id
```

Examine the converted configuration and original `aptl.json.bak` before startup.
Before you retry, resolve ambiguous input or a conflicting backup.
Do not bypass those refusals with an automatic migration during loading.
