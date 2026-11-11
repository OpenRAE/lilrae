# Victim Template Guide

Use this How-to guide to add a victim through the existing RAES authoring boundary.
Issue #812 removed the old in-tree victim image on 2026-07-24.
Do not copy the retired Dockerfile or installer paths.

The [source record](records/victim-template-guide-2026-11-06.txt) keeps the earlier procedure at revision `28fc8f18`.
Its design decisions remain historical evidence.
Status reviewed: 2026-11-06.

## Author a victim

1. Read the [scenario authoring boundary](../sdl/index.md).
2. Use the [environment-pack documentation](https://github.com/OpenRAE/env-packs) for pack structure and schema.
3. Declare the node's required software, accounts, services, content, and network attachments in RAES SDL.
4. Reuse the supported [node realization routes](../components/node-realization.md).

5. Keep real operator credentials outside portable scenario content.
6. Examine the scenario with the [static validation procedure](../raes/scenario-validation.md).
7. Use CI or an approved isolated VM for the relevant scenario contract tests.
8. Validate the admitted deployment with the [live validation procedure](../raes/live-validation.md).

9. Compare required services and log producers with their observed runtime state.

A static pass does not prove installation, startup, monitoring, or access.
The backend refuses unsupported realization. Do not add a parallel parser or topology map.

## Inspect the result

Use [victim inspection](../components/victim-operations.md) after startup.
Use runtime endpoints from `lilrae lab info`.
A scenario's declared address does not establish a published host port.

## Earlier section links

These links keep earlier heading targets after the rewrite.

- <a id="victim-container-template-guide"></a>[Victim Container Template Guide](records/victim-template-guide-2026-11-06.txt)
- <a id="overview"></a>[Overview](records/victim-template-guide-2026-11-06.txt)
- <a id="core-patterns-reference-files"></a>[Core Patterns (Reference Files)](records/victim-template-guide-2026-11-06.txt)
- <a id="1-post-entrypoint-one-off-service-pattern"></a>[1. Post-Entrypoint One-Off Service Pattern](records/victim-template-guide-2026-11-06.txt)
- <a id="2-ssh-key-multi-mode-pattern"></a>[2. SSH Key Multi-Mode Pattern](records/victim-template-guide-2026-11-06.txt)
- <a id="3-siem-integration-pattern"></a>[3. SIEM Integration Pattern](records/victim-template-guide-2026-11-06.txt)
- <a id="container-creation-steps"></a>[Container Creation Steps](records/victim-template-guide-2026-11-06.txt)
- <a id="1-copy-victim-container-dont-build-from-scratch"></a>[1. Copy Victim Container (Do Not Build From Scratch)](records/victim-template-guide-2026-11-06.txt)
- <a id="2-rename-all-files-and-references"></a>[2. Rename All Files and References](records/victim-template-guide-2026-11-06.txt)
- <a id="3-study-existing-patterns-after-copying"></a>[3. Study Existing Patterns (After Copying)](records/victim-template-guide-2026-11-06.txt)
- <a id="3-networknaming-allocation"></a>[3. Network/Naming Allocation](records/victim-template-guide-2026-11-06.txt)
- <a id="3-use-existing-utilities"></a>[3. Use Existing Utilities](records/victim-template-guide-2026-11-06.txt)
- <a id="4-docker-compose-integration"></a>[4. Docker Compose Integration](records/victim-template-guide-2026-11-06.txt)
- <a id="implementation-checklist"></a>[Implementation Checklist](records/victim-template-guide-2026-11-06.txt)
- <a id="pre-implementation"></a>[Pre-Implementation](records/victim-template-guide-2026-11-06.txt)
- <a id="container-files"></a>[Container Files](records/victim-template-guide-2026-11-06.txt)
- <a id="integration"></a>[Integration](records/victim-template-guide-2026-11-06.txt)
- <a id="testing"></a>[Testing](records/victim-template-guide-2026-11-06.txt)
- <a id="lab-integration"></a>[Lab Integration](records/victim-template-guide-2026-11-06.txt)
- <a id="key-principles"></a>[Key Principles](records/victim-template-guide-2026-11-06.txt)
