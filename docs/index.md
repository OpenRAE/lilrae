# LilRAE (formerly APTL)

LilRAE runs a local purple-team lab for human operators and AI agents.
The released package supplies the CLI and lab assets. Docker runs the selected scenario.

!!! warning "Use an authorized, rebuildable environment"

    LilRAE starts vulnerable services and gives agents penetration-testing tools.
    Keep unrelated credentials elsewhere. Use only systems you are authorized to test.
    Read the [execution boundaries](getting-started/execution-boundaries.md) before starting.

| Reader need | Route |
| --- | --- |
| Learn through an exercise | [Tutorials: first lab](getting-started/quick-start.md) or [workshop](workshop/walkthrough.md) |
| Complete a task | [How-to guides: installation](getting-started/installation.md), [recovery](troubleshooting/index.md), or [documentation](contributing-documentation.md) |
| Look up exact facts | [Reference: CLI](reference/cli.md), [MCP](reference/mcp.md), or [web](reference/web.md) |
| Understand reasons and relationships | [Explanation: architecture](architecture/index.md) and [execution boundaries](getting-started/execution-boundaries.md) |

For older installations, use the [package migration guide](getting-started/installation.md#move-from-aptl-labs-to-lilrae).

## Run Your First Lab

The [first-lab tutorial](getting-started/quick-start.md) owns the complete exercise.
Use these links to return to a task:

- [Check prerequisites](getting-started/prerequisites.md).
- [Install LilRAE](getting-started/installation.md).
- [Choose a scenario](getting-started/quick-start.md#choose-a-scenario).
- [Start and verify the lab](getting-started/quick-start.md#start-and-verify-the-lab).
- [Inspect the running lab](getting-started/quick-start.md#inspect-the-running-lab).
- [Generate safe test activity](getting-started/quick-start.md#generate-safe-test-activity).
- [Inspect results](getting-started/quick-start.md#inspect-results).
- [Troubleshoot](troubleshooting/index.md).
- [Stop or reset the lab](getting-started/quick-start.md#stop-or-reset-the-lab).

## Supported Interfaces

Use the [CLI](reference/cli.md), [MCP](reference/mcp.md), and [web](reference/web.md) references.
Discover current endpoints with `lilrae lab info`.
The operator UI, target applications, and SOC interfaces are separate surfaces.

## Help And Project Policies

- [Get support](https://github.com/OpenRAE/lilrae/blob/dev/SUPPORT.md).
- [Contribute](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md).
- [Report a vulnerability privately](https://github.com/OpenRAE/lilrae/security/advisories/new).
- Review the [OpenSSF assessment](security/openssf-best-practices.md).

## Design And Historical Records

Use the [architecture overview](architecture/index.md) and [decision index](adrs/README.md) for design context.
Use the [documentation inventory](architecture/documentation-assignments.md) to find source and historical records.
Follow [release qualification](testing/smoke-test-plan.md) when checking a release candidate.
