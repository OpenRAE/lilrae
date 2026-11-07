# aptl_techvault

This package implements TechVault-specific backend behavior.
LilRAE discovers its providers through the registered entry points.

| Entry-point group | Name | What it gives |
| --- | --- | --- |
| `aptl.pack_backend_interactions` | `techvault.aptl` | which pack components belong to which operator start group |
| `aptl.scenario_runtime_parameters` | `techvault` | fresh runtime-owned bindings for the exact qualified pack release |
| `aptl.scenario_startup` | `techvault` | content-qualified startup and native log-producer realization |
| `aptl.scenario_verifiers` | `techvault.aptl` | the semantic answer key: is the declared defensive stack realized, does the attacker reach its peers |
| `aptl.participant_mcp_smoke_plans` | `guided-purple.techvault-attacker-target` | the exact MCP operations that qualify a participant |
| `aptl.participant_desktop` | `techvault` | the consoles, logins, guide and hostnames the participant desktop shows, as SDL references |

## Declared SOC logins

The pack declares every SOC console login as an SDL account with an authored
`secret_fixture` credential. `account_environment.py` maps each backend
variable, such as `INDEXER_PASSWORD`, to the account credential it carries.
`participant_desktop.py` names the consoles and logins the desktop shows. Neither module holds credential values. Core reads each username and secret from the admitted SDL. A changed authored login therefore needs no adapter value edit.

## Why it lives here

See [why TechVault has an adapter](../../docs/components/techvault-adapter-boundary.md).

## Customer database

The pack declares the customer database's listener, database, tables and login
role, and places its exact schema and seed SQL. Startup realizes those facts
from the declaration and runs the SQL once, in one transaction, as the declared
role. A marker on the database records that initialization, so a later startup
of the same run leaves participant changes alone. Startup refuses to reseed a
database it did not initialize.

The pack does not declare how clients authenticate to that database
(OpenRAE/env-packs#411), so the adapter chooses a posture that keeps the
authored attack paths meaningful. The declared role must have a SCRAM-SHA-256
password that matches the credential the portal presents and the workstation's
leaked `.pgpass` carries. The rule applies only to the network the database
and portal share. Startup makes sure that this rule is the first applicable entry
in PostgreSQL's effective rules. It then authenticates through the portal's
own client settings.

The provider declares this choice in `runtime_selections`.
Each run's reproducibility record reports it under
`backend_evidence.scenario_runtime_selections`, separately from authored state.

## Startup verification traffic

The adapter verifier no longer runs the old `nmap` and failed-SSH checks. Their
alerts outlived verification. Startup is nevertheless **not a zero-event
baseline**. The released SDL must have native evidence of a participant-equivalent
SQL-injection request, an authenticated MISP API write/read, and endpoint
telemetry.

Those checks create bounded activity and may leave records in the
range. Startup also emits bounded syslog, database, DNS, SMB, and HTTP activity. These checks prove that declared producers operate and that manager-attributed telemetry is fresh for declared Wazuh sources.

None of these records should be mistaken for
participant activity.

The framework owns capture windows and deadlines. The adapter receives scoped
backend operations, performs bounded readiness polling, and keeps credential
values inside the services that own them. It does not return those values as evidence.

## Compatibility

Compatibility is an atomic qualification claim, not a set of independent
allow-lists. `qualified_targets` names exact scenario-and-backend pairs, each
whole:

| Dimension | This release |
| --- | --- |
| Extension API | `2` |
| Scenario | `techvault`, source `env-pack`, pack version `7.2.4`, content digest `sha256:9926391531…` |
| Backend | RAES target `aptl` `0.1.0`, profile `full-remote-control-plane` |
| Transport | `docker-compose` and `ssh-compose` |

A pack release must have an adapter release. Changed content is unqualified even when the version is unchanged. A changed version is unqualified even when the digest matches. Version
and digest move together because they are one claim. Until an adapter release
declares the new pair, the gate reports terminal `blocked`.

Nothing is admitted by omission. An empty declaration qualifies nothing. Package version ranges do not establish qualification. An unqualified combination, malformed claim, or absent adapter produces `blocked`, without a pass, skip, or detection-failure verdict. Both transports use the same qualified pack content, target, and profile.

Under ADR-013, the transport selects the Docker daemon location. It does not change the realized range.

A gated test resolves the admitted pack through `env_pack_bundle()` and compares its identity with the adapter qualification. CI catches qualification drift before a live gate reports an unexplained block.
