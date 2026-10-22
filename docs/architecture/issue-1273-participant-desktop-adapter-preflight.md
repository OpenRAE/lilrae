# Issue #1273: Participant Desktop Adapter Preflight

The supplied issue is the contract; this note records design guardrails, not an
implementation plan. It extends the adapter boundary in the
[issue #980 preflight](issue-980-pack-adapter-install-seam-preflight.md) and
[ADR-053](../adrs/adr-053-pack-backend-deployment-serving-interaction-seam.md).
It does not accept the broader proposed ADR-054.

## Ownership and contracts

Use a purpose-specific desktop entry point in the existing `aptl.*` extension
family, such as `aptl.participant_desktop`. TechVault owns console selection and
order, credential references, guide selection, hostname references, and scenario
rule-file defaults. Core owns admission, resolution, validation, publication,
errors, and lifecycle. The provider returns bounded data, never shell, Python
import strings, privileged operations, literal passwords, or an arbitrary
environment/config mapping.

Select against the admitted `PackIdentity` and backend context, following
`pack_interaction_discovery.py` and `scenario_startup.py`: filter selectors before
loading, check API/version/digest/backend compatibility, require a unique
compatible provider, copy validated immutable results, and record distribution
provenance. Do not select from a filename, container suffix, static default pack,
or a global registry. Explicit absence of an optional desktop surface is distinct
from a required surface whose provider is missing or malformed; the latter fails
closed. Provider installation is a code trust boundary, not a sandbox.

The seam carries component-address references for endpoints and authored names,
classified SDL value references for credentials, and a bundle-relative asset
reference for the guide. Use the existing admitted RAES runtime models and
realization records, not another SDL parser/schema or service catalog. Core must
resolve every reference against the same admitted source and run. Both the
hostname and its target address come from that binding: changing the authored
hostname must not require editing an adapter literal. Labels/order may be
adapter-owned; URLs, hostnames, and password values may not be copied defaults.

`AptlRealization`/`NodeRealization`, `DeploymentServicePort`,
`DeploymentPublishedPort`, network attachments, `host_ports.py`, and backend
port readback already describe this machinery. They are not all observations:
planned publications do not prove actual reachability. Resolve the selected
service/network against the realized result and existing backend readback;
preserve the canonical component-to-runtime identity. If an address-keyed
projection is missing, extend that result narrowly rather than rediscovering
containers or adding a parallel persistent endpoint registry.

Bind observations to the existing deployment authority and owned resources:
`_docker_endpoint_binding.py`, `_compose_resource_ownership.py`,
`_compose_network_realization.py`, and `_compose_realization_networks.py` already
pin daemon/project authority and verify declared attachments. Readback failure
is not an empty inventory (`BackendObservationError`); timeouts use
`BackendTimeoutError`. A matching hostname/container label alone is not proof
of ownership. Resolve once for the current admitted start; invalidate the
projection on container replacement, network change, stop, or reset.

The desktop's network perspective must be explicit. A guest-local published
loopback endpoint is different from an attached container-network IP and from
the outer host's endpoint. Reject missing, ambiguous, unready, or unreachable
bindings; do not guess the first network, use a fixed subnet, substitute
`0.0.0.0` as a browser destination, or silently drop required consoles. Preserve
the authored TLS origin and realized port, including remapped ports.
`core/endpoints.py` is a legacy container-name snapshot annotation table, not
the source authority for this seam.

`deployment/_authored_service_hosts.py` already projects authored canonical
HTTPS hosts into certificate SAN generation in `_compose_stateful_realization.py`.
Build on that authored-host interpretation rather than create a second URL/SAN
catalog; its permissive host extraction is not browser/hosts-file validation.
Keep component references explicit, and fail if the released model cannot
represent a required binding. Reuse `core/host_ports.py` and `_port_bindings.py`
for published-port identity, with live backend readback for the final address.

## Cross-cutting layers and canonical incumbents

| Layer | Required passage and reuse |
| --- | --- |
| Pack and SDL admission | `ScenarioBundle`, `env_pack_bundle`, env-packs validation/content-manifest gates, and public RAES parsing/compilation stay authoritative. Validate referenced component existence, kind, and exact service/network binding; do not reinterpret raw YAML with weaker rules. |
| Installed extension admission | Follow `pack_interaction_discovery.py`/`scenario_startup.py` metadata, immutable-result validation, stable error codes, and provenance conventions. Validate sizes, unique identifiers, ordered collections, and supported reference shapes at the core boundary. Reuse existing context/identity types; add only the desktop-specific projection. |
| Config and environment shapes | Keep `AptlConfig`'s closed Pydantic models. Reuse `_scenario_environment.py`'s fixture/alias validation, `valid_environment_variable_name`, `hydrate_dotenv` reconciliation, and deployment `_environment_bindings.py`'s exact pack/consumer/source grants when startup needs bindings. Name/single-line/forbidden-key and `environment_file_line` checks still apply. Desktop data must not enter `workbench/agent.py`'s closed `mcpServers` / `command,args,env` shape or `participant_profile_models.py` as undeclared fields. No arbitrary env, URL override, command, or import-path config. |
| Secret classification and source | Resolve desktop credential references only when their admitted SDL value is explicitly `secret_fixture` and actually carries the authored value. Classification alone is insufficient: a value-less fixture may legitimately use an operator grant or startup adapter for deployment. Those sources and generated `value_from` outputs are not authored desktop fixtures. Reject `operator_secret`, redacted, unresolved, missing, or unclassified values; no `.env`, process environment, alias, content-extraction, or compatibility-password fallback. Keep raw values out of public DTOs, reprs, evidence, and generic serializers. |
| Assets and rendering | Resolve the guide with `ScenarioBundle.read_asset` and its containment/no-follow checks plus admitted asset integrity. Never fall back to a checkout handout. Bound decoded content; escape labels, usernames, fixture values, and URL attributes in HTML. No active HTML/scripts from credential strings, remote markdown resources, or executable asset references. |
| OS/filesystem publication | Reuse `utils/pathsafe.py`'s descriptor-relative no-follow reads/writes and the handoff's participant ownership behavior: private directory (`0700`), participant-owned file (`0600`), atomic replacement. `_private_file` alone checks only the leaf; it does not provide ancestor/race protection. `replace_private_nofollow` expects caller-owned parents, so root-to-participant handoff must respect that identity contract rather than relax it globally. Establish the trusted home/account from OS identity; no provider-selected output paths. Keep secrets out of argv, shell tracing, stdout/stderr, EC2 user-data, browser URLs, and public web serving. Unix root retains access; this is account isolation, not protection from root. |
| Hostname and URL validation | Permit only bounded hostnames and parsed IP addresses tied to admitted components; reject whitespace/control/line injection, conflicting mappings, and reserved-name overrides. Permit browser HTTP(S) origins without userinfo or secret query data; local guide files use a separate validated asset path. Never interpolate provider output into shell or desktop `Exec` commands. |
| Host effects and TLS | One core-owned hostname publisher is used by both `setup-rdp.sh` and desktop handoff. Follow the existing marked `/etc/hosts` replacement behavior, preserving unrelated entries and metadata; serialize updates, remove stale owned entries, and handle partial failure. Use realized network authority, not Docker enumeration. Preserve ADR-034 CA verification and exact authored origin; trust only the existing admitted public CA artifacts, never private keys or a new trust-all switch. |
| Authentication and containment | Keep admitted run/profile/role authorization, guest seat privileges, and management-owned MCP registrations. `verify_token` and web Host/Origin/CSRF/session controls are unchanged: no new web route or credential-serving endpoint is needed. Browser fixture access does not authorize provider keys, broader MCP access, or participant Docker-group membership. |
| MCP shapes and requests | Reuse `LabConfig.queries`, `path_param_patterns`, `tools/api-definitions.ts`, `tools/api-handlers.ts`, `HTTPClient`, and `endpoint-url.ts`. Definitions and runtime validation must agree; `CallToolRequestSchema` and the unstructured `params` schema do not validate filename/overwrite semantics. Full-match filename validation precedes encoding/request/auth; only the management-owned query configuration chooses the origin and Wazuh JWT source. Per-query auth uses an empty base URL, so filename validation is essential there too. Raw-string body and Content-Type handling from #1251 stay generic. |
| Errors, telemetry, persistence | Reuse `LabResult`/startup diagnostics, stable provider failures, `get_logger`, Python/MCP redaction, MCP success/error envelopes, and existing OTel boundaries. Log codes/counts/provenance and exception classes, never payloads or raw provider exceptions. Redaction is not proof that an arbitrary fixture password embedded in HTML will be masked. Existing run store/lifecycle authority owns non-secret references and provenance; no new database or secret-bearing run record. |

SDL fixture classification is not identical to deployment credential sourcing in
ADR-052, and `ScenarioEnvironmentFixture` alone does not attest an SDL
classification. In this checkout `aptl_techvault/wazuh_credentials.py` extracts
API credentials from embedded content and retains exact-release indexer
plaintext compatibility values pending env-packs#392. That helper cannot satisfy
the desktop's stricter `secret_fixture` acceptance criterion. A pack release
without suitable classified plaintext references is an explicit compatibility
gap, not permission to display its fallback or reverse a password hash. Establish
the compatible pack inputs before claiming all five service credentials work.

## Rule-file boundary

The checkout's Wazuh `create_detection_rule` already uses `{filename}` and
`path_param_patterns`; indexer's `create_rule` still fixes a scenario filename
and `overwrite=true`. Keep product API semantics in generic MCP config, and
scenario filename/default overwrite choices in the adapter or participant
profile. Both tool surfaces must use the same existing path-parameter mechanism;
read-file paths need the same filename safety when reachable through this flow.

Require a non-empty, bounded single filename with the supported XML suffix and
safe ASCII characters. Reject separators, percent escapes, controls, whitespace,
and query/fragment injection before any HTTP request. Encoding alone is not
validation. The shared handler currently stringifies parameter values; tests
must establish that wrong-shaped inputs cannot bypass the intended contract.
Keep validation in the shared mechanism/config rather than server-specific
wrappers. `overwrite` is a query parameter, not part of the filename; require
explicit scenario/profile policy and preserve the non-destructive generic
default. The current handler accepts a one-element filename array by string
coercion; require an actual string, bounded length, and a params mapping before
merging. Validate overwrite's supported shape and reject unsafe/missing names
before even the JWT authentication request. A TypeScript interface is not a
runtime validator. Catch malformed input within the existing MCP error envelope;
do not echo supplied values or raw validation/HTTP exceptions.

The existing participant narrative/profile and managed-client schemas have no
rule-default field. Supply defaults as validated tool arguments through the
adapter/participant invocation boundary; if a persistent profile field is
needed, evolve its closed contract and all readers deliberately. Do not patch
the canonical JSON query file per scenario or insert extra client-config keys.
Upload is a complete-file operation, not append/merge or automatic manager
restart. Do not add XML/rule semantics unrelated to this issue.

## Whole-repository guardrails and evidence

The affected surface includes `src/aptl_techvault`, provider metadata and wheel
bundling in `pyproject.toml`, core admission/startup/realization, environment
reconciliation, both rule tools and shared MCP handlers, `setup-rdp.sh`,
`launch-ranges.sh`, desktop handoff/session, guest provisioning and first boot,
and `scripts/appliance/build-seat-image.sh`. Guest scripts use system Python;
the installed/offline adapter metadata and core package must be visible there,
not only in a developer's virtualenv. Reuse `hatch_build.py`, `_asset_manifest.py`,
`core/assets.py`, the offline wheel closure, and `provision-offline.sh`'s installed
Python paths; keep every explicit guest-script copy list synchronized. The
current `core/lab.py` handoff subprocess receives only project/run identifiers,
not the admitted realization. Extend that bounded core handoff to carry the
validated projection; do not re-admit a default pack in the guest script.
Preserve the existing readiness ordering:
publish a validated complete desktop surface before `run-ready`; replace or
remove stale run outputs on restart/failure/teardown. A timer is not readiness.
`desktop-session.sh` currently opens `about:blank` immediately; browser tab
publication must consume the same ready surface. The participant-writable
`run-ready` marker coordinates UI only and must never authorize privileged
hostname publication. Keep credential rendering account-local and inactive;
the guide must not load network resources or execute pack-provided markup.

The launcher has no realized guest endpoints at instance launch. It must not
reconstruct SOC credentials/URLs or add remote extraction/upload machinery;
direct participants to the admitted guest-local surface. Seat login credentials
are a different authority from SOC fixture credentials. The existing RDP default
password and launcher seat-secret printing are adjacent exposure concerns;
moving SOC facts does not remediate or endorse them.

Exercise all four provider fields and mutation of credential/hostname through
`tests/fixture_pack.py` and the production admission path. Maintain fixture
manifests/digests through the owned pack conventions. Cover duplicate/incompatible
providers, invalid references/classifications, ambiguous networks, port remaps,
HTML/hosts injection, file permissions/link attacks, partial failure, and stale
state. Reuse `test_seat_desktop.py`, adapter install/artifact tests, endpoint
realization tests, and shared MCP API/security tests. A rendered page or direct
provider injection alone does not prove the installed guest path.

The shared `tools/check_pack_boundary.py` checker covers every issue-listed
directory, including all of `src/aptl`. It derives owned hostnames, credential
values and account names from admitted packs and installed adapter metadata;
diagnostics name only the path and fact kind. The staged hook and CI tests run
that same checker, and installed-wheel tests cover the bundled runtime copies.
Planted-fact tests establish directory coverage. Existing TLS-disabled
MCP config is also not evidence of ADR-034 compliance: preserve the canonical
CA plumbing and do not extend insecure settings to the new browser surface.
Local checks remain
targeted pytest/Vitest and staged `pre-commit run`; CI owns whole-tree gates and
clean lab/image validation.

The acceptance criterion covers directories, not just the issue's initial file
list. Other current matches include `scripts/thehive-apikey.sh`, backend
implementation catalogs, `raes_participant_fixture_{core,green}.py`,
`cli/lab_render.py`, and `core/lab.py`. Reconcile actual scenario credential,
hostname, and URL copies within that stated surface; do not merely move the
desktop copies and claim the criterion passes. Distinguish backend resource
identifiers from authored browser hostnames in the policy's ownership rules;
do not evade the check with renamed literals or permissive allowlists. This
does not authorize unrelated #1121 migrations outside the issue's surface.

## TheHive bootstrap lifecycle

After verifying the declared administrators, the backend retires the image's
undeclared bootstrap login. A verified declared administrator sets its password
through TheHive's native API to cryptographically generated material, which is
sent on stdin and discarded. Startup succeeds only after the replacement
authenticates, the old login receives an authentication refusal, and the
declared administrator still authenticates. Each reconciliation replaces the
password, so a temporary lock on the old login cannot masquerade as retirement.
Failed commands, unavailable readback, or unsuccessful rotation fail startup.
Reruns verify that bootstrap access remains closed and use a working declared
administrator when creating further declared accounts. An explicitly authored
bootstrap principal retains its SDL-defined credential.

The seed script requires the admitted administrator credentials and has no
image-default fallback. Manual reruns can load them through the existing
project-environment helper. Service API keys remain stable across reruns. This
closes the extra default-password access without changing the SDL or storing a
replacement bootstrap secret.

## Extensibility and non-goals

The next variation is another pack or desktop network perspective with different
console count/order, classified fixture references, guide asset, authored names,
and rule filename/overwrite policy. Parameterize those at the admitted
pack/backend/profile seam; keep host publication generic. Do not add service-name
branches, a fixed five-console schema, a new credential broker, duplicate SDL or
endpoint catalogs, a parallel exception hierarchy, plugin-defined workflow
graphs, dynamic package installation, a DNS daemon, or privileged shell output.

This issue does not implement #1121's entire repository migration, relocate
`aptl_techvault`, redesign seat login/authentication, change generic raw-body
support, introduce external hosting/services, or refactor the whole lab
controller. Existing identifiers follow ADR-062; do not create alias packages or
parallel config contracts. This preflight changes documentation only.

## RAES 7 compatibility qualification

The dependency upgrade retains the bounded-participant scenario's authored
source digest. Comparing canonical compiled artifacts from RAES 6.0.1 and
7.0.0 found one difference: the new runtime model adds an empty
`execution_policies` mapping. No existing field changed. The approved compiled
digest therefore changes from
`23307ff404c85e7a60396a0c601a808628e2c882ed42e647c84c6923063113d1` to
`507af439891f2df808809326146f808ddb8c1c7e3ba0e66d81ef4ae0d695747e`.
The exact authored-and-compiled identity refusal remains in place, with the
scenario-freeze and participant-runtime regression tests exercising it.

## Review repairs

Duplicate declarations for the same target principal must agree on identity
attributes, password strength, authentication method, credential source, and
credential value before any account mutation. Credential values are compared
explicitly because their record deliberately omits them from ordinary equality.
The account-provider tests cover both Samba and application targets, conflicting
declarations, equivalent duplicates, and refusal before the mutation boundary.

The RDP opener waits for the root-owned hostname publisher's systemd unit to
be active and for all desktop files to exist. The unit reaches that state only
after the range and hostname publication succeed; its stop/restart lifecycle
follows the range through `PartOf`, and stopping clears the owned mappings.
No participant-writable readiness file authorizes privileged publication.
The seat-desktop regression exercises both publication orders and checks that
the browser opens once, after both are ready.

The hostname reader opens files nonblocking before checking their type, so a
FIFO cannot stall the privileged publisher before regular-file validation.
Subprocess regressions cover a FIFO at either the document or hosts path.
