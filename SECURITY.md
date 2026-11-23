# Security Policy

Use this guide to report a suspected vulnerability privately.

## Reporting a Vulnerability

Do not put vulnerability details in public issues, pull requests, or discussions.

1. Open a [private vulnerability report](https://github.com/OpenRAE/lilrae/security/advisories/new).
2. If private reporting is unavailable, use the private contact path on [Brad Edwards' profile](https://github.com/Brad-Edwards).
3. Include the affected package, command, container, MCP server, scenario, or document.
4. Identify the version, commit, or branch.
5. Give reproduction steps, expected behavior, actual behavior, and impact.
6. Include available proof of concept, logs, packet captures, or screenshots after removing secrets and private data.

Use the [published advisories](https://github.com/OpenRAE/lilrae/security/advisories) to find disclosed reports.

## Scope

Report problems in these boundaries:

- CLI, MCP servers, web UI, and API.
- Scenario parsing, compilation, and execution.
- Run archives, telemetry export, and secret redaction.
- Compose assets, images, mounted configuration, and generated files.
- Lab isolation and host exposure.
- Repository automation that handles untrusted input.

LilRAE intentionally includes vulnerable targets, test credentials, and penetration-testing tools.
Report failures that cross lab boundaries, expose operator data, leak control-plane secrets, or weaken isolation.
Also report failures that invalidate documented safety assumptions.

## Response Expectations

Maintainers review reports as time permits.
Reproducible issues affecting current code, host safety, secrets, published packages, or documented workflows receive priority.
Do not publish exploit details before the maintainer can assess the report and prepare a fix or mitigation.
