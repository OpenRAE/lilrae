# Default Defensive Posture

This reference distinguishes authored weaknesses, enabled detection, and disabled response coupling.
The admitted pack and runtime observations determine a run's actual state.
A historical baseline cannot establish that state.

The [source record](records/default-defensive-posture-2026-11-06.txt) keeps the earlier baseline at revision `28fc8f18`.
It includes original design reasons and proposed mode behavior.
Status reviewed: 2026-11-06.

## How to read this doc

| Term | Meaning |
| --- | --- |
| `WEAKNESS BY DESIGN` | This term means an intentional scenario weakness, such as a planted credential or excessive account privilege. |
| `STARTING POSTURE` | This term means response coupling that is disabled, absent, or empty before a participant changes it. |
| `BASELINE ENABLED` | This term means detection or collection that already operates at startup. |

Detection and response are separate facts.
A rule can generate alerts while its response block remains disabled.
Startup verification activity can leave events before participant work begins.

## Suricata IDS

Suricata uses passive packet capture.
It does not give inline packet drops.
The checked configuration loads bundled rules, `local.rules`, and generated `misp/misp-iocs.rules`.
The local rules use `alert` actions.

MISP synchronization selects `aptl:enforce` attributes by default.
It writes alert rules and hash lists to the admitted runtime volume.
Its default interval is 300 seconds.
Empty checked-in seeds do not prove an empty running MISP instance.

See [ADR-019](../adrs/adr-019-suricata-ids-only-prevention-via-wazuh-ar.md) and [ADR-043](../adrs/adr-043-suricata-runtime-config-ownership-boundary.md).

## Wazuh detection rules

The manager loads the bundled ruleset and declared custom rules.
The acquired pack owns scenario-specific decoders and content.
Red-side self-reports do not feed the defensive SIEM under ADR-033.

A blue-authored rule upload must have an explicit XML filename.
Replacement must have an explicit overwrite choice.
The connected server's schema defines the installed tool contract.
See [MCP reference](../reference/mcp.md).

## Wazuh active-response

The five response blocks in `config/wazuh_cluster/wazuh_manager.conf` start commented out.
They select rules 5763, 302060, 302010, 301002, and 304040, with 120-second timeouts.
Only `aptl-firewall-drop` enforces the Kali source-IP whitelist.
See the [response reference](wazuh-active-response.md) for command and matcher semantics.

## MISP IOCs

The checked rule seeds start empty.
The admitted pack, startup checks, and participant actions can add runtime data.
An authenticated startup write/read check is distinct from participant IOC promotion.
MISP's current identity and credentials come from the admitted SDL and generated private configuration.

## Shuffle SOAR

The manager declares a `custom-shuffle` integration for level-10 alerts.
A declaration alone does not prove webhook delivery or an enabled workflow.
The admitted pack and backend own Shuffle services and runtime configuration.
See the [scenario reference](../reference/techvault-scenario-overview.md).

## Identity controls (Active Directory)

The admitted SDL owns account names, group membership, SPNs, credential fixtures, and disabled state.
The backend realizes and reads back those declarations.
A planted weak credential is scenario content, separate from an operator credential.
The static account-parity check detects differences between declarations and provisioner behavior.

## Network segmentation

Declared networks and attachments determine peer reachability.
Kali's multiple attachments permit direct access to several target zones.
A network name does not prove firewall enforcement or participant containment.
See [appliance boundary](appliance-boundary.md) for the separate workload-to-management controls.

## Cross-references

- [Wazuh SIEM](wazuh-siem.md)
- [Node realization](node-realization.md)
- [Observe a deployment](../deployment.md#observe-a-deployment)

## How to extend

See [change defensive posture](defensive-posture-operations.md).

## Appendix: forward-looking notes (NOT current contract)

### Per-run mode-gated posture (SCN-001)

The earlier proposed `mode` policy remains in the source record.
It is not a supported local scenario schema or an automatic posture switch.
Current authoring uses [RAES SDL](../sdl/index.md).

### Orchestrator-side continuity carve-out (RTE-001 / #252)

`lilrae lab continuity-audit` is a separate operator-invoked continuity check.
It removes coarse Kali source-IP bans within its declared scope.
It does not establish general rollback or override granular defensive changes.
See [ADR-024](../adrs/adr-024-orchestrator-side-purple-continuity-carve-out.md) for the original decision.
