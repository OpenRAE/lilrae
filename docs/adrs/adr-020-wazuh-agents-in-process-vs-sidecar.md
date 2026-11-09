# ADR-020: Wazuh agents run in-process on the target containers; sidecars only for upstream-image carve-outs

## Status

accepted

## Date

2026-05-02

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [active-response Reference](../components/wazuh-active-response.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

The v6.3.0 work (CHANGELOG 2026-05-01) added six **Wazuh sidecar** containers (`wazuh-sidecar-{webapp,fileshare,ad,dns,db,suricata}`) built from `containers/wazuh-sidecar/`. Each sidecar mounts its target's log volume read-only and ships the contained log files to the Wazuh manager. This supplied log forwarding for five targets without upstream agents. It was a temporary integration choice rather than the final architecture.

[ADR-019](adr-019-suricata-ids-only-prevention-via-wazuh-ar.md) exposed a sidecar limitation. Its iptables rules affect its own namespace rather than the target's namespace. A sidecar could install a real `firewall-drop` rule while target traffic used another namespace. That rule did not provide the required target enforcement. ADR-019 selected Wazuh active response after the Docker NFQ experiments failed. Effective enforcement required the agent inside the target's network namespace.

Issue [#248](https://github.com/Brad-Edwards/aptl/issues/248) is the implementation. This ADR records the agent-placement decision as a permanent design rule, so future containers added to the lab pick the right pattern by default.

## Decision

**In-process Wazuh agent is the default placement on every APTL target container.** The sidecar pattern is reserved for the narrow case where the upstream image's constraints (immutable / no first-party agent package / hardened user-isolation) make in-process disproportionately costly.

### Default—in-process

The four target containers `webapp`, `fileshare`, `ad`, `dns` run `wazuh-agent` directly inside the container's own namespace, supervised by `supervisord` alongside the primary service. Each Dockerfile uses the shared bootstrap layer at `containers/_wazuh-agent/`:

- `install.sh`: apt-repo + key + `wazuh-agent=4.12.0-1` install. Run once during image build.
- `wazuh-agent.sh`: runtime bootstrap: wait for the Manager authentication port, render `ossec.conf`, and register through `agent-auth -A <name>`. The Manager replaces stale names through `<auth><force><enabled>yes</enabled></force></auth>`. Wazuh 4.12 `agent-auth` has no `-F` option. The bootstrap starts the agent and observes `wazuh-agentd`. Its exit lets the supervisor restart the bootstrap.
- `ossec.conf.template`: base ossec.conf with `__WAZUH_MANAGER__` / `__AGENT_NAME__` / `__LOCALFILE_BLOCKS__` substitution.

Each target's compose entry adds:
- `cap_add: [..., NET_ADMIN]` so the agent's AR can call `iptables` on the container's own namespace.
- `WAZUH_MANAGER` / `AGENT_NAME` / `LOG_PATHS` / `LOG_FORMAT` env vars.
- Memory limit lifted to 512m where the previous limit (128–256m) would not fit agent + primary service together.

The targets do **not** declare `depends_on: { wazuh.manager: service_healthy }`. `wazuh.manager` is in the `wazuh` profile and the targets live in `enterprise` / `dns` / `fileshare`—a hard dependency would make `aptl lab start --profile enterprise` fail when SOC is not selected. The bootstrap script's 180s wait for the manager auth port and its agent-auth retry loop (12 × 10s) handle the startup-ordering case without coupling profiles.

Each target's image build context is the repo root (so the Dockerfile resolves both `containers/_wazuh-agent/...` and `containers/<name>/...`).

### Carve-out—sidecar retained

The `db` container uses upstream `postgres:16-alpine`. Bringing the agent in-process would require either rebuilding postgres on a glibc base or maintaining a custom alpine wazuh-agent build (no first-party Wazuh alpine package exists). The decision judged both options too costly for this database target. It prioritized credential-attack exercises over network-layer blocking on `db`. `wazuh-sidecar-db` continues to ship db's `pg_log/postgresql.log` to the manager via the existing pattern.

The `suricata` container's deployment is governed separately by ADR-019 (Suricata stays IDS-only). Its sidecar (`wazuh-sidecar-suricata`) ships `eve.json` to the manager and is unaffected by this ADR.

### Future containers

Any new container added to the lab, regardless of who is adding it, defaults to in-process Wazuh agent. The sidecar pattern is invoked only when:
- the upstream image cannot be modified, AND
- there is no in-process path that fits within image-build cost (substantial extra image size, package-source unavailability, or user-isolation conflicts).

Document the carve-out in CHANGELOG and link back to this ADR. do not extend the sidecar fleet without that justification.

## Consequences

### Positive

- **AR works.** Every in-process target's `iptables -L` is the same namespace as its primary service, so AR-installed `firewall-drop` rules block real traffic.
- **One source of truth.** `containers/_wazuh-agent/` is shared between in-process targets and the remaining sidecars—a fix in either path is a fix everywhere.
- **Uniform daemonization.** All four in-process targets run supervisord. `ad` already had it; webapp/fileshare/dns gained it as part of #248. New programs added in future (rsyslog tweaks, additional collectors) drop in cleanly.
- **Operational footprint shrinks.** Four sidecar containers are removed from the lab. The remaining two are explicit carve-outs, not the default.
- **Aligns with #249.** AR command/block wiring lands on top of in-process agents without any further topology work.

### Negative

- **Memory bumps.** webapp/fileshare/dns moved from 256m or 128m to 512m. The agent + service combination needs the headroom; on resource-constrained hosts the lab's total memory ceiling is ~500MB higher than before.
- **Dockerfile complexity.** Each target Dockerfile now installs supervisor + wazuh-agent and copies the shared bootstrap. The trade-off is uniform supervised lifecycle across targets, which the maintainability gain pays back.
- **Build context shift.** The four target images (and the remaining two sidecar images) build from repo root rather than per-container subdirectory. Root-context changes can invalidate COPY layers. The inputs remain under `containers/...`, while `.dockerignore` excludes documentation, Git, dependencies, and other irrelevant paths.

### Risks

- **In-process agent crashes affect the target's container restart loop.** Mitigation: supervisord's `autorestart=true` + `startretries=10` on the agent program restart it independently; the primary service is a separate program and is not restarted.
- **Postgres carve-out becomes load-bearing.** If a future attack scenario requires AR on db (for example, rate-limit a credential-spray source), the carve-out blocks it. Mitigation: track the postgres-with-agent custom-image work as a separate issue; this ADR documents that it is a known gap.
- **NET_ADMIN changes the target trust boundary.** Target agents need it for namespace-local drops. An attacker can also use `iptables -F` to remove those rules.
  The accepted lab trade-off permits intentionally vulnerable targets and uses multiple detection layers.
  Wazuh observes commands, Suricata observes network signatures, and MISP/SOAR supplies indicator context.
  A sidecar rule did not affect the target namespace at all.
  The decision does not approve this boundary for production; production needs separate host or BPF enforcement.
- **Forced registration permits impersonation.** A caller that reaches Manager port 1515 can replace an existing agent identity.
  The historical example was `agent-auth -A aptl-webapp-agent` from a rogue container.
  The caller could replace the legitimate key and submit forged telemetry under that name.

The original registration rationale claimed that all four networks were internal.
Root Compose actually leaves the security network external.
Internal attachments therefore do not prove exclusive reachability.
The lab also configures `<use_password>no</use_password>`.
Registration logs provide observations, not prevention.

The original production recommendation used `<use_password>yes</use_password>` with per-agent passwords and shorter force windows.
Its alternative disabled force and used manual key rotation.
These historical recommendations are not production qualification of the lab.

## Related

- [#248](https://github.com/Brad-Edwards/aptl/issues/248): implementation issue (closed by this ADR).
- [#249](https://github.com/Brad-Edwards/aptl/issues/249): AR `<command>` + `<active-response>` wiring with kali-IP carve-outs. Builds on this ADR's in-process agents.
- [[ADR-019](adr-019-suricata-ids-only-prevention-via-wazuh-ar.md): chose Wazuh AR as the prevention layer; this ADR is the precondition that makes it work.
- [ADR-002](adr-002-wazuh-siem.md): original Wazuh selection rationale; the "Dual Log Collection" subsection is updated with a forward-pointer to this ADR.
- [ADR-021](adr-021-active-response-whitelist-via-wrapper.md): the in-band whitelist that the in-process agents shipped here enforce.
