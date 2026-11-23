# Set Up A Workshop Seat

Use this guide to prepare the released full-TechVault seat for the [learner tutorial](walkthrough.md).
You need a dedicated Linux/KVM lab host, an approved signed desktop image, and permission to acquire that image.
Install the host tools and reserve the resources in the [seat launcher prerequisites](../reference/appliance-seat-launcher.md#prerequisites).
Use an approved isolated test environment for qualification.
Do not run seat operations, lab commands, or tests on the developer workstation.

The result is a private desktop seat with working red and blue terminals, a Wazuh bookmark, and a proven learner route.
The reduced guided-purple fixture is separate historical research material.
See [the workshop reference](reference.md) for that distinction.

## Start The Seat

As the assigned host user, start the approved image in event mode:

```shell
lilrae seat start --desktop-mode event
lilrae seat status
lilrae seat open-kiosk
```

On first acquisition, inspect and approve the launcher prompt only for the intended image source.
Do not use an alternate registry or trust key without approval.
Expected result: signature verification and startup succeed, then the browser opens the private desktop.
The first-boot service starts the guest lab.
Event mode gives the desktop account neither sudo nor Docker-group access.

If a selected older image rejects desktop mode, follow the [image update procedure](../reference/appliance-seat-launcher.md#updates-are-never-forced).
Do not silently fall back to a different privilege or access contract.
Keep the reported seat identity and selected image digest in the private event ledger.
Each launching host account owns its private seat state.

## Prepare Agent Access

Open the supplied red terminal inside the guest desktop.
Complete provider authentication through the event's approved account boundary.
Do not copy another user's provider state or bake credentials into an image.
Inspect the connected MCP tools before generating activity.

Confirm that red has `aptl-red` and `kali_run_command`.
Close the red agent and its MCP processes before opening the supplied blue terminal.
Confirm that blue has `aptl-indexer`, `aptl-wazuh`, and the full pack's admitted defensive tools.
The tutorial uses only indexer and Wazuh operations on that side.
Do not combine red and blue tools in one client environment.

Use the desktop's generated service guide and login information for the Wazuh bookmark.
Do not copy a fixed localhost port or password from an old handout.
See [the participant desktop contract](../reference/appliance-seat-launcher.md#participant-desktop) for the generated files and service routes.

## Prove Readiness

Check that the seat start completed its required guest and boundary checks.
Then complete the [learner tutorial](walkthrough.md) through the actual tools and browser route.
Verify the authorized victim address before assigning it to learners.
Record a successful Kali command, bounded failed logins, and correlated indexer and Wazuh alerts.
Record source address, target, and event times.
A tool listing, login page, or HTTP 200 alone is insufficient.

For candidate qualification, also follow [manual release QA](../testing/smoke-test-plan.md).
Use only targeted checks in the approved VM or CI.
If any required check fails, withdraw the seat and investigate before assignment.
Passing one workshop session does not qualify every image or host.

## Recover A Session

Withdraw the affected assignment and close its agents.
As the seat's host owner, stop and restart the same selected seat:

```shell
lilrae seat stop
lilrae seat start
lilrae seat open-kiosk
```

Expected result: the selected image restarts with its retained overlay and privilege mode.
Repeat the learner readiness proof before reassignment.
Use [Troubleshooting](../troubleshooting/index.md) for guest service failures.
For guest-root diagnosis, use the documented host-administrator rescue path after stopping the seat.
Do not grant the participant Docker or sudo access as a workaround.

## Clean Up

Retain only the approved non-secret exercise results.
Close the assigned agents, browser session, and MCP processes.
As the host owner, stop the seat:

```shell
lilrae seat stop
```

For reassignment, retain required data before destroying the overlay:

```shell
lilrae seat reset --desktop-mode event
```

Reset destroys overlay data without a separate destruction prompt.
Review the retention decision before running it.

Expected result: the old overlay is destroyed and the replacement uses event mode.
See the [seat lifecycle reference](../reference/appliance-seat-launcher.md#reset-and-recovery) for reset and restart behavior.
Repeat readiness and provider-access setup before the next participant uses it.
The cached signed base image remains available for reuse.
For inner lab cleanup, use [Manage The Lifecycle](../deployment.md#manage-the-lifecycle) through authorized management access.
