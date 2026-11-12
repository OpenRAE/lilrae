# Historical Hosted-Seat Trial

This reference records the July 28, 2026 reduced-profile trial in `us-east-2`.
Its source branch was `origin/825-hosted-backup-seats` at `2db0f8ac`.
Use [the reconstruction procedure](hosted-backup-seats.md) only after separate deployment approval.
The August full-TechVault fleet and the current seat launcher are different delivery paths.

## Trial Outcome

One Ubuntu 24.04 `m6i.4xlarge` host used 16 vCPUs, 64 GiB RAM, and a 200 GiB root disk.
The trial proved exact-host public TLS, HTTP redirect, and Caddy as the only public web listener.
DCV listened on loopback and accepted the correct participant password while rejecting a wrong password.
The browser rendered a 1440 by 900 GNOME desktop with a participant-owned terminal and Claude Code `2.1.220`.
The guided lab reported required containers healthy.
Four semantic operations passed before and after a 95-second stop/start recovery.

Those results supported a conditional decision for that exact payload.
They did not qualify the development branch or the current appliance.
The proof host had an unencrypted root volume.
New event launches required the procedure's encrypted mapping; the reused host did not prove that launch property.

At the trial revision, PyPI `aptl-labs==5.1.1` lacked the guided profile.
The development scenario produced exiting Debian placeholders instead of the intended services.
The working Kali Dockerfile also needed its recorded NodeSource repair.
Desktop installation could let NetworkManager interrupt `systemd-networkd` ownership.
Avahi occupied UDP 5353, conflicting with a lab service.
These are historical findings, not current-version defect claims.

The proof launched the coding-agent binary but supplied no model credential and made no billed call.
Provider authentication remained a separate event decision.
Credentials were not admitted into AMIs, user data, handouts, or seat-state directories.

## Proof Inputs

| Component | Pinned proof input |
| --- | --- |
| AWS CLI profile and region | `catalyst-dev`, `us-east-2`, no SSO |
| Ubuntu AMI | `ami-0dc6aa44dbcdd872e`, Canonical owner `099720109477`, `ubuntu-noble-24.04-amd64-server-20260714` |
| Instance size | `m6i.4xlarge` |
| Event root volume | 200 GiB encrypted gp3, delete on termination |
| Amazon DCV | `nice-dcv-server` and `nice-dcv-web-viewer` `2025.0.20103-1` |
| Caddy | `2.11.4` |
| Docker | Engine `29.6.2`, Compose plugin `5.3.1` |
| Host Node.js | `22.23.4` |
| Coding agent | Claude Code `2.1.220` |
| Working APTL payload | commit `e9373f5bec57b2c315c4a9c5d7ab837983b19595` |
| Wazuh certificate helper | `config/wazuh-certs-tool.sh` from commit `ec54ee2da2cd59c58eb17f1dd7737483901b1838` |
| Guided profile and semantic validator | commit `583e100853ac42240de4827678a20d94edb93d7d` |
| Kali build repair | `tools/workshop/hosted-seat-kali-node.patch`, SHA-256 `71ea3832154d25ce8004e9bd9da8275282f4ff33bdf771ae7e50a8bf34376f4c` |
| APTL host ports | Wazuh dashboard `9443`, MISP `9444`; Caddy keeps `443`, DCV keeps `8443` |


The stager owns the three commit pins and the admitted Kali patch.
Its manifest binds the staged payload.
The helper owns seat IDs, private state, DCV/Caddy configuration, and semantic smoke selection.
Their current source remains under `tools/workshop/`.

## Access Model

Each participant used one browser URL, matching username, and independent passphrase.
Each seat had its own VM, Caddy listener, verified loopback TLS connection, DCV PAM login, and GNOME desktop.
The trial used neither a shared account nor a shared application gateway.
Participant VPN, RDP, and SSH were absent.
Only operator SSH was admitted from the exact operator address.

## Vendor References

- [Install Amazon DCV on Ubuntu](https://docs.aws.amazon.com/dcv/latest/adminguide/setting-up-installing-linux-server.html)
- [Amazon DCV server parameter reference](https://docs.aws.amazon.com/dcv/latest/adminguide/config-param-ref.html)
- [Amazon DCV authentication](https://docs.aws.amazon.com/dcv/latest/adminguide/security-authentication.html)
- [Caddy installation](https://caddyserver.com/docs/install)
- [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
- [Claude Code setup](https://docs.anthropic.com/en/docs/claude-code/getting-started)
