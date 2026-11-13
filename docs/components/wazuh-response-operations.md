# Configure and diagnose Wazuh response

Use an approved isolated lab VM and a disposable test account or target.
Before you change enforcement, read the [response reference](wazuh-active-response.md).
Only `aptl-firewall-drop` honors the Kali whitelist.
Other response commands can affect Kali access.

## Wiring a detection rule to AR

1. Select a rule that detects the intended behavior.
2. Examine the selected rule's authored severity and target agent.
3. Examine the project's manager template and its generated private runtime copy.
4. Configure the selected response block through the existing project configuration owner.

5. Uncomment only the intended block.
6. Keep a bounded timeout and the intended location.

For example, this block selects one SQL-injection rule:

```xml
<active-response>
  <command>aptl-firewall-drop</command>
  <location>local</location>
  <rules_id>302010</rules_id>
  <timeout>120</timeout>
</active-response>
```

Do not add a `level` matcher unless the broader logical-OR behavior is intended.
Do not edit a checked template and assume a container restart renders it again.
Startup renders private configuration under `.aptl/config/`.
Apply the changed project configuration through an approved lab restart.

Volume removal is destructive and is not required merely to restart the manager.

Use the realized manager identity for service operations.
Before you generate a bounded test event, make sure that the intended block loaded.
Examine detection, dispatch, target effect, and timeout cleanup separately.

Before you select an agent scope, read the [response-location contract](wazuh-active-response.md#response-location).

## `disable-account` manual procedure (AC#4 of #249)

Use a disposable, non-administrator account.
Do not test against the only login a participant can use.

1. Create the account through the admitted target's normal account-management interface.
2. Select a detection rule that actually identifies this account.
3. Examine the agent's `disable-account` implementation and supported account type.
4. Configure a bounded response for that exact rule and agent.

5. Apply the configuration through the existing manager configuration owner.
6. Generate the bounded event that matches the selected rule.
7. Examine the account state on the target.
8. Examine timeout recovery or explicitly re-enable the account.

9. Remove the temporary response and disposable account.

A Linux account-disable script does not by itself prove Samba AD account support.
The former `kinit` example did not establish that its event matched the selected rule.
The [source record](records/wazuh-response-2026-11-06.txt) keeps that earlier test proposal.

## Troubleshooting

| Observation | Action |
| --- | --- |
| No response dispatch | Make sure that the rule fired, the block is enabled, and the manager loaded the intended configuration. |
| Dispatch without a target effect | Examine the agent's response log, installed script, and required authority. |
| `SKIPPED for whitelisted` | Make sure that the intended Kali carve-out applies. |
| An unexpected source-IP block | Do a check for bare `firewall-drop`, another command, or an incorrect whitelist. |
| A broader alert set triggers response | Examine combined `rules_id`, `rules_group`, and `level` matchers. |
| A drop remains after expiry | Examine the delete invocation and target firewall state before the next iteration. |

Run `scripts/test-wazuh-ar-whitelist.sh` only in CI or an approved isolated VM.
Keep raw credentials and target log payloads outside shared reports.
