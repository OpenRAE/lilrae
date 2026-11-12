# CLI Reference

The `lilrae` command is the supported control plane for a lab project. Project-root invocation uses the directory created by `lilrae lab init`.
Commands with a project-directory option can select another project explicitly.

Installed help describes the exact options in that release:

```shell
lilrae --help
lilrae <command> --help
lilrae <command> <subcommand> --help
```

The `aptl` command is a deprecated alias of `lilrae`. It runs the same
commands and writes one deprecation notice to stderr.
The candidate still registers it despite the planned 10.0.0 removal target. See [Move from the aptl command](../getting-started/installation.md#move-from-the-aptl-command).

## Command Groups

| Command | Supported behavior |
| --- | --- |
| `lilrae doctor` | Examine the host and the selected Docker engine before a start. It changes nothing. |
| `lilrae lab` | Initialize, select, start, examine, validate, stop, and clean a lab project. |
| `lilrae config` | Show and validate the strict, non-secret project configuration. |
| `lilrae container` | List realized project containers and open bounded logs or shells. |
| `lilrae runs` | List, examine, locate, export, and verify project run evidence. |
| `lilrae web` | Serve the local operator UI and API through the supported single-origin boundary. |
| `lilrae kill` | Terminates processes and containers in an emergency. It does not do normal teardown. |
| `lilrae experiment` | Admit experiment inputs and persist an immutable trial plan. It does not execute the plan. |
| `lilrae seat` | Run one disposable appliance seat from a published VM image. |
| `lilrae mcp-access` | Materialize authorized MCP client access for a participant or appliance seat. |
| `lilrae containment` | Run one command in the shared containment wrapper. See the [containment interface](containment-interface.md). |

`lilrae --version` prints the installed CLI version. Hidden implementation flags
and direct calls into Python modules are not supported interfaces.

## First-Lab Commands

| Task | Command | Result |
| --- | --- | --- |
| Create a project | `lilrae lab init <directory>` | Materializes the lab assets bundled with the installed release. |
| Examine the host | `lilrae doctor` | Reports each unmet prerequisite with its fix and exits with status 1 when a check failed. |
| Discover scenarios | `lilrae lab scenarios` | Lists validated identities from the installed environment pack. |
| Start | `lilrae lab start --scenario <id>` | Validates and realizes the scenario, starts services, and reports readiness. |
| Examine state | `lilrae lab status` | Reports the current project lifecycle and realized containers. |
| Discover access | `lilrae lab info` | Prints runtime URLs, remapped ports, usernames, and credential locations. |
| List containers | `lilrae container list` | Lists containers owned by the realized project. |
| Examine runs | `lilrae runs list` | Lists recent run records in the project-local run store. |
| Stop | `lilrae lab stop` | Stops the project and keeps volumes. |
| Reset | `lilrae lab reset` | After confirmation, removes the project's containers, networks, and volumes and finishes pending host cleanup. `lilrae lab stop -v` does the same. |

To run one trial that a trial SDL declares, add `--run-id`, `--attempt-id`, and
`--deadline` to `lilrae lab start`. See [Lab start trials](lab-start-trials.md).

The CLI result reports the admitted startup outcome.
A running container alone does not establish lab readiness.
Generated configuration and observed endpoints belong to the supported startup path.
The control plane owns scenario realization, generated configuration, port
selection, readiness, MCP setup, and run recording.

## Exit Status And JSON Output

`lilrae doctor`, `lilrae lab start`, `lilrae lab status`, `lilrae lab stop`, and
`lilrae lab reset` share the exit status contract below. Regression tests examine these results.

| Exit status | Meaning |
| --- | --- |
| `0` | The operation returned its stated result. Doctor found no failed check. Startup returned an outcome. Status observed the project. Stop or reset completed. |
| `1` | A doctor, start, state-observation, stop, or reset operation failed. A reset with pending host cleanup also returns this status. |
| `2` | The command received invalid usage. Examples include unknown options and conflicting selectors. JSON cleanup requires `--yes` for `--clean`, `--volumes`, or `lilrae lab reset`. |

A start that ends `degraded_usable` or `degraded_unusable` still exits with
status 0. The outcome field distinguishes these degraded results. If the operator declines confirmation for `--clean`, `--volumes`, or `lilrae lab reset`, the command prints `Aborted.`.
It changes nothing and exits with status 0.

With `--json`, `lilrae doctor`, `lilrae lab start`, `lilrae lab stop`, and
`lilrae lab reset` print one JSON object on standard output, and start progress
goes to standard error.
Exit status 2 prints no JSON object. The usage error goes to standard error.
Each object has `command`, `schema_version` (now `1`), and `ok`, which is
`true` exactly when the exit status is `0`. A new field keeps the schema
version. A field removal or type change raises it.

The JSON and text outputs
render the same result. The renderer first redacts free-form text (`error`, `message`, `operator_action`,
`summary`, and `fix`), so a credential-shaped value prints
as `[REDACTED]`.

| Command | Fields after `command`, `schema_version`, and `ok` |
| --- | --- |
| `lilrae doctor --json` | `counts`, `checks`. |
| `lilrae lab start --json` | `outcome`, `error`, `execution_boundary`, `admission_seconds`, `diagnostics`, `published_ports`, `published_ports_observed`, `residue`, and `trial` for a trial start. |
| `lilrae lab stop --json` | `volumes`, `error`. |
| `lilrae lab reset --json` | `containers_found`, `networks_found`, `error`. |

| Field | Contract |
| --- | --- |
| `counts` | This field gives the number of doctor checks per `pass`, `warn`, `fail`, and `skip` status. |
| `checks` | This field contains doctor entries with `id`, `status`, `summary`, and `fix`. |
| `outcome` | `ready`, `degraded_usable`, `degraded_unusable`, or `failed`. |
| `error` | This field is a string or `null`. |
| `execution_boundary` | This field is an observed boundary object or `null`. |
| `admission_seconds` | This field is a number or `null`. |
| `diagnostics` | This field contains entries with `step`, `component`, `impact`, `severity`, `message`, and `operator_action`. |
| `published_ports` | This field contains entries with `service`, `default_port`, `host_port`, `protocols`, `host_ip`, and `remapped`. |
| `published_ports_observed` | This field states whether Docker reported the ports. |
| `residue` | This field is `null` or failed-start state with `container_count`, `network_count`, `teardown_requested`, and `torn_down`. |
| `trial` | This field is present only for a [trial start](lab-start-trials.md#exit-status-and-json-output). |
| `volumes` | This field states whether stop requested `--volumes`. |
| `containers_found`, `networks_found` | These fields give pre-reset counts for the recorded workspace project. They are `0` without a recorded project, or `null` for unavailable counts. |

`execution_boundary` is the observation behind the text summary's
`Execution boundary:` line. It carries its own `schema_version`,
`aptl.execution-boundary/v1`, and `transport`, `override_source`,
`daemon_runtime`, `host_containment`, `observation_status`, `host_os`,
`host_kernel`, `docker_version`, `containment_verified`, `profile_ref`, and
`evidence_refs`.

`published_ports` lists the host ports the text access summary reads. When the lab operates, they are the bindings Docker reports, and
`published_ports_observed` is `true`. When Docker reports none, the list is
the start-time port plan, which can name a port the scenario never published.
`published_ports_observed` is then `false`, and the text summary marks its
access locations as unverified. Service names use hyphens, so
`wazuh.dashboard` from the plan and `wazuh-dashboard` from Docker both appear
as `wazuh-dashboard`. A failed start reports an empty list, because its text
output has no access summary.

`lilrae lab status --json` keeps its existing output, the redacted range
snapshot with `timestamp`, `software`, `containers`, `wazuh_rules`, `networks`,
`config_hashes`, `services`, and `ssh`. It exits with status 1 when the
snapshot cannot be captured.

## Destructive And Emergency Operations

`lilrae lab reset` and `lilrae lab stop -v` are the supported full cleanup for one
project. They require confirmation unless the explicit non-interactive option
shown by `--help` is used. They destroy volume-backed lab data and finish
pending host cleanup, but do not prune unrelated Docker resources.

`lilrae lab start --clean` performs the same project-volume cleanup before a
new start. `lilrae kill` and its container option are emergency controls for
stuck MCP processes or lab containers. They are not a graceful stop, a data
reset, or a substitute for investigation of a failed readiness result.

A failed `lilrae lab start` keeps its containers and networks for diagnosis. The failure summary counts retained resources and names two recovery commands.

`lilrae lab stop` keeps volumes. `lilrae lab stop -v` removes managed volumes and destroys their data. Recovery commands include `--project-dir` when startup selected a project outside the current directory.
`--teardown-on-failure` stops failed-start containers and networks automatically. It keeps volumes.
See [recover a failed start](run-operations.md#recover-a-failed-start) for operating steps.

An appliance seat's guest readiness publication also runs under the start lock. Its failure reports residue and honors the option. Long-lived appliance access supervision
runs after that lock is released. Its later failures require explicit recovery.

Container removal destroys writable layers and container-local logs.
Retained volumes keep volume-backed data, with anonymous node
volumes. Disposable helpers still discard their temporary storage.

Anonymous volumes retained after their containers are removed are not
automatically reattached or removed by a later `stop -v`.
They require explicit data recovery or removal. Project cleanup never prunes unowned volumes.

The backend compensates for partial Compose startup and ownership-capture
failure even without the option. It removes attempted runtime and keeps
volumes. If ownership capture failed, retained volumes may need ownership
repair before another start or cleanup. The backend refuses uncertain ownership.

## Configuration And Secrets

See [Validate project configuration](project-configuration.md#configuration-and-secrets).
