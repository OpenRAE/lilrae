# Optional Windows endpoint reference

This endpoint is a separately managed Windows VM.
Normal LilRAE startup does not create it.
The scripts in `containers/windows-victim/` configure an existing endpoint.
The [setup guide](https://github.com/OpenRAE/lilrae/blob/dev/containers/windows-victim/README.md) gives the operating steps.

## Resources and installation limits

The earlier setup proposal allowed 4–6 GB RAM, two vCPUs, and at least 40 GB disk.
The reverse-engineering orchestrator estimates 30 to 60 minutes and 20 to 25 GB for its tool set.
These are historical planning estimates, not current qualification measurements.

Several scripts download mutable upstream releases.
This directory does not give an offline, reproducibly pinned Windows image.
Installer completion does not establish compatibility between downloaded releases.
A reboot can be necessary for build tools and WDK.

## Script selection

| Script | Selected installation or default |
| --- | --- |
| `setup-ssh.ps1` | Windows OpenSSH service |
| `setup-wazuh-agent.ps1` | Wazuh 4.12.0 MSI. Manager default `172.20.0.10` |
| `join-domain.ps1` | Domain `techvault.local`, DNS `172.20.2.10`, and dummy lab credential defaults |
| `enable-rdp.ps1` | Optional Remote Desktop access |
| `setup-sysmon.ps1` | Sysmon and its selected configuration |
| `setup-vs-buildtools.ps1` | Visual Studio 2022 C++ build tools and Windows SDK |
| `setup-wdk.ps1` | Windows Driver Kit. Requires the build tools first |
| `setup-ghidra.ps1` | Ghidra 11.3.1 and JDK 17 |
| `setup-x64dbg.ps1` | x64dbg/x32dbg debugger |
| `setup-sysinternals.ps1` | Sysinternals tools |
| `setup-python-re.ps1` | Python 3.12.8 and declared reverse-engineering libraries |

`setup-re-tools.ps1` runs the six reverse-engineering installers in dependency order.
Its switches are `SkipBuildTools`, `SkipWdk`, `SkipGhidra`, `SkipX64dbg`, `SkipSysinternals`, and `SkipPython`.
Wazuh event collection and domain membership must have separate runtime verification.
A successful ping or service process does not establish either result.

## Network and MCP limits

A new macvlan network does not automatically attach this VM or connect it to an existing Docker bridge.
The historical `172.20.3.10` address is not an automatically provisioned endpoint.
The selected lab's admitted addresses and actual routes govern connectivity.

There is no dedicated Windows MCP server in this repository.
The admitted red MCP can reach an authorized Windows target through its existing tool boundary.
Installed Kali tools and network reachability determine available operations.
The historical technique list does not establish tool installation, implemented techniques, or detection coverage.

## Source record

The [earlier proposal](https://github.com/OpenRAE/lilrae/blob/dev/containers/windows-victim/records/setup-2026-11-06.txt) keeps revision `28fc8f18`.
Status reviewed: 2026-11-06.
