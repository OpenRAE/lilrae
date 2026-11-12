# Issue #1559: SEC-005 credential isolation preflight

This note covers SEC-005 in Go port 08, inspected at `f573683d1`.
It records guardrails, not an implementation plan, implementation, or passed
package design. Existing ADRs 025, 028, 029, 034, 040, 052, 055, 065, and 066
provide the architecture; no new ADR is needed.

## Requirement conflict

SEC-005's exclusive `.env` storage and substitution-only Compose wording
conflicts with existing source and delivery contracts. The delivery must
reconcile that wording before claiming compliance; Python trace links alone
do not establish it. This preflight does not change the requirement record.

`core/_credential_sources.py` permits explicit process-environment and
project-env-file sources. `deployment/_environment_bindings.py` distinguishes
authored, generated, granted, and identity-bound adapter values.
`deployment/_compose_environment.py` deliberately delivers out-of-band values
through per-service private env files, outside global `${NAME}` interpolation.
ADR-028 permits generated credential-bearing configuration, ADR-034 permits
key material outside `.env`, and ADR-052 separates credential sources from
private provider delivery stores.

The requirement correction should retain the ignored project `.env` for
operator-maintained project credentials, explicitly authorized alternate
sources, private generated delivery, and consumer-specific grants.
Compose must contain no literal operator secrets. Operator secrets and
generated private material must remain outside version control.
Retain ADR-029's distinction between designed vulnerable target data and
operator secrets. Tracked `.env.example` and root `docker-compose.yml` contain
lab fixture values as well as substitution markers. Do not remove scenario
behavior or classify every fixture as a leaked operator credential.

## Canonical owners and required passage

Python paths below are relative to `src/aptl/`; other roots are explicit.
These obligations describe the intended Go design, not completed Go support.

| Layer | Canonical incumbent and required behavior |
| --- | --- |
| Authentication and authority | API `deps.py`, `session.py`, BFF Host/Origin/CSRF gates, and terminal target checks precede effects. MCP common `src/{config,server}.ts` retains capability and closed argument-schema validation. Add no secret-reading route, tool, flag, or request-selected root. A locator or matching variable name grants no authority. |
| Config shape and semantics | `core/config.py:AptlConfig`, `core/_credential_sources.py`, and `docs/reference/schemas/aptl-config.schema.json` define one non-secret model. ADR-065 requires bounded strict JSON, exact names, duplicate/unknown-field, invalid UTF-8, non-finite, and trailing-data rejection, followed by existing semantic validation. Preserve missing/null/zero distinctions, grant uniqueness, and complete deployment settings. No permissive map or controller-specific validator. |
| Source admission | `deployment/_environment_bindings.py` owns exact admitted pack/consumer/variable matching, classification, grant-before-adapter precedence, and an operation-scoped acquisition snapshot. Preserve authored empty values, generated `value_from`, and OPEN versus exact fixture authority. No ambient fallback, process-wide dotenv loading, or global secret bag. Reject available invalid values before mutation; validate generated values before delivery. |
| Parsing and transport shapes | `core/env.py`, `utils/placeholders.py`, deployment `_realization_primitives.py:environment_file_line`, `_compose_environment.py`, `_compose_stateful_artifact_helpers.py`, and `_compose_runtime_config.py:compose_literal` own existing rules. Use the Compose dotenv parser with explicitly authorized lookup inputs. Preserve Docker versus Compose representability, literal dollar escaping, per-service private delivery, stale-file cleanup, bound-name labels, and readback. `compose_process_environment` remains the client-environment filter for local and SSH runners. |
| Files, locks, and state | `utils/pathsafe.py`, `core/lifecycle_guard.py`, `core/lilrae_config_migration.py`, and Go `internal/securefile`/`internal/filelock` own containment, no-follow access, regular files, retained handles, private publication, lock interoperability, and migration. Product owners retain lock scope/reentrancy, resource receipts, runtime authority, and recovery. No alternate writer, project-state schema, lock registry, or workflow engine. |
| OS exposure | `utils/curl_safe.py`, Go `internal/httpclient`, scoped child environments, and existing stdin/private-file transports keep secrets outside argv, shell text, URLs, filenames, command diagnostics, and environment dumps. Argument arrays prevent injection but do not conceal passwords. Bound I/O and cleanup; do not inherit unrelated credentials or lock handles. |
| TLS and SSH | `core/soc_ca.py`, `_soc_ca_chain.py`, deployment `_stateful_certificates.py`, `_participant_desktop_tls.py`, `core/ssh.py`, `core/host_keys.py`, and ADR-040 retain trust, identity, key-pair, time, consumer, and protection checks. Consolidate certificate verification through `crypto/x509` with explicit purpose/identity/time. The `x/crypto/ssh` client consumes persisted pins; unknown or changed keys fail closed. No trust-all callback, request-time repinning, or fallback from a bad configured CA. |
| Errors and observability | `core/lab_types.py`, deployment errors, CLI `_common.py`, `api/schemas.py`, and MCP `isError` own presentation. Use safe categories and `errors.Is`/`As` where callers branch. Remove secret-bearing parser/transport causes before wrapping. Reuse ADR-029 redaction and `tests/fixtures/redaction_parity_corpus.json` through port 07's shared Go redactor. Inject `slog` on stderr; logging helpers and default struct formatting do not sanitize values. |
| Evidence and persistence | Snapshot `to_dict()`, runstore/evidence writers, telemetry, safe config identity, and exporter remain canonical. Redact before each sink; opaque copy/file writes do not redact. Preserve schema versions, approved descriptor digests and public fingerprints. Do not dump config/environment objects or add secret-derived hashes to provenance. Packaging must receive already-safe evidence. |

The data flow is authenticated entry, strict non-secret configuration,
admitted source/consumer, scoped acquisition, private delivery, verified
client, then safe output and evidence. Core owns values and policy;
application owns operation ordering; adapters own effects through small
consumer-owned interfaces. Foundation must not discover projects or secrets.
Keep Wazuh fields out of generic environment models; service providers own them.
Do not copy Python's private helpers or module structure into Go packages.

## Compatibility and platform hazards

Project dotenv input, Compose project interpolation, Compose service
`env_file`, and Docker `--env-file` are distinct contracts. The shared parser
must not resolve `${OTHER_SECRET}` from an unrestricted host environment or
discover another project's `.env`. Characterize quotes, comments, escapes,
interpolation, duplicates, unset/empty values, multiline input, CRLF, encoding,
malformed lines, and precedence before accepting a replacement.
Record each Python/Compose discrepancy explicitly; neither silently changing
supported values nor adding another handwritten parser is acceptable.

Python currently logs skipped lines without `=` at debug level.
Do not carry that input disclosure into Go. `update_dotenv_values()` emits
raw assignments; newline rejection alone does not protect quotes, dollars,
comments, or backslashes under Compose parsing. Writers must round-trip exact
values through their selected reader while preserving unrelated authored lines.
Preserve existing real generated credentials; only admitted adapter fixtures
may reconcile their authoritative values. Placeholder detection and required
presence are separate checks; optional empty values remain optional.

`find_config()` checks only the supplied directory; lifecycle ownership can
search ancestors. Preserve distinct caller discovery rules.
Inspection must not acquire credentials, hydrate files, migrate, or contact
a backend. Migration stays explicit, locked across read/backup/replace,
validated before writing, idempotent, and preserves exact original backup
bytes while rejecting conflicting backups. Atomic writes are not a multi-file
transaction. Keep each `.aptl/` record with its existing owner.

Preserve `0700` directories, `0600` secrets, and deliberate `0644` bind-readable
service files under protected parents. Blanket `0600` changes break consumers.
Windows `securefile` modes do not establish private ACLs. Preserve the existing
SSH private-key ACL guarantee through the canonical file boundary and prove it
natively; do not claim POSIX-mode parity or add a weaker platform fallback.
Protection must hold before publication, including reused files and failures.
The operator key's existing host-user location does not permit arbitrary home
credential discovery. Operator private keys must never mount into targets.

One certificate verification implementation must preserve different reuse,
artifact-admission, and live-peer policies. Retain renewal windows, SANs,
root aliases, key pairing, keystore/leaf consistency, and exact issued-leaf
comparison. Parsing is not verification. Resolve PKCS#12 support without
dropping the format or writing cryptographic parsing locally. Shared
verification does not merge Wazuh and SOC issuance or SSH client/pivot/host-key
roles. The #677 preflight retains host-user generation and remote-artifact
refusal; #1002/#1188/#1191 distinguish TLS, transport, auth, and readiness.
#1413 retains contained pack locators and refusal of ambient pack fallback.

The extension seams are source kind plus requested credential contract,
exact pack/consumer/variable binding, delivery-reader selection, caller-supplied
root/protection, and verification purpose/identity/time. The next source or
service extends its owner without copying resolvers, adding service fields
to core, global environment overlays, or a new policy registry.

## Whole-repository and delivery boundaries

`.gitignore`, `.dockerignore`, `.env.example`, Compose assets, `config/`
templates, `core/assets.py`, `_asset_manifest.py`, and `hatch_build.py` each
participate in secret exclusion. Ignore checks cover `.env`, `.aptl/`, and
generated key directories; the selected Git index paths list only `.env.example`.
This is not a history or secret-content audit. Ignore rules do not untrack
files, exclude build contexts, protect forced additions, or restrict access.
Root `.dockerignore` does not explicitly exclude `.env`, `.aptl/`, or `keys/`.
Assess the selected build context; this omission alone does not prove an image
leak. Functional gaps require separate bug work outside the port, without
silently changing Python or distribution. Keep private-key hooks and CI Trivy
secret scanning; neither proves all credentials are absent. No broad fixture
exemptions, history rewrite, or external upload is part of this preflight.

Reuse `tests/test_{config,env,env_hydration,credentials,ssh}.py`,
`tests/test_compose_environment_bindings.py`, migration/lifecycle, host-key,
certificate/stateful-realization tests, redaction parity, and existing descriptor
and env-file naming vectors. The conformance inventory lacks dedicated dotenv,
grant, and key-material cases; `cases/config.txtar` is insufficient for port 08.
Missing public contract cases must run on Python before Go. Explicitly record
parser differences; conformance cases are not base-failing regression tests.
Require native file/ACL/lock tests, negative SSH/TLS tests, exact transport
round-trips, and secret canaries in actual errors and retained output.

Closed bug lessons include [#184](https://github.com/OpenRAE/lilrae/issues/184)
(wrong credential source), [#185](https://github.com/OpenRAE/lilrae/issues/185)
(archive/trace leakage), [#266](https://github.com/OpenRAE/lilrae/issues/266)
(credential-write containment), [#418](https://github.com/OpenRAE/lilrae/issues/418)
(SSH identity), and [#1105](https://github.com/OpenRAE/lilrae/issues/1105)
(symlinks and argv disclosure). Preserve invariants, not tests of unsafe behavior.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `architecture/model.yaml`,
`tools/cmd/archcheck`, its generated diagram, `go.mod`/`go.sum`, `.golangci.yml`,
`tools/ci/go-gates.sh`, `tools/ci/select_checks.py`, `checks.yml`, Sonar,
`tools/mutation-thresholds.json`, and `.gc/pack-ownership.json`. The delivery
design must name actual packages/imports/model changes and pass the design
check against `origin/go-cutover` before code. Whole-repository checks include
all OS/build-tag files; no suppressions to bypass findings. Local checks stay
targeted; CI owns full gates and mutation. Add Go trace links only when the
code/tests exist, retaining Python links until cutover.

Non-goals are implementation, an implementation plan, new sources or secret
services, new commands/public fields, config command presentation (port 10),
scenario sources (port 17), service credentials (port 19), lifecycle workflow
replacement, user documentation, distribution, and cutover. This note does not
mark SEC-005 implemented or verified or approve an unwritten package design.
