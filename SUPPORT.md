# Get support

LilRAE has community support on a best-effort basis. There is no commercial support channel.

## Where to Ask

1. For vulnerabilities, follow [SECURITY.md](SECURITY.md). Keep details out of public issues, PRs, and discussions.
2. For reproducible bugs, documentation problems, or focused feature requests, open a [GitHub issue](https://github.com/OpenRAE/lilrae/issues).
3. For broader usage or design questions, use GitHub Discussions if enabled.

## What to Include

For a bug report, include:

- Commit or package version.
- Operating system, Python, Docker, and Compose versions.
- Command or API call, with private values removed.
- Relevant scenario, profile, or configuration.
- Expected result, actual result, and error output.
- Whether the project started from clean state after `lilrae lab stop -v`.

Do not destroy project volumes just to prepare a report.
State whether cleanup occurred and whether retained state might affect reproduction.

For MCP or agent integration problems, also include:

- Server name and client.
- Tool call, arguments, and response with private values removed.
- Reviewed logs or trace output.
- Container health at the time.

For a scenario or topology proposal, include:

- Training, research, or validation problem.
- Current workaround, if any.
- Affected containers, networks, services, scenarios, or tools.
- Safety and isolation considerations.
- Expected telemetry or agent behavior.

Keep credentials, private targets, and unreviewed logs out of public reports.

## Maintenance Expectations

Keep reports focused. Supply a reproducible example when possible.
Maintainers handle issues and PRs as time permits.
