# ADR-021: Active-response whitelist enforcement via a standalone iptables AR script

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

[ADR-019](adr-019-suricata-ids-only-prevention-via-wazuh-ar.md) chose Wazuh active-response (AR) on in-process agents as the lab's packet-level prevention layer. [ADR-020](adr-020-wazuh-agents-in-process-vs-sidecar.md) shipped the precondition: in-process agents on `webapp` / `fileshare` / `ad` / `dns` (issue #248). Issue #249 wires the rule → command → agent triggers.

The wiring needs a **purple-team continuity carve-out**. A broad reconnaissance-triggered response could block Kali's source IP on every target. Red activity would then stop at iteration N+1. That ends the exercise after one iter—a degenerate equilibrium that defeats the lab's research purpose. We need a mechanism that lets blue use AR realistically (drop on per-pattern, per-payload, per-behavior signatures) but refuses to act on kali's IPs even when blue's rule would otherwise fire.

The constraint applies to AR scripts that act on a source IP—primarily `firewall-drop`. `disable-account` (acts on accounts) and `host-deny` (acts on hostnames) are out of the immediate scope; this ADR governs `firewall-drop` and is generalizable to other srcip-driven scripts when needed.

## Decision

Implement the kali-IP whitelist as a **standalone Wazuh AR script** that wazuh-execd runs in place of the upstream `firewall-drop`. Manager-side `<command>` blocks reference `aptl-firewall-drop`; the agent's `/var/ossec/active-response/bin/aptl-firewall-drop` reads the AR JSON from stdin, consults `/var/ossec/etc/lists/active-response-whitelist`, and either short-circuits (whitelisted srcip on `add`) or runs `iptables -I/-D INPUT -s <srcip> -j DROP` directly.

The script is **not** a wrapper around upstream `firewall-drop`—it reimplements the iptables operation. Wazuh can keep stdin open for an optional `check_keys` handshake. A forwarding wrapper that waits for EOF can deadlock or break that dialogue. By owning the iptables work end-to-end, the script's stdin contract is single-message-and-exit, which is what Wazuh 4.x's stateless mode expects for simple add/delete operations.

The script:
- Only short-circuits on `command="add"`. `command="delete"` (timeout cleanup) **always** runs the iptables removal branch; otherwise drops installed before an IP joined the whitelist would never be reaped.
- Validates `parameters.alert.data.srcip` as a single dotted-decimal IPv4 with octet bounds. Without validation, a Wazuh decoder that pulls srcip from a hostile log line could embed `evil\n172.20.4.30`; `grep -Fxq` would match the embedded whitelisted line and short-circuit. The validator rejects multi-line input, leading-zero octets, and non-numeric content.
- Idempotent on `add`—checks for an existing matching rule with `iptables -C` before inserting, so repeat dispatches across agent reconnects do not duplicate state.
- Propagates `iptables -D` failure on `delete` as a non-zero exit so wazuh-execd surfaces the cleanup failure to the manager (otherwise the manager believes cleanup succeeded while the DROP rule is still installed).
- Logs every short-circuit, insert, and delete to `/var/ossec/logs/active-responses.log` so blue can audit which AR invocations the carve-out suppressed and which actually mutated state.
- Reads the whitelist with `grep -Fxq` (literal whole-line match). One IPv4 per line in the whitelist file, `#` comments on their own lines only, no CIDR.

The whitelist file ships in the repo at `config/wazuh_cluster/etc/lists/active-response-whitelist` and is **COPYed into each agent's image at build time** (in-process targets per #248 and the remaining sidecars). The file does *not* mount into the manager—the script runs on the agent, and the manager has no role in the whitelist check. Updating the whitelist is a `aptl lab stop -v && aptl lab start` cycle (rebuilds the agent images).

The whitelist ships pre-seeded with kali's three lab IPs: `172.20.4.30` (redteam), `172.20.1.30` (kali on dmz), `172.20.2.35` (kali on internal).

The carve-out has a **complement** in [#252](https://github.com/Brad-Edwards/aptl/issues/252): orchestrator-side post-iter cleanup of overly coarse iptables rules. This script is the *in-band* defense (refuses to install the rule); #252 is the *out-of-band* defense (reverts rules that slipped through, for example, from a non-AR path). The script prevents unwanted active-response drops. Issue #252 separately addresses rules authored directly through `wazuh-control` or a custom script.

### Why not the alternatives

- **Forwarding wrapper around upstream `firewall-drop`.** The first design was rejected because Wazuh can keep stdin open for `check_keys`. A wrapper that buffers through `cat` would wait for EOF. Reading just the first line and re-emitting it to the upstream script is possible but loses the bidirectional stdin path the upstream needs. Standalone implementation owns the contract end-to-end.
- **CDB list with paired suppressor rules.** Wazuh-idiomatic: a rule fires at level 0 (suppressing AR) when the srcip is in a CDB list. Each response rule would need a paired suppressor, producing twice as many rules. The decision placed the shared defensive policy outside individual detection rules. The standalone script is one file for the whole lab.
- **Manager-side dispatch filtering.** Wazuh's manager does not expose a "skip AR if srcip matches" hook. Patching wazuh-manager is out of scope.
- **AR script that filters on rule_id instead of srcip.** Easier to implement (just check `parameters.alert.rule.id`) but does not generalize—every new AR rule blue writes would need to be added to a per-rule allow-list. Srcip-keyed whitelist scales naturally.
- **Generalize to all AR commands now (`aptl-host-deny`, `aptl-disable-account`).** Premature. The pattern is established; if a future scenario needs `host-deny` against kali to be carved out, a per-command standalone script takes ~30 minutes. The `<command>` blocks for `host-deny`, `disable-account`, `route-null` remain declared without an APTL counterpart—blue is responsible for scoping rule_id and level if they enable AR using those commands.

## Consequences

### Positive

- **Carve-out works against the most common AR command** (`firewall-drop` is the canonical srcip blocker; the issue's acceptance criteria call it out explicitly).
- **Wazuh-native plumbing.** No patching of wazuh-execd, no manager-side hacks, no rule-chain proliferation. The script is a self-contained shell script that follows Wazuh's documented AR contract (read JSON from stdin, exit 0 on success, exit non-zero on failure).
- **Auditable.** Every short-circuit logs to `active-responses.log`, so blue (and researchers reviewing run archives) can see exactly which AR invocations the whitelist suppressed.
- **Generalizes easily.** The script's structure (parse stdin → check whitelist → run iptables) is replicable for `host-deny` / `disable-account` / future commands as needed—each gets its own standalone implementation. Future ADR can record that generalization.
- **Defaults are conservative.** All `<active-response>` blocks ship `<disabled>yes</disabled>` (per #249), severity-gated at `<level>10</level>`, timeout-bounded at 60–300s. Even without the whitelist, blue's AR cannot easily wedge the lab—the whitelist is the deepest-defense layer.

### Negative

- **Whitelist file lives in N+1 places.** The same file is COPYed into every Wazuh agent image at build time (4 in-process + 2 sidecars = 6 places). Updating the whitelist requires rebuild + lab cycle. Acceptable given how rarely the kali IPs change (never, in the current topology).
- **Wrapper covers `firewall-drop` only.** `host-deny` / `disable-account` rule chains can still affect kali if blue enables them. Documented in `docs/components/wazuh-active-response.md` and in the manager-config comment block. Future work generalizes.
- **Behavior change on the existing rule-5763 AR block.** Pre-#249 the rule-5763 AR was enabled (auto-block SSH brute force) and used bare `firewall-drop`. After #249 it is `<disabled>yes</disabled>` and uses `aptl-firewall-drop`. **This is intentional per #249 AC#6** ("Default starting posture: all `<active-response>` blocks disabled—blue's job over iters is to enable and tune them"). Blue re-enables by deleting one `<disabled>` tag. The uniform disabled posture removed the earlier automatic block. Researchers could then distinguish actions enabled during the exercise from actions enabled before it. Documented in `CHANGELOG.md` for v6.6.0.

### Risks

- **A compromised lab container that reaches manager auth port (1515) could re-register as `aptl-webapp-agent`** and dispatch arbitrary AR commands ([ADR-020 risk note](adr-020-wazuh-agents-in-process-vs-sidecar.md#risks)). The script's whitelist provides the same protection regardless of which agent calls it. Documented; production deployments need `<use_password>yes</use_password>` per ADR-020's hardening guidance.
- **The script trusts `/var/ossec/etc/lists/active-response-whitelist` as written.** A container compromise that gains root inside the agent (which it has—see the `NET_ADMIN` trade-off in ADR-020) could rewrite the whitelist to remove kali, causing the next AR invocation to drop kali. Mitigation: file is owned `root:wazuh` mode `640` so only root and the wazuh group can write. In a non-lab production deployment, immutable storage (read-only filesystem, dm-verity) would be the answer.

## Related

- [#249](https://github.com/Brad-Edwards/aptl/issues/249): implementation issue (closed by this ADR + the PR that ships it).
- [#252](https://github.com/Brad-Edwards/aptl/issues/252): orchestrator-side post-iter carve-out, the out-of-band complement to this in-band script.
- [ADR-019](adr-019-suricata-ids-only-prevention-via-wazuh-ar.md): designates Wazuh AR as the lab's prevention layer; this ADR is the carve-out that makes it usable in a purple loop.
- [ADR-020](adr-020-wazuh-agents-in-process-vs-sidecar.md): in-process agent placement; this ADR's wrapper deploys to every agent's `/var/ossec/active-response/bin/`.
