<a id="prerequisites"></a>

# Prepare The Lab Host

Use an approved isolated VM or a dedicated, rebuildable lab machine.
You need permission to install host tools and change Docker settings.
The result is a host ready for CLI installation and prerequisite checks.
Do not run the lab or behavior tests on the developer workstation.

## Requirements

Compare your machine with the [host requirements](host-requirements.md).
Allocate resources for the selected scenario before starting Docker.

## Install Docker

Install Docker through your organization's approved package source.
Include Docker Compose and Buildx.
For native Linux, check the server version and cgroup mode after installation:

```shell
docker version --format '{{.Server.Version}}'
docker info --format '{{.CgroupVersion}}'
docker info --format '{{json .SecurityOptions}}'
```

Expected result: Engine 28.0 or newer, cgroup `2`, and no rootless daemon.
For systemd nodes, the daemon must also have no `userns-remap` setting.
Docker access permits control of the daemon's host.
Grant that access only to the lab operator.

For Docker Desktop, start its Linux engine and allocate the selected scenario's memory.
On Windows, enable the WSL2 backend.

For an approved Colima installation on macOS, install its CLI plugins:

```shell
brew install docker docker-buildx docker-compose colima
mkdir -p ~/.docker/cli-plugins
ln -sf "$(brew --prefix docker-buildx)/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
ln -sf "$(brew --prefix docker-compose)/bin/docker-compose" ~/.docker/cli-plugins/docker-compose
```

Start Colima with resources sufficient for your selected scenario.
Check the active context with `docker context ls`.
Colima transport support does not establish containment or full-TechVault qualification.

## System Config

After project creation, run `lilrae doctor` from that project.
If the selected adapter requires a kernel setting, follow the diagnostic for the engine host.
For example, an adapter can require this native Linux minimum:

```shell
sudo sysctl -w vm.max_map_count=262144
```

Use your host's approved configuration method to retain the setting after reboot.
Do not apply a physical-host sysctl for Docker Desktop's managed Linux VM.
For a remote daemon, verify the setting on the remote engine host.

Use ports reported by `lilrae lab info` after startup.
LilRAE can remap an occupied default port.
Pin a port only through its documented `APTL_HP_*` setting.

## Python environment

Install pipx and a [supported Python interpreter](host-requirements.md#tools-and-resources) through an approved source.
Use [Installation](installation.md) to install the released CLI in pipx.
Do not install it into an externally managed system Python.

For source development, follow the [contribution setup](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md#development-setup).
Activate that virtual environment in each new terminal.
Do not run tests or the lab on the developer workstation.

## Verify

On the approved lab machine, check the installed tools:

```shell
docker compose version
docker buildx version
docker ps
node --version
npm --version
command -v ssh-keygen
```

Expected result: Docker responds and the required client tools are available.
The final command prints the key generator path without creating a key.
After [project creation](installation.md#create-a-lab-project), run `lilrae doctor` for the project-specific checks.

## Tested execution profiles and limits

Read [Execution boundaries](execution-boundaries.md) before choosing a deployment path.
Use the [qualification records](host-requirements.md#qualification-records) to distinguish measured results from unverified combinations.
A successful boot does not establish host containment.
