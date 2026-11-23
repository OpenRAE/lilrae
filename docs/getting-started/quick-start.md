# Run Your First Lab

In this tutorial, you start TechVault, inspect its services, create a local event, and stop the lab.
Use an approved isolated test VM or dedicated, rebuildable lab machine.
Do not run these commands on the developer workstation.

Start with the released CLI and a new project from [Installation](installation.md).
Open a terminal in that project directory.
Keep the generated credentials, keys, and run data private.

## Choose The Execution Boundary

Confirm that you can discard the lab machine and that its network permits this exercise.
Do not use a machine with unrelated workloads or credentials.
For the boundary labels and their limits, see [Execution boundaries](execution-boundaries.md).
For a disposable KVM seat, follow the [seat launcher](../reference/appliance-seat-launcher.md).

## Check The Host

Check the project and selected Docker engine:

```shell
lilrae doctor
```

Expected result: no `FAIL` checks.
Warnings can remain, including resource or remote-host checks that require your review.
Read each warning before continuing.
If a check fails, follow its printed action and repeat the check.
See [Prerequisites](prerequisites.md) for setup tasks.

## Choose A Scenario

Open `aptl.json` in your editor.
Set its existing `scenario` object to:

```json
"scenario": {"source": "env-pack", "identity": "techvault"}
```

Save the file, then inspect the configured catalog:

```shell
lilrae lab scenarios
```

Expected result: the installed pack validates and the catalog lists `techvault`.
A new project has no selected identity.
If the pack is unavailable, follow [Install a scenario pack](installing-packs.md).

## Start And Verify The Lab

Start TechVault:

```shell
lilrae lab start --scenario techvault
```

Read the final result before continuing.
Expected result: startup completes its required readiness checks.
If it reports degradation or failure, use the named diagnostic in [Troubleshooting](../troubleshooting/index.md).

Inspect the running project:

```shell
lilrae lab status
lilrae lab info
```

Expected result: project containers appear, with access information for the realized services.
A running container alone does not establish readiness.

## Inspect The Running Lab

List the realized containers:

```shell
lilrae container list
```

Find the victim container in this list.
For the standard TechVault victim, open a shell:

```shell
lilrae container shell aptl-victim
```

If that name is absent, stop here and check your selected pack.
Do not substitute a container from another project.
Expected result: an interactive shell inside the lab victim.

## Generate Safe Test Activity

In the victim shell, create one local log message and return to the project terminal:

```shell
logger "APTL first-lab test event"
exit
```

Expected result: the command completes and your project terminal returns.
This message is a telemetry check; it need not create a security alert.
Do not run exercise commands against systems outside this range.

## Inspect Results

Read the service access information again:

```shell
lilrae lab info
```

Open the reported Wazuh Dashboard URL.
Use the reported project credential locations.
Find recent victim events and compare their time with your log message.
If the event is absent, inspect collection status before continuing.
Use the [workshop tutorial](../workshop/walkthrough.md) for an exercise with a defined SSH alert.

List the recorded scenario runs:

```shell
lilrae runs list
```

If a run is listed, copy its ID into these commands:

```shell
lilrae runs show <run-id>
lilrae runs path <run-id>
```

Expected result: run metadata and its local evidence location.
Runtime health, service events, and archived run evidence answer different questions.
For export fields, see the [evidence bundle reference](../reference/evidence-bundle-export.md).

## Stop Or Reset The Lab

Return to the project terminal and stop the lab:

```shell
lilrae lab stop
```

Expected result: project containers and networks are removed; volumes remain available for another session.
For this tutorial, normal stop is sufficient.
If you intend to destroy volume data, follow [Manage The Lifecycle](../deployment.md#manage-the-lifecycle).
Keep any required evidence before a reset.

## Continue From Here

- [Deploy and manage a lab](../deployment.md)
- [Workshop tutorial](../workshop/walkthrough.md)
- [CLI reference](../reference/cli.md)
- [MCP reference](../reference/mcp.md)
- [Web reference](../reference/web.md)
- [Troubleshooting](../troubleshooting/index.md)
