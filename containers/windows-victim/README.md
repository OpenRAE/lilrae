# Windows 11 Victim VM

Use this How-to guide for the optional, separately managed Windows VM.
Normal LilRAE startup does not create this VM.
Before you select scripts or resources, read the [endpoint reference](../../docs/reference/windows-endpoint.md).
The [source record](records/setup-2026-11-06.txt) keeps the earlier setup proposal at revision `28fc8f18`.
Status reviewed: 2026-11-06.

## Prerequisites

Use an approved isolated test VM and an authorized Windows installation image.
Read the [resource and installation limits](../../docs/reference/windows-endpoint.md#resources-and-installation-limits).
Keep the VM outside production networks.

Examine each selected script before execution.
Make sure that the approved environment permits each selected download.

## Setup

### 1. Create the VM

Create the Windows VM with the approved hypervisor and image.
Select resources for the approved Windows image and selected tools.
Record the actual image, hypervisor, resource allocation, and network configuration.
Do not infer network connectivity from the old example.

### 2. Configure Networking

Choose an explicitly approved connection to the isolated lab.
Before you install integration services, examine routes, DNS, and return traffic.
Read the [network limits](../../docs/reference/windows-endpoint.md#network-and-mcp-limits).
Use the admitted domain controller and Wazuh manager addresses for the selected lab.

### 3. Run Setup Scripts

Open PowerShell as Administrator inside the approved VM.
Run only the selected integration scripts:

```powershell
.\setup-ssh.ps1
.\setup-wazuh-agent.ps1 -WazuhManagerIP '<reachable-manager-address>'
.\join-domain.ps1
.\enable-rdp.ps1
.\setup-sysmon.ps1
```

Before you join the domain, examine `join-domain.ps1` parameters and its dummy lab credential defaults.
Pass the admitted domain, DNS endpoint, and authorized lab account through the approved credential procedure.
Omit `enable-rdp.ps1` when RDP is not required.
After you install Sysmon, examine actual Wazuh event collection.

### 3b. Install Reverse Engineering Tools (Optional)

Examine the external downloads and disk allowance before installation.
Run the existing orchestrator for the selected tools:

```powershell
.\setup-re-tools.ps1
```

Use its skip switches to omit unwanted components:

```powershell
.\setup-re-tools.ps1 -SkipWdk -SkipBuildTools
```

For individual installation, select the script from the [script reference](../../docs/reference/windows-endpoint.md#script-selection).
Before you run the script, examine its parameters.
Reboot when the selected installer requires it.
Examine installed versions before exercise use.

### 4. Verify Integration

1. Examine SSH from an authorized lab peer to the VM's actual address.
2. If RDP is enabled, verify it with the intended lab account.
3. Make sure that the endpoint appears in the Wazuh agent list.
4. Generate a bounded Windows event and confirm delivery under that agent identity.
5. If Sysmon is installed, verify its event channel separately.
6. Examine installed tool paths and versions before an exercise.

Keep credentials out of command arguments and shared evidence.

## Attack Scenarios

Use only the explicitly authorized lab exercise.
Examine the [historical proposal](records/setup-2026-11-06.txt) only as planning evidence.
Record the selected scenario, bounded action, observed effect, and cleanup.

## MCP Integration

Read the [MCP limits](../../docs/reference/windows-endpoint.md#network-and-mcp-limits).
Use only the admitted red MCP tools and authorized routes for the selected target.
Examine actual tool availability before an exercise.
