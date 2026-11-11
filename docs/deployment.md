<a id="deployment-and-lifecycle"></a>

# Deploy And Manage A Lab

Use this guide for operating tasks after installation.
Start with an initialized project, its selected pack, and permission to operate the chosen Docker engine.
Use an approved isolated VM or dedicated lab host.
Do not run lab operations or behavior tests on the developer workstation.

## Released Local Project

Complete [Installation](getting-started/installation.md) to create the project.
Open its `aptl.json` and set the existing scenario object:

```json
"scenario": {"source": "env-pack", "identity": "techvault"}
```

From that project, check and start the selected pack:

```shell
lilrae config validate
lilrae lab scenarios
lilrae doctor
lilrae lab start --scenario techvault
```

Expected result: the final startup report passes required readiness checks.
Resolve each failed preflight before repeating startup.
Use the printed diagnostic for a degraded result.
Do not substitute `docker compose up` for this operation.
It omits scenario admission, generated state, readiness, and run recording.

## Source Checkout

Follow the [contribution setup](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md#development-setup) for a source installation.
Use the checkout as the project directory.
Do not run `lilrae lab init` over the checkout.
Run the lab and targeted tests only in CI or an approved isolated VM.

## Disposable Appliance

Follow the [seat launcher guide](reference/appliance-seat-launcher.md) for image verification, startup, update, and rollback.
Use the signed launch inputs and trust anchors required by that release.
Expected result: the launcher admits a disposable KVM guest and reports its participant access.
Offline startup refuses missing staged inputs instead of downloading or building replacements.

## Configuration

From the project, inspect and validate the non-secret configuration:

```shell
lilrae config show
lilrae config validate
```

Expected result: the strict `aptl.json` configuration validates.
Select packs with [Install a scenario pack](getting-started/installing-packs.md).
Keep credentials in their declared private sources, outside `aptl.json`.
Generated `.env` and `.mcp.json` files must not be committed.

### Scenario Environment Grants

Use this task when an admitted pack declares a secret without an authored value.
First identify the exact pack ID, consuming node, variable, and classification in its SDL.
Check the [environment-binding rules](getting-started/environment-bindings.md) before choosing a source.

Add the grant to `deployment.environment_grants` in `aptl.json`:

```json
{
  "deployment": {
    "environment_grants": [
      {
        "pack": "example-pack",
        "consumer": "webapp",
        "variable": "DB_PASSWORD",
        "source": {"kind": "process-environment", "variable": "LAB_DB_PASSWORD"}
      },
      {
        "pack": "example-pack",
        "consumer": "worker",
        "variable": "API_TOKEN",
        "source": {"kind": "project-env-file", "variable": "WORKER_API_TOKEN"}
      }
    ]
  }
}
```

Replace these example names with declarations from your admitted pack.
Provide a nonempty source value through the named process environment or private project `.env` key.
Do not put the value in the grant.
Validate the configuration, then start the lab.
Expected result: only the named consumer receives the binding.
Missing sources and invalid authority stop preflight before scenario resource mutation.

For a project-tree scenario, use authored fixtures or declared generated-artifact consumers.
Pack grants do not apply without an acquired pack identity.

## Observe A Deployment

Inspect the project after startup:

```shell
lilrae lab status
lilrae lab info
lilrae container list
```

Use the URLs and credential locations from your own `lab info` output.
For remote Docker, check reachability on the remote daemon host.
The [execution-boundary explanation](getting-started/execution-boundaries.md) describes the separate host observation.

For a container returned by the list, inspect bounded logs or open a shell:

```shell
lilrae container logs <container-name> --tail 50
lilrae container shell <container-name>
```

Expected result: the commands inspect only a project-owned container.
A running container alone does not prove readiness.
Use the final startup result for that decision.

## Host Docker Socket Access

Before admitting a scenario, review its declared Docker control authority.
A socket holder has root-equivalent control over the daemon host.
For TechVault, verify that the admitted worker manager is the intended authority.
See the [socket authority explanation](getting-started/environment-bindings.md#docker-socket-authority).
Do not add socket mounts to bypass model validation.

## Manage The Lifecycle

For an ordinary end of session, stop the project:

```shell
lilrae lab stop
```

Expected result: project containers and networks are removed while volumes remain.
Wait for any active lifecycle operation before retrying a busy project.
Mutations share one project lock.

If you intend to destroy all project volume data, retain required evidence first.
Then run:

```shell
lilrae lab reset
```

Read and confirm the destruction warning.
Expected result: project containers, networks, volumes, and pending host cleanup are removed.
Configuration, `.env`, keys, certificates, and run records remain, except host state named by cleanup records.
`lilrae lab stop -v` performs the same teardown.
For a clean boot in one operation, use `lilrae lab start --clean` with the selected scenario.

If host cleanup remains, follow [pending host cleanup](troubleshooting/index.md#lilrae-lab-stop-v-reports-pending-host-cleanup).
Do not delete lifecycle records or use daemon-wide prune commands.
Use `lilrae kill` only for emergency process or container termination.
It does not replace normal teardown or reset credentials.

## Automatic Lifecycle Policy

Use this task when the project needs time-to-live, idle, or scheduled provisioning rules.
Inspect the installed command options first:

```shell
lilrae lab policy --help
lilrae lab enforce --help
lilrae lab monitor --help
```

Configure the intended `lifecycle_policy` in `aptl.json` and validate it.
Use the installed help to select enforcement or monitoring options.
Expected result: policy actions use the same project lock as manual operations.
For policy behavior and failures, see [ADR-045](adrs/adr-045-ephemeral-lifecycle-policy-enforcement.md).

## Recovery

Retain logs and required evidence before recovery.
From the affected project, try a volume-preserving restart:

```shell
lilrae lab stop
lilrae lab start
```

Expected result: the selected configuration starts with its retained data.
If it still fails, use [Troubleshooting](troubleshooting/index.md) for the named failure.
Reset volumes only after an explicit backup or data-discard decision.
