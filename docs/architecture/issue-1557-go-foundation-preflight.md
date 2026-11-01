# Issue #1557: Go foundation architecture preflight

Issue #1557 is the delivery contract under SYS-009. This preflight records
boundaries, not an implementation plan or a passed design check. Inspection
used `87c284f5` on `1557-go-foundation`. No Go product package exists yet.
[ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md),
the [#1510 preflight](issue-1510-code-quality-preflight.md), and the
[#1555 vector design](issue-1555-serialization-vectors-design.md) govern.

## Decisions required before code

The direction is sound: small foundation mechanisms with injected effects,
no product policy, and exact contract tests. The delivery design still needs
to resolve three tensions rather than hide them behind library defaults:

- **Scheme coverage versus domain ownership.** The
  [serialization inventory](../reference/serialization-schemes.md) includes
  product projections, model validation, resource names, signatures, and
  workflow decisions as well as generic encoding and hashing. Name each
  scheme's function and vector coverage. Keep domain projections and
  admission in their later owning packages; foundation accepts already
  projected values or bytes and explicit framing parameters. Do not move RAES
  models, trial plans, bundle envelopes, or flag-token policy into foundation
  to claim all vectors pass. If a scheme cannot be covered without its later
  owner, record and resolve that acceptance dependency before claiming #1557
  complete; testing SHA-256 alone does not cover a product identity scheme.
- **Strict admission versus historical encoding.** `strict-json.json` rejects
  non-finite constants, duplicates, invalid UTF-8, and trailing data, but
  `sorted-compact-json.json` and `techvault-bounded-json.json` preserve Python
  encodings of non-finite values. A compatibility encoder is not an ingress
  parser. State the disposition for each affected scheme against ADR-065;
  neither silently changing vectors nor weakening strict readers is allowed.
- **Portable APIs versus platform guarantees.** `os.Root` permits internal
  symlinks; renameio supplies neither Windows writes nor full crash
  durability. A path-based locking library may reopen a name after validation.
  Qualify no-follow access, durable publication, locking interoperability,
  replacement, and ACLs for the selected APIs and supported filesystems.
  An unavailable guarantee blocks that operation's delivery, rather than
  authorizing a weaker fallback. See the platform requirements below.

ADR-065's Windows sentence describes renameio's portability limitation; it
must not be read as permission to drop #1557's Windows replacement/ACL
behavior. Qualify the actual filesystem guarantees in the delivery design.
If that needs a reversal of the accepted ADR, follow ADR-000's supersession
rule; do not silently rewrite accepted history or disable Windows support.

The issue's `go-arch-lint` wording is superseded by ADR-065 and #1583:
`tools/cmd/archcheck` and `architecture/model.yaml` are canonical. Do not add
another architecture checker. Before Go code, the delivery design must name
packages, components, imports, and model changes in
`issue-1557-<topic>-design.md` front matter and pass
`go run -C tools ./cmd/archcheck design -base origin/go-cutover <note>`.
This preflight does not add empty packages or model entries to manufacture
that result. The checker validates proposed packages against the working-tree
model; it cannot approve unassigned components from prose alone.

## Package boundaries and extension seams

These are responsibility boundaries for the delivery design. Final paths and
exact dependency permissions belong in its machine-checked record. All product
packages stay under `internal/`, in the existing foundation layer, with no
imports of core, application, adapters, entry, plugins, or developer tools.

| Concern / suggested package | Existing contracts to build on | Dependency and variation boundary |
| --- | --- | --- |
| Files / `internal/foundation/files` | `utils/pathsafe.py` public surface, `_pathsafe_core.py`, `_pathsafe_read.py`; secure writers in `core/credentials.py`, `core/_soc_ca_io.py`, and seat persistence | Standard `os.Root` plus ADR-065's renameio on supported platforms. One owner for no-follow access, complete writes, publication, removal, and permission enforcement. Separate create-once and replacement operations; explicit final mode and required durability. Windows support stays behind platform files in this package. |
| Canonical forms / `internal/foundation/canonical` | `utils/strict_json.py`, `rfc8785.json`, `sorted-compact-json.json`, `runstore-canonical-payload.json` | `encoding/json/v2` and ADR-065's JCS dependency as qualified by vectors. Named schemes with exact numeric and Unicode domains; no universal marshal helper, product schema, or YAML/SDL parser. |
| Digests / `internal/foundation/digest` | Inventory and vectors for raw SHA-256, locator SHA-256/SHA-512/BLAKE3, domain framing, and digest spelling | May use canonical and the approved BLAKE3 module. One named function per distinct scheme; explicit bytes, domain, framing, prefix, and truncation where the contract permits variation. No model introspection, environment lookup, or algorithm negotiation from untrusted input. |
| Time / `internal/foundation/clock` | `core/correlation/clock.py` effect seam and timestamp vectors | Standard time only. UTC instants and monotonic elapsed time; preserve each text formatter separately. Source synchronization metadata in `ClockContext` is a later domain concern, not part of a generic host clock. |
| Deadline waits / `internal/foundation/wait` | `core/services.py:wait_for_service`, deployment listener/readiness loops | May use clock. Inject time/timer and probe seams; caller owns interval, deadline, retry eligibility, progress, and terminal policy. No readiness service, workflow engine, or automatic operation replay. |
| Locks / `internal/foundation/filelock` | `core/lifecycle_guard.py`, `core/runstore.py:finalization_lock`, seat `locking.py`/`allocation.py`, workbench lock owners | May use files and the ADR-065 flock module where it preserves the opened-handle contract. Distinct shared/exclusive and try/wait operations. Lock scope and reentrant ownership are explicit, not inferred from a goroutine or global registry. |
| Processes / `internal/foundation/process` | `workbench/process.py`, `_pipe_exchange.py`, deployment local/SSH runner contracts | Standard execution plus platform process control. Explicit argv, cwd, environment, stdin, output and time limits, termination grace, and cleanup result. Domain command selection, SSH transport, and Docker ownership remain outside. |
| Host HTTP / `internal/foundation/httpclient` | `utils/curl_safe.py`, `core/collectors.py` CA resolution, `core/services.py` outcomes; bounded downloads and workbench proxy contracts | Standard HTTP/TLS with an injectable `Do`/transport seam. Inject trust roots, context, timeout, response limits, and redirect/proxy policy. No discovery of lab paths, credentials, service names, retries, or JSON model validation. |

Use small consumer-owned interfaces for file operations, clocks, process runs,
and HTTP; return concrete results. Use standard interfaces where sufficient.
Entry wiring supplies concrete implementations later. Do not create a common
effects container, storage repository, plugin registry, dependency injection
framework, or parallel mock API. Fakes cannot replace real platform tests.
The existing tool-layer renameio wrapper is precedent, not a product import:
`tools/internal/architecture/replace*.go` remains owned by tooling.

## Required passage through cross-cutting layers

The later call chain is authenticated entry -> admitted application/domain
operation -> foundation effect -> domain result -> redacted presentation.
Foundation implements mechanics, not admission or authorization. The following
layers constrain its interfaces even though their consumers are out of scope.

| Layer and canonical owner | Required passage |
| --- | --- |
| Authentication and external shapes | `api/deps.py`, `api/session.py`, `api/middleware/bff.py`, API routers and `api/schemas.py`; MCP common `src/{config,server}.ts` and Ajv gates retain token/session, Host/Origin, capability and closed argument validation before effects. Add no listener, HTTP route, MCP tool, auth decision, alternate DTO, or foundation command passthrough. |
| Configuration, environment, and credentials | `core/config.py:AptlConfig`, `core/env.py`, `utils/placeholders.py`, `core/_credential_sources.py:EnvironmentGrant`, deployment `_environment_bindings.py`, `_compose_environment.py`, and `_realization_primitives.py` remain authoritative. Durable config is non-secret; exact pack/consumer/variable grants, placeholder checks, source selection, and Docker/Compose representability precede mutation. Foundation receives explicit values, does not hydrate `.env`, read ambient credentials, or treat a variable name as authority. Preserve existing `APTL_*` bindings and locator shapes; add no parallel spelling or runtime settings schema. |
| Decode and semantic validation | Strict bounded first-party decode follows ADR-065: exact names, unknown-field rejection, duplicate/UTF-8/non-finite checks, one value/document, then semantic validation before effects. Canonical maps cannot enforce a caller's schema. RAES and env-packs public Go APIs own SDL, packs and plans; `resolver.py`/`spec_loading.py`, `AdmissionPolicy`, and bundle validation retain their existing limits and rejection stages. Missing upstream APIs block their dependent scope; no local substitute. External HTTP JSON follows the owning service contract. |
| Filesystem and OS exposure | `utils/pathsafe.py`, ADR-028 generated state, ADR-034 CA storage, and `core/ssh.py` Windows ACL handling define protection floors. Trusted roots are supplied by owners. Reject unsafe paths and special files before reading or writing; use the same opened handle for reads, hashes, and mutation. Secrets stay out of argv, raw command diagnostics, default string formatting, and world-readable temporary files. Explicit child env and handle inheritance prevent ambient credentials or lock descriptors leaking to children. |
| Host HTTP and trust | `curl_safe.py` outcomes and ADR-034 govern TLS: validate hostname and chain, fail on missing/malformed configured CA, and retain existing explicit per-client insecure exceptions without creating a global bypass. Callers resolve explicit CA, `APTL_LAB_CA_PATH`, `APTL_PROJECT_DIR`, then existing project fallback; foundation only consumes the result. Keep intended lab trust versus system trust explicit. Auth headers/body travel in memory; URL userinfo/query secrets, proxy credentials, redirects, and raw `url.Error` text must not escape. |
| Persistence and integrity | `RunStorageBackend`/`LocalRunStore`, runstore internals, evidence/content store, archival seal/verify, and bundle owners retain namespaces, redaction, create-once comparison, locking, immutability, reserved seal-marker authority, and independent verification. Foundation owns bytes and durability, not run schemas or seal transitions. A checksum does not establish authenticity, authorization, or resource ownership. |
| Errors and observability | ADR-065 errors use `errors.Is`/`As` and wrapping where safe; add a typed category only if callers branch on it. `deployment/errors.py`, `LabResult`/`LabStatus`, CLI exit mapping, API envelopes and MCP `isError` remain presentation authorities. Never wrap or print a secret-bearing parser, URL, exec, stdout/stderr, or response error verbatim. Return safe operation/category metadata and preserve cancellation versus timeout, busy versus unavailable, HTTP versus transport, and cleanup residue. |
| Redaction and tracing | ADR-029, `utils/redaction.py`, its MCP counterpart, `utils/logging.py`, MCP telemetry wrappers, snapshot `to_dict()` and runstore serialization define the existing boundary. Go port 07 owns the shared Go redactor. #1557 must already avoid secret-bearing errors/logs and implicit payload dumps; bounded output is still sensitive. Prefer no foundation logging, otherwise injected `slog`, static messages, safe fields and stderr. No new redactor, taxonomy, trace exporter, or temporary unsanitized output path. |
| Repository policy and workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `.gc/pack-ownership.json`, `tools/check_pack_boundary.py`, module manifests, `.golangci.yml`, `tools/ci/go-gates.sh`, `tools/ci/select_checks.py`, `checks.yml`, branch protection and Sonar settings all see this change. Add exact component/module permissions and regenerate the architecture diagram during delivery. Keep scenario facts outside foundation, zero findings and no convenience suppressions. |

## Contract hazards and evidence anchors

**Files.** `os.Root` contains access but follows links within the root and is
not an OS sandbox; it does not exclude device files or mounted filesystems.
Retain lexical rejection before cleaning (`.`, `..`, empty components, NUL,
absolute paths), every-component no-follow behavior even for internal links,
regular-file checks, and retained directory/file handles during rename races.
Root creation itself needs a trusted owner. Windows adds drive/UNC/device and
reparse-point cases. Do not reopen a checked file by its original path or use
path-based chmod after publication. See [Go's Root contract](https://pkg.go.dev/os#Root).

Keep private ancestor ownership/non-writability, owner-only parent creation,
unpredictable exclusive temporary names, complete short writes, exact final
modes, same-filesystem publication, file sync and parent-directory sync where
required, and cleanup on every failure. Atomic visibility, create-once
no-clobber, and crash durability are separate contracts. A failure after
publication but before directory sync must not claim the old file is intact
or blindly retry a create-once write. renameio's
[atomicity documentation](https://github.com/google/renameio#atomicity-vs-durability)
does not promise full durability. Its replacement semantics do not supply
create-once publication. Windows needs qualified replacement, sharing and
ACL handling; [ReplaceFileW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew)
also preserves existing file metadata, so do not assume POSIX inode/mode rules
transfer. `chmod(0600)` alone is insufficient. No delete-then-rename fallback.

**Canonical bytes and digests.** Read the existing inventory and corpus
directly, with closed test dispatch and exact bytes as well as digest checks.
Preserve integer precision and float identity (`1` versus `1.0`, negative
zero), Unicode ordering/escaping, optional/null fields, domains, separators,
LF/CRLF, prefixes, truncation and rejection stage. RFC 8785 sorts UTF-16 keys
and formats ECMAScript numbers; Python compact sorted JSON uses code-point
ordering, ASCII escapes and different numbers. Ordinary Go encoding and
`map[string]any` decoded through float64 are not compatibility solutions.
Corpus type tags remain test-only. Hash raw bytes without text decoding;
do not conflate integrity hashes with MACs, signatures, fingerprints or IDs.

**Time and waits.** Use monotonic elapsed time for deadlines and UTC for
instants, with cancellable timers and no sleep past the remaining budget.
Preserve the owners' check-at-deadline/no-check-after-deadline behavior and
pass remaining time to blocking probes; an outer timer does not bound an
uncancellable probe. Do not restart budgets per retry or hide failures as
unready forever. Keep `utc-now`, `continuity-now` and
`workflow-next-timestamp` text contracts separate, including fraction precision,
offsets and historically naive inputs; a workflow advancement rule is not
the host clock. Readiness polling must never replay a mutating RAES apply.

**Locks.** Lifecycle mutations are exclusive, nonblocking and reentrant per
owner; POSIX observations share and exclude mutations. Run finalization is
blocking and reentrant, excluding producers across check/write/seal. Seat,
allocation, workbench preparation and client-state locks have their own scope
and acquisition order. Use stable lock inodes; never replace/unlink a held
rendezvous file or use file/PID presence as ownership. Preserve busy versus
unsupported/unavailable and release after process death. Shared lifecycle
observation fails closed on Windows today, while lifecycle mutation uses a
one-byte CRT lock and rejects reparse points by handle; runstore's Windows
path currently lacks POSIX cross-process locking. Do not turn these into one
portable exclusive-lock policy or silently strengthen/change a domain contract.
Prove lock-family interoperability when Python and Go can share state. Avoid
thread-local reentrancy translated into global or goroutine-ID state.

**Processes.** `workbench/process.py` and `_pipe_exchange.py` preserve a single
deadline covering launch, stdin and capture, a combined output bound, draining
without pipe deadlock, and separately bounded cleanup after every outcome,
including success. Clean the owned group, not just the child; escalate after
the parent exits, reap, and report streams held or unconfirmed group cleanup.
Do not signal unrelated services or an already vanished/reused group.
`exec.CommandContext` alone kills only its process; pipe wait bounds do not
establish descendant termination ([Go exec contract](https://pkg.go.dev/os/exec#CommandContext)).
Qualify platform termination, concurrent cancellation, inherited handles and
Windows argument quoting; no shell interpolation or generic remote/Docker
escape hatch. Preserve argv secrecy independently of later redaction.

**HTTP.** Keep every `CurlOutcome.category`: `http_response`,
`connection_refused`, `timeout`, `tls_handshake`, `empty_reply`,
`connection_reset`, `curl_error`, `request_timeout`, `curl_unavailable`.
Numeric curl exit metadata and spawn-only outcomes have no automatic native
HTTP equivalent: record caller use and a compatibility mapping, rather than
inventing exit codes or merging categories. Classify typed causes, not error
strings. Any HTTP status remains a response even for 401/403/500 or invalid
JSON; polling owners decide authentication, retry and warning policy.
`Accept` applies to bodyless requests; JSON `Content-Type` only accompanies
a body. Bound headers/body, close responses on all paths, propagate deadlines,
and preserve streaming download limits and redirect behavior. The
[HTTP client](https://pkg.go.dev/net/http#Client) has redirect and header-forwarding
defaults that must not broaden credentials or destinations compared with each
existing caller. No implicit retries or ambient proxy policy changes.

## Verification and delivery boundaries

Reuse `tests/test_serialization_vectors.py` and its owner bindings before Go,
and consume the same `conformance/testdata/vectors/` corpus from Go. Extend
conformance for missing foundation contracts first and run against the Python
release; conformance cases are not base-failing regressions. Preserve safe
case-ID-only diagnostics, synthetic credentials and temporary roots.

The repository carries concrete bug lessons: #966 private replacement and
ancestor races (`test_pathsafe.py`); #963 stdin deadlines, output limits,
group escalation and residue (`test_workbench_process.py`); #905 lifecycle
ownership and Windows junctions (`test_lifecycle_guard.py`); #1002 deadline
edges and phased transport outcomes (`test_services.py`, `test_curl_safe.py`);
#623 authentication mismatch (`test_services.py`); #879 exception leakage
(`test_collectors.py`). Also reuse `test_credentials.py`, `test_ssh.py`,
`test_soc_ca.py`, `test_correlation_clock.py`, runstore and archival security
tests. Convert invariants into Go contract evidence, not Python private mocks.
Live closed-`bug` and open planned-use issue searches could not be completed:
`gh` could not connect to `api.github.com`. The repository references above
are evidence anchors, not verified issue status. Complete those searches
before deciding coverage or leaving an incumbent behavior behind.

`checks.yml` currently executes Go tests on Ubuntu; its Windows matrix runs
Python, and Go lint cross-compiles for Windows. `go-gates.sh test` runs fuzz
seeds via ordinary tests but no sustained `-fuzz` campaign. Delivery must add
actual Windows Go execution for ACLs, locks, reparse rejection and replacement,
and bounded CI fuzz campaigns for containment and canonical encoding through
the existing routing/gate owners. Do not claim skipped cases, fake platform
calls or compile-only checks satisfy that evidence. Use `testing/synctest`
for timers, plus real isolated filesystem/process/TLS tests; mutation,
race/shuffle, whole-repository architecture and existing security gates remain
required. No lower thresholds or new suppression to pass.

Local verification stays scoped: `tools/run-targeted-tests.sh` with explicit
test paths, then staged-file `pre-commit run`. Full suites, coverage,
whole-tree lint/prose and architecture runs belong to CI. The explicit design
check is the required pre-code gate. This documentation-only preflight does
not claim those delivery gates passed. The delivery PR targets `go-cutover`,
keeps Python trace links and adds `IMPLEMENTS`/`TESTS` links of the GRC workflow platform
for SYS-009 to Go artifacts. No release before port 31.

Non-goals: implementation of these packages or their consumers in this
preflight; Python changes, user documentation, distribution changes, new
features, a Go redactor, credential discovery, CA generation, auth/schema
redesign, workflow retries, a persistence model, copied RAES/env-packs
semantics, scenario facts, or a general-purpose effects framework. Functional
gaps become separate bug issues; do not repair them covertly during parity.
