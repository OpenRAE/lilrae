# Wazuh Active Response

Wazuh active response runs an enabled command when a manager alert matches its response block.
The affected agent's `wazuh-execd` executes the configured script.
The script can change local firewall or account state.

## Overview

The design uses Wazuh response for packet blocking while Suricata stays IDS-only.
See [ADR-019](../adrs/adr-019-suricata-ids-only-prevention-via-wazuh-ar.md).
Agent placement and namespace authority use [ADR-020](../adrs/adr-020-wazuh-agents-in-process-vs-sidecar.md).
The whitelist decision is in [ADR-021](../adrs/adr-021-active-response-whitelist-via-wrapper.md).

## Architecture

The manager sends the selected command to the agent.
`aptl-firewall-drop` reads `/var/ossec/etc/lists/active-response-whitelist` before it adds a rule.
It writes its result to `/var/ossec/logs/active-responses.log`.

This script implements the stateful protocol directly.
It does not wrap the upstream `firewall-drop` process.
A forwarding wrapper can deadlock if it buffers the complete protocol input.
The admitted node's software and build determine script installation. A historical agent count is not a runtime inventory.

## Available commands

| Command | Honors whitelist? | Effect |
| --- | --- | --- |
| `aptl-firewall-drop` | yes | The command adds or removes an INPUT-chain source-IP drop. |
| `firewall-drop` | no | The upstream command drops a source IP without the LilRAE whitelist. |
| `host-deny` | no | The command updates TCP-wrapper denial state. |
| `disable-account` | no | The target's script disables the selected account. |
| `route-null` | no | The command adds a null route. |

The manager template declares these commands.
An agent must have the actual script and required authority for response availability.
Only `aptl-firewall-drop` gives the Kali whitelist protection.

## Wiring a detection rule to AR

See [configure Wazuh response](wazuh-response-operations.md#wiring-a-detection-rule-to-ar).

## Whitelist (kali-IP carve-out)

The checked whitelist contains `172.20.4.30`, `172.20.1.30`, and `172.20.2.35`.
It accepts one IPv4 address per line.
Blank lines and separate `#` comment lines are permitted.
Inline comments and CIDR ranges do not match the script's exact whole-line lookup.

| Input | Result |
| --- | --- |
| `add`, whitelisted source | The script logs `SKIPPED for whitelisted` and exits. It does not change iptables. |
| `add`, other source | The script searches for an existing rule. If the rule is absent, it adds the INPUT drop. |
| `delete` | The script removes matching drops regardless of whitelist membership. |

The delete path removes stale rules even after the whitelist changes.
The whitelist permits later purple-team iterations. It does not suppress detection.

## Severity gate

Wazuh combines `rules_id`, `rules_group`, and `level` matchers with logical OR.
A block with rule 302010 and level 10 also matches other level-10-or-higher alerts.
A match on either condition selects the alert.

The five checked response blocks select explicit rules without a `level` matcher.
The configuration declares their selected rules at level 10 or higher.
A new low-severity rule does not inherit that property.
A level-only block is a broader, separately selected policy.

## Timeout strategy

The checked blocks use 120-second timeouts.
After expiry, the agent sends the delete command for cleanup.
The recommended exercise range is 60–300 seconds.
This recommendation does not replace the selected command's actual cleanup behavior.

## Default posture

All five checked response blocks ship commented out.
Do not use `<disabled>yes</disabled>` to turn off one block.
`wazuh-execd` reads the first `<disabled>` element under `<active-response>` as the global switch.
A `yes` value stops the manager's `wazuh-execd`, and the manager restart API then fails.
Detection rules can still generate alerts.
See [default defensive posture](default-defensive-posture.md).

## `disable-account` manual procedure (AC#4 of #249)

See the [account-response procedure](wazuh-response-operations.md#disable-account-manual-procedure-ac4-of-249).

## Troubleshooting

See [response diagnosis](wazuh-response-operations.md#troubleshooting).

## Related

- [Continuity cleanup decision](../adrs/adr-024-orchestrator-side-purple-continuity-carve-out.md)
- `tests/test_wazuh_active_response.py`: manager-template and script contract checks.
- `scripts/test-wazuh-ar-whitelist.sh`: targeted whitelist behavior checks for an approved runner.

## Response location

`location=local` selects the agent that generated the alert.
Other configured locations can select all agents, a named agent, or the manager.
The installed Wazuh version defines its exact supported location values.
The selected location does not grant a script authority beyond its installed target context.
