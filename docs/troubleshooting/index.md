<a id="troubleshooting"></a>

# Recover A Lab

Use this guide when a project reports a startup, access, or teardown failure.
You need its project directory and authorized operator access on an approved lab machine.
Do not run lab operations or behavior tests on the developer workstation.
Retain required evidence before changing state.

## Quick Checks

From the affected project, inspect its configuration and runtime:

```shell
lilrae config validate
lilrae lab status
lilrae lab info
lilrae container list
```

Read the final startup result for the failed component and proposed action.
Inspect only a container returned by the project list:

```shell
lilrae container logs <container-name> --tail 50
```

Expected result: a named failure and bounded evidence for the next task.
Do not include private configuration, keys, credentials, or authentication headers in support reports.

## Common First-Run Problems

### A service URL does not open

Run `lilrae lab info` again and use its current service URL.
Check whether the selected scenario includes that service.
For a remote daemon, verify reachability on the remote host.
Inspect the service's project-scoped logs if access still fails.

Use the project's generated trust root and reported service hostname.
Do not disable TLS verification or accept an unexplained certificate warning.
Expected result: access uses the actual service endpoint and trusted certificate.

### Startup reports insufficient resources

Check the engine's memory allocation against the [host requirements](../getting-started/host-requirements.md).
Allocate sufficient resources for the selected pack before retrying startup.
To choose a smaller pack, configure its identity and verify its catalog first.
`lilrae lab scenarios` lists the configured pack; it is not a menu of all installed packs.

For a kernel-limit failure, apply the exact diagnostic on the selected engine host.
Docker Desktop manages its Linux VM settings separately from the physical host.
Expected result: the named preflight passes on the next start.

### A container shell fails

Confirm the target with `lilrae container list`.
Open only a container in that project:

```shell
lilrae container shell <container-name>
```

The default tries `/bin/bash`, then `/bin/sh`.
Use `--shell` only when you need another installed shell.
Kali shell access is refused while required session capture runs.
Use the admitted captured tool route instead.
See [Kali host access](../components/kali-redteam.md#host-access).

### MCP servers are unavailable

Check the startup report's MCP phase and the scenario's realized services.
Run the client from the project directory so it can find its generated configuration.
Inspect its connected servers and exact tool inventory.
For released projects, let `lilrae lab start` own builds and configuration.
For source development, use the existing `mcp/build-all-mcps.sh` build on the approved development path.
See the [MCP reference](../reference/mcp.md) for enabled and built surfaces.

## Project-Scoped Recovery

Close affected agents and preserve required logs.
Retry a volume-preserving lifecycle:

```shell
lilrae lab stop
lilrae lab start
```

Expected result: the configured scenario starts with its retained data.
For an explicit SDL fixture, repeat the original `--scenario-path` option.

If a full reset is intended, retain required data first:

```shell
lilrae lab stop -v
lilrae lab start
```

The destructive stop asks for confirmation and removes all project volumes.
It does not prune the Docker daemon.
Do not use daemon-wide prune commands or raw Compose startup for recovery.
`lilrae kill` is emergency termination, not normal teardown.

### `lilrae lab stop -v` reports pending host cleanup

Read the reported failure class before retrying.
`[lifecycle-docker-teardown-failed]` means Docker teardown failed; host cleanup was not attempted.
Resolve the Docker error first.
`[lifecycle-host-cleanup-pending]` means volumes are gone but a listed host action remains.
Use the [cleanup reason reference](diagnostics.md#host-cleanup-reasons) to identify its repair.

After resolving the cause, repeat:

```shell
lilrae lab stop -v --yes
```

Use `--yes` only when the destruction decision still applies.
Completed actions are not repeated; pending actions retry.
Do not delete or edit `.aptl/lifecycle/` records to hide an error.
Expected result: teardown completes and no host cleanup remains pending.

## Platform Issues

### Linux

If Docker denies operator access, check the approved daemon access policy.
If that policy uses the Docker group, an administrator can add the operator:

```shell
sudo usermod -aG docker "$USER"
```

Sign out and back in, then check access again.
Docker-group membership grants root-equivalent control over that daemon host.

### macOS

Start the selected Docker VM before retrying.
Allocate enough VM memory for the selected scenario.
If another service owns a default port, use the remapped URL from `lilrae lab info`.
Do not disable unrelated host services merely to reuse a copied port number.

### A container is `Up` but reports `unhealthy`, blocking `lilrae lab start`

Use the project list to identify the affected container.
On the approved lab host, inspect its memory limit, exit state, and restart count:

```shell
docker inspect <container-name> --format 'Mem={{.HostConfig.Memory}} OOMKilled={{.State.OOMKilled}} RestartCount={{.RestartCount}}'
lilrae container logs <container-name> --tail 50
```

Check for repeated restarts, killed child processes, and service-specific errors.
`OOMKilled=false` does not exclude a killed child process.
A surviving PID 1 also does not establish that the intended daemon is alive.
Use a project container shell to inspect its service logs and process status.

If memory is insufficient, increase available resources or correct the owning scenario's supported resource declaration.
Do not edit the root `docker-compose.yml` as a substitute for the admitted scenario model.
Expected result: the intended service starts and passes authenticated readiness.

### Shuffle exits during OpenSearch initialization

Inspect `lilrae container logs aptl-shuffle-backend --tail 50` when that container belongs to the project.
Check datastore readiness, resources, and credentials.
The default `on-failure` policy retries an error exit when the scenario leaves restart policy open.
An authored restart policy takes precedence.
It does not repair datastore failures or restart an orderly exit.
Repeat normal startup only after resolving the cause.

### `lilrae lab start` fails because a Wazuh service did not become ready

Read the diagnostic phase and reason.
The [Wazuh diagnostic reference](diagnostics.md#wazuh-readiness) defines these fields.

For `transport`, inspect the named container's logs, restarts, and API listener.
In an existing manager container, inspect `/var/ossec/bin/wazuh-control status` through its project shell.
If the API is absent, use `wazuh-control start` there and investigate the daemon's exit cause.
The normal authenticated readiness check must still pass.
Certificate generation alone does not establish API readiness.

For `authentication`, compare the private configured credentials with the retained service state.
If data must remain, restore the original credential rather than resetting the volume.
For `manager_status`, inspect the manager's daemon status and service logs.
Expected result: the API authenticates and reports running manager daemons.
Do not disclose credentials in a support report.

### `lilrae lab start` fails with "Existing network aptl_aptl-... does not match realized network"

Use a project-scoped stop to remove stale project networks, then retry:

```shell
lilrae lab stop
lilrae lab start
```

If `lifecycle-owner-busy` appears, wait for the active operation to finish.
If cleanup observation fails, restore the selected local or SSH Docker connection and repeat stop.
Do not prune unrelated networks.
Expected result: the next realization creates networks with the required ownership labels.

### An older TechVault seat stops before it is ready

Old images can contain TheHive's expired trial.
Current releases omit TheHive and Cortex.
Retain required guest files before adopting a replacement image.
An image update deletes overlay data.

As the seat owner, stop it.
Then use the administrator rescue path if files must be recovered:

```shell
lilrae seat stop --seat-root <seat-root>
sudo lilrae seat rescue --seat-root <seat-root>
```

The host needs `virt-rescue` for this task.
Exit rescue before updating and starting the same selected seat in event mode:

```shell
lilrae seat update --seat-root <seat-root> --desktop-mode event
lilrae seat start --seat-root <seat-root> --desktop-mode event
```

See the [seat launcher](../reference/appliance-seat-launcher.md) for seat selection and image trust requirements.
Expected result: the replacement image starts without the retired services.
Their case and analyzer state is not restored automatically.

### `lilrae lab start` reports an unowned search index

The diagnostic names an index that lacks the expected content ownership marker.
LilRAE refuses to adopt, delete, or overwrite that index.
Current adapters map no schema to a native index, so this is a conditional recovery path.

Keep the failed-start containers and retained volumes while investigating.
Open a project shell in the named container and query read-only:

```shell
lilrae container shell <container>
```

From that shell, for a service with the reported local HTTP endpoint:

```shell
curl -fsS 'http://localhost:9200/<index>/_count'
curl -fsS 'http://localhost:9200/<index>/_mapping'
```

Use the service's configured TLS and authentication if required.
Before resetting, back up every service whose data must remain.
Follow [Back up a conflicting search index](search-index-backup.md) for the Elasticsearch snapshot procedure.
A filesystem copy of its data directory is not a supported snapshot.

Only after successful restoration checks or an explicit data-discard decision, reset the project:

```shell
lilrae lab stop --volumes
```

Confirm the warning, then repeat the original scenario start.
Expected result: a new disposable index can receive its ownership marker.
Restoring the old index unchanged also restores its unowned state.

### macOS: Docker Desktop uninstall leftovers

Use this task after switching from Docker Desktop to Colima or Homebrew Docker.
Check `~/.docker/cli-plugins/` for links to the removed application.
After installing the intended plugins, replace the two known links:

```shell
mkdir -p ~/.docker/cli-plugins
ln -sf "$(brew --prefix docker-buildx)/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
ln -sf "$(brew --prefix docker-compose)/bin/docker-compose" ~/.docker/cli-plugins/docker-compose
```

Review other broken links individually before removing them.
If Docker cannot find `docker-credential-desktop`, inspect its `credsStore` setting in `~/.docker/config.json`.
Replace or remove only the obsolete helper setting using your approved credential-storage policy.
Keep unrelated registry authentication and contexts.
Expected result: Compose, Buildx, and registry authentication use installed tools.

### WSL2

Save work in all WSL sessions before restarting WSL.
From Windows, run:

```powershell
wsl --shutdown
```

Configure `%UserProfile%\.wslconfig` with enough memory and processors for the selected scenario.
Restart the Docker Desktop WSL2 backend and check its resources.
An 8 GB allocation is insufficient for full TechVault.
