<a id="emergency-workshop-rollout-runbook"></a>

# Prepare An Emergency Workshop Rollout

Use this guide when participant machines cannot support the planned exercise.
You need a separately approved hosting plan, provider budget, access policy, and teardown owner.
Do not create cloud resources or transfer payloads before that approval.
The result is an admitted contingency session or an explicit decision to postpone.
Do not run lab operations or behavior tests on the developer workstation.

## Decision Gate

Confirm which failure blocks the normal route: Docker installation, platform mismatch, unavailable downloads, or an active session failure.
First try [session recovery](setup.md#recover-a-session) for an existing range.
Do not treat emergency hosting as qualification of an untested delivery path.
Record each defect and retain non-secret evidence for its repair.

## Capacity Model

Calculate required vCPUs for the intended instance size and seat count.
Include replacement and canary capacity.
For an approved AWS deployment, inspect the selected region's Standard On-Demand quota:

```shell
aws service-quotas get-service-quota \
  --service-code ec2 \
  --quota-code L-1216C47A \
  --region "$AWS_REGION"
```

Request the total required quota if an increase is needed.
Confirm approval before launch.
The [historical trial reference](hosted-backup-reference.md) records its exact resource inputs.

## Golden Host

Build one canary on the same intended delivery path as participants.
Install the approved runtime, desktop access, and agent versions.
Use [Workshop setup](setup.md) for the released desktop-seat exercise.
For a released full-TechVault seat, use the [seat launcher](../reference/appliance-seat-launcher.md).
Do not substitute a historical provisioning snapshot for either route.

Complete the actual tutorial on that canary before copying an event image.
A Linux canary does not qualify Windows, macOS, or another access path.

## Lab Contract

Choose one profile for the event and record its exact inputs.
For this lesson, keep red and blue agent terminals separate.
Use only the SSH and Wazuh operations required by the tutorial.
Use [the workshop reference](reference.md) for the profile facts.
Do not silently expand a reduced exercise into the full research stack.
Register only services present in the admitted scenario.

## Readiness Proof

On each approved host, inspect the installed versions and project state:

```shell
lilrae --version
lilrae lab status
lilrae lab info
node --version
npm --version
```

Then complete the real learner tool calls and browser checks.
Record the Kali identity, bounded authentication attempts, and correlated SSH alerts.
Keep canary proof separate from each participant seat's proof.
A connected MCP process, tool list, or HTTP 200 alone is insufficient.
Do not assign a host until its required operations pass.

## Student Distribution

Use only the event's approved private assignment channel.
Give each participant their own URL, account, and authentication instructions.
Do not publish a bundle containing every participant credential.
If an assignment service is proposed, obtain approval before deploying it or sending data to it.
Keep provider credentials out of images, handouts, and shared state.
Test the exact participant sign-in path before admitting the host.

## During The Event

Keep the admitted fleet stable.
Withdraw an affected assignment before repair or replacement.
Repeat its readiness proof after a change.
If a host-level repair applies to the fleet, verify every affected host before reassignment.
Keep the private instance and assignment ledger current.
Do not add services or relax access checks under event pressure.

## Wind Down

Withdraw participant assignments and close their agents.
Stop each lab through its own project lifecycle.
For cloud resources, review the exact IDs in the approved event ledger before deletion.
Terminate only event instances and verify their final state.

Audit volumes, images, snapshots, network interfaces, public addresses, security groups, DNS, certificates, IAM resources, and assignment services.
Remove event credentials and provider authentication state through their approved handling procedure.
Restore reused hosts to their recorded baseline instead of terminating them.
See [historical teardown](hosted-backup-seats.md#teardown) only for that pinned event recipe.
Expected result: no event cost drivers, public listeners, or participant access remain.

## Lessons Learned

Compare the final state with the pre-event ledger.
Record non-secret proof, failures, repairs, and unresolved operating decisions.
Use [the pinned trial reference](hosted-backup-reference.md) for historical observations.
Do not describe those observations as current qualification.
