# Inspect a victim

Use an approved isolated lab VM with an admitted TechVault deployment.
The [victim reference](victim-containers.md) states the current network and monitoring contract.

## Open the node

List the project's realized containers:

```shell
lilrae container list
```

Open the realized victim through the supported command:

```shell
lilrae container shell aptl-victim
```

Do not use the retired host SSH port 2022.

## Inspect services

In the victim shell, examine the declared services:

```shell
systemctl status sshd rsyslog wazuh-agent
/var/ossec/bin/wazuh-control status
```

Compare failures with the admitted SDL and startup diagnostics.

## Diagnose monitoring

Examine the Wazuh agent log inside the victim:

```shell
tail -n 100 /var/ossec/logs/ossec.log
```

Examine the manager's enrolled agents through the generated Wazuh MCP connection.
Make sure that new victim events carry the victim's agent identity.
Do not treat a running process as proof of event delivery.
