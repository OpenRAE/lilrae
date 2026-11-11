# Validate project configuration

Use this How-to guide for an existing lab project.
See the [CLI reference](cli.md) for supported commands and result contracts.

## Configuration And Secrets

1. Keep durable, non-secret project settings in `aptl.json`.
2. Run `lilrae config validate` in the approved lab environment.
3. Correct reported configuration errors before startup.
4. Use `lilrae lab info` to discover observed access endpoints and credential-file locations.
5. Keep runtime credentials and generated client configuration in private project files.

`.env` and `.mcp.json` can contain secrets.
Do not paste generated files into issues, command arguments, or documentation examples.
Use [configuration migration](migrate-configuration.md) for an older project format.
