# Lab Walkthrough

In this tutorial, you create failed SSH logins, find their alerts, and explain the result.
Your facilitator must first complete [Workshop setup](setup.md) on an approved isolated lab machine.
Do not run lab operations or tests on the developer workstation.
Use only the assigned victim and the prepared agent workbenches.

This lesson uses the released full-TechVault desktop seat.
The [workshop reference](reference.md) describes its required tools and the separate historical guided fixture.

## 0. Prerequisites, once, at home

Obtain your assigned lab, red workbench, blue workbench, and Wazuh bookmark from the facilitator.
Confirm that the facilitator has authorized the target `172.20.2.20` for this session.
Keep your provider login in the approved account boundary.
Do not copy credentials from another participant.

## 1. Install and stand up the range [2]

Ask the facilitator to confirm that [setup](setup.md) passed before opening the agent.
You do not need a source checkout or Docker management access for this lesson.
Expected starting state: a running, verified range with a monitored SSH victim.
If the seat is unavailable, stop and ask for another prepared session.

## 2. Verify the range is up [2]

Open the Wazuh bookmark supplied for your session.
Confirm that its dashboard loads.
Expected result: the assigned SOC view opens without a certificate error.
If access fails, ask the facilitator for help before generating activity.

## 3. Wire your agent [3]

Open the prepared red workbench.
Inspect its connected tools.
Expected result: `aptl-red` is available, including `kali_run_command`.
Keep the blue workbench closed during the red exercise.

## 4. Confirm the agent can reach Kali [3, 5]

Ask the agent:

> Use `kali_run_command` to run `id` and `hostname` on Kali.

Expected result: the command runs as the unprivileged `kali` user.
Record the hostname returned by the admitted Kali tool.
If the tool fails, stop and ask the facilitator to inspect the backend.

## 5. See the required attack tool [5]

Ask the agent:

> Use `kali_run_command` to locate the SSH client with `command -v ssh`.

Expected result: an SSH executable path.
You will use this client for a small, noisy authentication exercise.

## 6. Attack, hands-on [6]

### Bounded SSH authentication attack

Ask the agent:

> From Kali, make six failed SSH login attempts against the authorized victim `172.20.2.20`.
> Use made-up usernames `aptl-a` through `aptl-f` and no passwords.
> Stop after those six attempts and report the result.
> Do not contact any other target.

Expected result: failed logins rather than an authenticated session.
Record the attempt time and Kali's source address.
Do not interpret an SSH failure as a failed exercise; failed authentication is the intended activity.

## 7. The blue side [7]

Close the red agent and its MCP processes.
Open the prepared blue workbench.
Expected result: `aptl-indexer` and `aptl-wazuh` are available in the blue terminal.
No red server belongs in that client environment.
You will now find evidence from your own activity.

## 8. Meet the SOC dashboard [8]

Return to the assigned Wazuh bookmark.
Open its security events view.
Expected result: the dashboard displays the same lab monitored by your blue tools.
Use the provided route; do not substitute a copied localhost URL.

## 9. Investigate, hands-on [9]

### Find the alerts your own attacks caused

Ask the agent:

> Use `indexer_query` to find recent rule `5710` alerts from my SSH exercise.
> Report the event time, source address, username, and target.

Indexing can take time.
If the query is empty, wait briefly and repeat it within the session's readiness budget.
Expected result: an alert for a non-existent SSH user, correlated with your attempt time and source address.
Do not accept an older participant's alert as proof of your exercise.

### Explain the top alert

Ask the agent:

> Use `wazuh_query_alerts` to inspect the matching SSH alert.
> Explain what happened and which evidence supports your explanation.

Expected result: the agent identifies failed authentication, the source, and the monitored victim.

### Human view

Search the dashboard for `rule.id:5710`.
Compare the event time and source with the tool result.
Expected result: both views identify the same activity.

## 10. Name it: agentic purple [10]

Write three sentences: the activity you generated, the alert you found, and what the alert proves.
Distinguish a detected attempt from a successful compromise.
You have completed an attack-and-investigation loop with an agent.

## 11. Play [11]

If the facilitator permits another attempt, change only the made-up username or timing.
Repeat the same target-bound exercise and compare the alerts.
Do not add targets, tools, or services without the facilitator's authorization.
For the full-TechVault follow-on, request a separate prepared session.

## Developer-preview clean reset

Close both agent workbenches and their MCP processes.
Give the facilitator your non-secret results.
Ask the facilitator to perform [cleanup](setup.md#clean-up) before reassignment.
Do not reset another participant's range.

## Developer-preview troubleshooting

If a tool, bookmark, or alert is missing, stop the exercise.
Use [session recovery](setup.md#recover-a-session) with the facilitator.
Do not bypass capture, TLS, readiness, or participant access checks.
