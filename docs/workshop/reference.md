# Workshop Reference

Use [Workshop setup](setup.md) to prepare the released seat and [Lab Walkthrough](walkthrough.md) for the lesson.
This reference distinguishes that route from the historical reduced research fixture.

## Released Desktop Seat

The current signed desktop image runs the full TechVault lab inside a disposable KVM guest.
The participant uses the guest browser and separate red/blue agent terminals.
Event mode gives the desktop account no sudo authorization or Docker-group membership.
The physical host account remains the seat owner.

| Exercise item | Required surface |
| --- | --- |
| Attacker operation | `aptl-red`, `kali_run_command` |
| Alert search | `aptl-indexer`, `indexer_query` |
| Alert inspection | `aptl-wazuh`, `wazuh_query_alerts` |
| Human view | Generated Wazuh desktop bookmark |
| Bounded target | Victim `172.20.2.20`, after facilitator verification |
| Expected SSH alert | Wazuh rule `5710` |

The full blue role also admits network, threat-intelligence, and SOAR tools.
This introductory lesson does not require those operations.
The smoke answer key requires an unprivileged Kali identity and recent SSH alert hits.
A successful command alone does not establish correlation or full readiness.

The image declares its resource minimums and signed boundary policy.
Use those values rather than a reduced-fixture resource estimate.
A developer preview can pull or build assets; offline appliance startup must use its digest-locked staged inputs.
Downloads, image pulls, image builds, or package resolution fail offline qualification.
See [execution boundaries](../getting-started/execution-boundaries.md) for containment limits.

## Historical Guided Fixture

The checkout-only guided-purple version 1 fixture is separate from the released desktop seat.
Its source inputs are:

| Item | Source or value |
| --- | --- |
| Profile | `participant-profiles/guided-purple-v1/profile.json` |
| Project configuration | `participant-profiles/guided-purple-v1/aptl.json` |
| Scenario | `scenarios/techvault-attacker-target.sdl.yaml` |
| Readiness contract | `participant-profiles/guided-purple-v1/readiness.json` |
| Resource fixture | x86-64, eight vCPUs, 16 GiB memory, 100 GiB disk |
| Red role | `aptl-red` |
| Guided-blue role | `aptl-indexer`, `aptl-wazuh` |

The wheel does not ship this reduced profile or its research SDL.
Its configuration and scenario require explicit staging from a matching checkout.

It declares Kali, one victim, Wazuh manager, Wazuh indexer, and their network dependencies.
The historical profile derives a ten-service surface, including capture, access, and observability apparatus.
That exact-surface contract is not evidence of a current passing realization.
There is no standalone guided-workbench launch CLI.
Do not present this fixture as an independently supported participant deployment.

## Historical Contingencies

The [July hosted-seat reference](hosted-backup-reference.md) records one pinned reduced-profile trial.
The [August archive](arsenal-2026/README.md) records a different full-TechVault event.
Neither qualifies the current launcher or development branch.
Current releases omit TheHive and Cortex.
