<a id="workshop-playbook"></a>

# Facilitate A Workshop

Use this guide to lead the [guided tutorial](walkthrough.md).
First complete [Workshop setup](setup.md) and prove the exact learner route.
Use an approved isolated range and approved provider accounts.
The result is one bounded attack, correlated alert, and participant explanation per learner.

The times below are estimates for a beginner group, not measured class results.
The guided session takes about 60 minutes, followed by authorized practice.

## Before you start

Confirm every assignment, workbench, and Wazuh bookmark.
Keep operator credentials and Docker management access away from learners.
Check that each participant knows the authorized target and stop condition.
Use [Emergency rollout](emergency-rollout.md) only for a separately approved contingency.

## 1. Intro (about 5 min)

State the task: generate failed logins, find the alerts, and explain the evidence.
Identify the assigned range and its target boundary.
Show learners how to request help and stop a session.
Explain that reset destroys volume data and belongs to the facilitator.

## 2. Cyber ranges (about 5 min)

Identify the attacker, monitored victim, and SOC view in the prepared session.
Explain that the range is disposable but still requires isolation and authorization.
Do not describe it as risk-free.

## 3. Agents in cyber (about 5 min)

Show the red workbench's connected `aptl-red` server.
Ask a learner to identify `kali_run_command` before using it.
Explain that the tool runs real commands inside the assigned range.

## 4. The kill chain (about 5 min)

Describe reconnaissance, access attempts, and an attack objective in plain language.
Ask which step the failed-login exercise represents.
Explain that a failed attempt can still leave useful evidence.

## 5. Offensive tools (about 5 min)

Guide learners through the Kali identity and SSH-client checks in the tutorial.
Stop any session whose tool or target differs from the prepared fixture.
Do not substitute management commands for participant proof.

## 6. Attack, hands-on (about 12 min)

Have learners follow the tutorial's bounded six-attempt prompt.
Ask them to record the time and source address.
Confirm that they stop after the authorized attempts.
If the agent refuses or cannot act, inspect the authorization and tool setup.
Do not ask learners to bypass a refusal or protection.

## 7. Cyber defense (about 4 min)

Close red agents and MCP processes before opening blue workbenches.
Explain the next task: find the same activity through the defensive tools.
Confirm that red tools are absent from the blue client environment.

## 8. Defensive tools (about 5 min)

Open the assigned Wazuh bookmark.
Show where learners can search security events.
Explain that indexer and Wazuh tools provide another view of the event data.
Keep supporting observability services separate from participant investigation tools.

## 9. Investigate, hands-on (about 12 min)

Have learners query recent rule `5710` alerts through the tutorial.
Compare event time, source address, username, and target.
Require correlation with their own attempts.
If indexing is delayed, wait and retry within the prepared readiness budget.
Do not accept an older participant's alert as a successful result.

## 10. Purple teaming (about 4 min)

Ask each learner to explain the attempted action and the corresponding detection.
Ask what the evidence proves about authentication and compromise.
Collect a short, non-secret summary for the session.

## 11. Play (open)

Authorize a specific variation before learners repeat the exercise.
Keep the same target and bounded attempt count.
For enterprise, web, Suricata, MISP, or Shuffle exercises, prepare a separately bounded follow-on lesson.
At session end, follow [cleanup](setup.md#clean-up) before assigning the range again.
