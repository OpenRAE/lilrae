# Victim Container

The admitted TechVault pack owns the victim node's software, accounts, services, and network attachments.
The removed in-tree image is a historical implementation.
Status reviewed: 2026-11-06.

The [source record](records/victim-containers-2026-11-06.txt) keeps the earlier description at revision `28fc8f18`.
Its host SSH port and Falco claims do not describe current pack realization.

## Container Configuration

The full TechVault victim uses the Rocky Linux 9 systemd Wazuh-agent base.
Its declared address is `172.20.2.20` on `internal-net`.
The pack declares `labadmin`, `sshd`, `rsyslog`, and the Wazuh agent.
See [node realization](node-realization.md) for the materialization route.

## Security Monitoring

The Wazuh agent sends declared log sources to the manager.
Declared software and observed service state determine monitoring coverage.
The presence of old Falco rules does not prove that this node runs Falco.

### Wazuh Agent + Falco Integration

The older dual-monitoring design remains in the source record.
Current TechVault declares Wazuh log collection for `/var/log/secure` and `/var/log/messages`.

### Monitored Data

Authentication and system logs give the victim's declared telemetry.
A successful startup check does not prove coverage for every possible attack.

## Network Configuration

The node publishes no host SSH port.
The historical `localhost:2022` command does not reach this victim.

## Access Methods

See [inspect a victim](victim-operations.md) for host access through the supported container command.

## Service Status

See [inspect victim services](victim-operations.md#inspect-services).

## Troubleshooting

See [diagnose victim monitoring](victim-operations.md#diagnose-monitoring).
