# LilRAE (formerly APTL)

LilRAE is a local purple-team lab for human operators and AI agents.
It runs intentionally vulnerable services for authorized research, training, and assessment.
Scenario documents select the range. The `lilrae` CLI manages its lifecycle and run records.

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=Brad-Edwards_aptl)](https://sonarcloud.io/summary/new_code?id=Brad-Edwards_aptl)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/OpenRAE/lilrae/badge)](https://scorecard.dev/viewer/?uri=github.com/OpenRAE/lilrae)

Accepted to [Black Hat USA Arsenal 2026](https://blackhat.com/us-26/arsenal/schedule/#aptl-advanced-purple-team-labs-52322),
[SecTor Arsenal 2026](https://blackhat.com/sector/arsenal/schedule/index.html#aptl-advanced-purple-team-labs-54785), and SecTor 2026 Briefings.

## Status And Safety

**Active development. Not for production. Not hardened.**

Use a dedicated, rebuildable environment and keep unrelated credentials elsewhere.
Operate only on systems you are authorized to test.
Native Docker can expose the host. A VM boundary reduces risk but does not remove it.

Seats have no default outbound network controls.
Read the [execution boundaries and limits](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/execution-boundaries.md) before starting a lab.

## Quick Start

Follow [Run your first lab](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/quick-start.md).
For an older installation, use the [package migration guide](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/installation.md#move-from-aptl-labs-to-lilrae).

## Requirements

Check the [prerequisites](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/prerequisites.md) and [host requirements](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/host-requirements.md).
These pages own the supported versions and resource limits.

## Supported Interfaces

Use the [CLI](https://github.com/OpenRAE/lilrae/blob/main/docs/reference/cli.md), [MCP](https://github.com/OpenRAE/lilrae/blob/main/docs/reference/mcp.md), and [web](https://github.com/OpenRAE/lilrae/blob/main/docs/reference/web.md) references for supported interfaces.
Use `lilrae lab info` for the current project's URLs and credential locations.

## Scenarios

The installed LilRAE startup catalog determines available scenarios.
[Scenario Pack installation](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/installing-packs.md) describes selection and acquisition.
Reusable definitions live in [OpenRAE/env-packs](https://github.com/OpenRAE/env-packs).
LilRAE owns local admission, realization, readiness, and operation.

## Documentation

The [published manual](https://openrae.github.io/lilrae/) has four reader routes:

| Reader need | Route |
| --- | --- |
| Learn through an exercise | [Tutorials: first lab](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/quick-start.md) |
| Complete a task | [How-to guides: install LilRAE](https://github.com/OpenRAE/lilrae/blob/main/docs/getting-started/installation.md) |
| Look up exact facts | [Reference: CLI](https://github.com/OpenRAE/lilrae/blob/main/docs/reference/cli.md) |
| Understand reasons and relationships | [Explanation: architecture](https://github.com/OpenRAE/lilrae/blob/main/docs/architecture/index.md) |

## Project Links

- [Get support](https://github.com/OpenRAE/lilrae/blob/dev/SUPPORT.md).
- [Contribute](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md).
- [Report a vulnerability privately](https://github.com/OpenRAE/lilrae/security/advisories/new).
- Read the [security policy](https://github.com/OpenRAE/lilrae/blob/main/SECURITY.md) and [OpenSSF assessment](https://github.com/OpenRAE/lilrae/blob/main/docs/security/openssf-best-practices.md).

## Ethics And Disclaimer

Follow applicable laws and obtain authorization before testing.
Do not disclose vulnerabilities in public issues or discussions.
Lab test credentials are fixtures. Keep generated control-plane credentials private.
LilRAE uses standard security tools and gives agents Kali access.
This public repository adds no red-team enhancements to their existing capabilities.

## License

[MIT](https://github.com/OpenRAE/lilrae/blob/main/LICENSE).
