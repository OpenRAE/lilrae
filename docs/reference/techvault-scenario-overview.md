# TechVault Scenario Overview

TechVault is the installed enterprise scenario used for ordinary local and seat delivery.
It models a fictional company with intentional application, identity, and infrastructure weaknesses.
This reference describes the admitted pack boundary, not a separately maintained topology preset.

## Where the scenario is defined

The acquired `techvault` bundle gives canonical SDL, content, and artifact identities.
`pyproject.toml` declares supported dependencies. `uv.lock` pins RAES 10.7.0 and environment packs 7.2.2.
The bundled adapter qualifies one exact pack version and set digest in `src/aptl_techvault/pack_identity.py`.

The operator catalog projects acquired identities.
`scenarios/catalog.json` belongs to explicit checkout-only research fixtures.
It does not add normal startup aliases.
See the [authoring boundary](../sdl/index.md) for upstream schema and pack owners.

## Fictional company

TechVault Solutions is the range's fictional enterprise.
Its internal domain is `techvault.local` and its AD realm is `TECHVAULT.LOCAL`.
Authored accounts and content give the employee personas and planted weaknesses.
The earlier [company profile](techvault-company-profile.md) and [OSINT plan](techvault-osint-readiness.md) are historical proposals.
They do not establish a deployed public company, domain, cloud account, or external profile.

## Topology

The SDL declares security, DMZ, internal, and red-team networks.
The backend derives deployment from the admitted nodes, connections, and dependency closure.
Scenario names do not select a topology preset.

### Enterprise targets

The pack declares `webapp`, `ad`, `db`, `workstation`, `fileshare`, `dns`, and `victim`.
It also declares the `kali` and `soc-workstation` participant nodes.
The current pack does not declare the retired mail or reverse workstation nodes.
Software versions and services come from the admitted runtime declarations and observed realization.
A former PostgreSQL image version does not describe a newly materialized database.

### Defensive and SOC stack

The pack declares Wazuh manager, indexer, dashboard, Suricata, MISP with database/cache support, and Shuffle services.
Suricata gives detection. Wazuh active response gives separately enabled prevention.
See [default defensive posture](../components/default-defensive-posture.md).

Eight declared Wazuh agents belong to webapp, AD, DNS, fileshare, victim, workstation, database, and Suricata.
Enrollment identity survives a service restart so manager events remain attributable.
This does not prove that every possible event is detected.
Kali has no defensive SIEM self-reporting path.

MISP uses its authored origin, `https://misp.techvault.local`, with the lab CA.
Its database, cache authentication, and administrator identity are admitted before startup.
Optional OTel services are backend apparatus.
Normal TechVault native evidence does not require or admit that optional stack.

### Host-published ports

`lilrae lab info` reports observed runtime URLs, remapped ports, and credential-file locations.
`lilrae lab start --json` distinguishes observed ports from an unverified start-time plan.
A declared service listener does not itself publish a host port.
There is no default reverse-workstation SSH publication on port 2027.

The [source record](records/techvault-scenario-overview-2026-11-06.txt) keeps the earlier static port list and topology description.
Status reviewed: 2026-11-06.
That record is not a current endpoint inventory.

## Planted vulnerabilities

The admitted SDL and content own exact vulnerabilities and credential fixtures.
The enterprise models SQL injection, command injection, XSS, authorization failures, credential exposure, and weak identity controls.
The precise admitted version determines which paths are present.
A declared vulnerability is not proof of successful exploitation or detection.

## Planted secrets

Authored `secret_fixture` credentials are synthetic scenario content.
They are distinct from real operator, provider, signing, and control-plane secrets.
The backend must respect admitted realization scopes when it places content or binds credentials.
An unspecified scope does not authorize a new environment value or mount.

## Curated startup variants

Three reduced fixtures exercise attacker/target, enterprise/web, and defensive-minimum realization.
They remain checkout-only research inputs.
Their [reference](../sdl/curated-variant-reference.md) owns the fixture matrix.
Use the [fixture procedure](../sdl/techvault-curated-variants.md) for explicit selection and validation.
Reduced-profile evidence does not qualify full TechVault or its seat delivery.
