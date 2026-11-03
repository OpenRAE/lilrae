# Issue #1608: Host HTTP client architecture preflight

The boundary is `internal/httpclient`: HTTP mechanics in the existing
foundation layer, using `net/http`, `crypto/tls`, and `crypto/x509`. It must
consume caller-supplied trust and policy without becoming a service client.
This note refines the [#1557 design](issue-1557-go-foundation-design.md) and
[preflight](issue-1557-go-foundation-preflight.md) under SYS-009 and
[ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md).
Inspection used `6d3e220b` on `1608-host-http-client`.

This is guidance, not an implementation plan or a passed design check. Before
Go code, the delivery design must record its exact package/import permissions
and model changes in `issue-1608-<topic>-design.md` front matter and pass
`go run -C tools ./cmd/archcheck design -base origin/go-cutover <note>`.
Use the base configured in `.ground-control.yaml` if it changes. Do not add
empty packages or stale model entries just to claim a gate passed.

## Existing contracts and ownership

| Canonical incumbent | Contract the Go design must preserve |
| --- | --- |
| `src/aptl/utils/curl_safe.py:curl_request`, `CurlOutcome`; `tests/test_curl_safe.py` | Status takes precedence over transport category. Any HTTP status, including 401/403/500, is a response; invalid JSON does not erase it. No redirects (`-L` is absent), no automatic retries, and no warning per polling attempt. `Accept: application/json` accompanies JSON requests; JSON `Content-Type` only accompanies a body. These headers belong to the JSON consumer, not every HTTP request. |
| `curl_safe.py:curl_json`; `core/collectors.py`; `services/misp_suricata_sync/misp_client.py`; `core/deployment/_wazuh_attestation.py` | `-f` makes HTTP errors, nonzero process exits, subprocess failures/timeouts and invalid JSON collapse to `None`. The consumer retains this policy above the HTTP result. An unavailable MISP response is distinct from a valid empty IOC set; failure must not erase installed rules. |
| `src/aptl/core/services.py:WazuhApiProbe`, `_api_failure`, manager/indexer probes | Credential-free transport check precedes authentication and manager-status interpretation. `curl_exit` is copied into the probe and displayed by `describe()` only when no HTTP status exists. No host consumer branches on a particular numeric curl exit. Preserve phase, category and status; never fabricate a Go process exit code. Any externally visible removal/change of numeric metadata needs a consumer compatibility decision. |
| `src/aptl/appliance/download.py`; `tests/test_appliance_download.py` | HTTPS-only requests and bounded HTTPS redirects (handler limit 5), exact size/length/range checks, metadata cap at 1 MiB, incremental artifact reads, digest verification and atomic cache publication. Only the original URL's 401 challenges authorize the existing token flow. HTTP transport must expose the necessary headers and response identity without owning authentication, resume or cache policy. |
| `src/aptl/workbench/browser_gateway.py`; `tests/test_browser_gateway.py` | Fixed loopback upstreams, participant authorization and rechecks, filtered hop headers/session cookies, no ambient proxy (`trust_env=False`), no redirects, 30s HTTP and 60s outer budgets, 16 MiB request and 64 MiB response caps. Response bytes are raw. Proxy header/cookie rewriting and WebSockets remain gateway responsibilities. |
| `mcp/aptl-mcp-common/src/{http,endpoint-url,config}.ts` and HTTP/security tests | Existing future consumers already have same-origin endpoint admission before attaching auth, configured CA resolution, and timeout/error contracts. Preserve these when porting their owners; do not import TypeScript models or JWT exchange into foundation, or assume every current MCP transport has identical redirect behavior. |

The source audit covers the current repository's host product callers. Curl
inside containers, shell build/publish scripts, guest programs and developer
tools retain their existing runtime owners; “one HTTP client” is not permission
to move their network effects onto the host or migrate them in this issue.
The raw-URL warning paths in `curl_json` are existing exposure risks, not a
logging precedent to copy; native failures must meet ADR-029 from the outset.

## Outcome compatibility: resolve before code

Keep all nine category spellings. Classify with `errors.Is`/`errors.As`, typed
OS/network/TLS causes and the phase of the operation, never text matching.
The existing mapping is numerical, not a complete description of Go failures:

| Category | Existing evidence and required native distinction |
| --- | --- |
| `http_response` | Any parsed final HTTP status wins, even with a failed or oversized body. Preserve status separately from a safe body-completion error; incomplete bytes must not be accepted as a complete payload. |
| `connection_refused` | Curl 7 means failure to connect, broader than its category name. Use typed connect-phase causes; distinguish DNS resolution (curl 6, currently `curl_error`) and timeouts. Record which connect causes are included on each supported OS. |
| `timeout` | Curl 28. A transport/phase timeout is distinct from the encompassing operation deadline. Current `_run_curl` supplies a subprocess timeout, not `--max-time`; elapsed duration alone cannot choose this category. |
| `tls_handshake` | Curl 35: failure to complete negotiation. An EOF/reset during TLS negotiation must not become an HTTP empty reply. This category does not prove bad credentials or a bad certificate. |
| `empty_reply` | Curl 52: no HTTP response. Distinguish EOF before final response headers from a valid zero-length response and a truncated body after headers. |
| `connection_reset` | Curl 56: receive failure, broader than a reset errno. Use receive-phase typed evidence; record how truncation and other receive failures are represented without losing an observed status. |
| `curl_error` | All other completed curl errors, including certificate verification failure (curl 60), DNS failure and malformed protocol. Check typed verification errors before general handshake failure; do not relabel all TLS errors `tls_handshake`. |
| `request_timeout` | Python `TimeoutExpired` before curl completion. Native equivalent is the overall request budget expiring, including reading the body. An earlier caller deadline caps that budget; it must not restart on redirects or reads. |
| `curl_unavailable` | Python `OSError` starting curl. There is no native executable to be missing. Keep the category in the compatibility vocabulary, explicitly mark native unreachability, and prove that disposition in tests. If delivery proposes a native producer, it must name an actionable typed cause and justify the mapping before code; DNS, TLS, HTTP errors and invalid options are not subprocess startup failures. |

The delivery design must settle classification precedence, typed/phase
coverage and the compatibility-only category's test evidence before its design
check. A table test of category strings is insufficient proof of each reachable
native failure. Do not introduce a fake curl runner or invoke curl to manufacture
coverage for a native client. Keep caller cancellation detectable with
`errors.Is(..., context.Canceled)`; do not report user cancellation as a timeout.
If a category is required alongside cancellation, record that choice explicitly.

The verification distinction follows both the repository's curl-60 test and
the [curl error contract](https://curl.se/libcurl/c/libcurl-errors.html).
Go exposes a typed
[certificate verification error](https://pkg.go.dev/crypto/tls#CertificateVerificationError).
Record phase at the effect boundary where the public Go error types alone
cannot distinguish negotiation, request transmission and response reading.

## Transport, trust and resource guardrails

- **Trust is per client.** Accept explicit roots/trust mode from wiring. An
  explicit bundle is not an instruction to append system roots; system trust
  is a separate choice, and an explicit empty/invalid bundle fails closed.
  Missing, unreadable or malformed configured roots must not fall back to
  system trust or insecure mode. Verify chain and hostname/SAN, including IP
  destinations. Do not override the TLS server name to make a test pass.
  Existing Wazuh/debug insecure exceptions stay explicit and local, never the
  default or a process-global TLS setting. No CA discovery, certificate
  generation, client identity selection or file watching here.
- **Credentials stay in memory.** Caller-built auth headers and bodies never
  pass through argv, subprocess environments or temporary curl files. Reject
  URL userinfo rather than letting `net/http` synthesize Basic auth. Admitted
  URLs and query strings remain sensitive and never become diagnostics;
  credential placement remains headers/body, not URL parameters. Validate
  request syntax, headers and positive finite bounds before network I/O using
  standard parsers and HTTP validation, without building a competing URL or
  service-schema validator.
- **Redirects are explicit.** Default to returning the 3xx response for curl
  and gateway consumers. Downloads opt into bounded HTTPS redirects. Admit
  every destination before sending anything; compare scheme, host and
  effective port, not just hostname/subdomain. Define method/body replay and
  credential-header handling, including custom API-key headers, cookies,
  proxy auth and Referer. A rejected redirect still leaves a real 3xx status;
  do not accidentally discard it through `CheckRedirect` error handling.
  No implicit cookie jar or session shared between callers. Go's
  [redirect defaults](https://pkg.go.dev/net/http#Client.Do) can forward
  sensitive headers to subdomains or a different scheme on the same host.
- **Proxy authority is explicit.** Curl/urllib can consult ambient proxies;
  the gateway deliberately cannot. Resolve that policy in wiring and pass it
  in, including a direct mode; do not inherit `ProxyFromEnvironment` by
  accident. Keep proxy credentials out of errors and origin headers. Never
  use process-wide environment mutation to select trust or proxy policy.
- **One bounded operation.** Context is the first I/O argument. The earliest
  caller deadline/request budget covers DNS, connect, TLS, redirects, headers
  and body reads; phase timeouts never extend it. Preserve caller budgets
  (readiness 10s, collectors 120s, other JSON calls 30s, downloads 60s) rather
  than selecting one universal timeout. Reject options that silently select
  unlimited I/O. No abandoned goroutine around an uncancellable read.
- **Bounds apply to actual reads.** Bound response headers and body bytes,
  including chunked replies and bytes after decompression when decoding is
  enabled. Do not trust `Content-Length`, silently truncate success, drain an
  unbounded rejected body for reuse, or allocate an entire artifact. Keep
  wire/raw versus decoded-byte behavior explicit for downloads and proxying.
  Close bodies and release connections on success, read failure, limit,
  redirect refusal and cancellation. Streaming ownership must keep the
  deadline alive until close; returning headers does not finish the request.
- **No hidden workflow.** No retry/backoff/auth refresh/status policy. The
  [standard transport](https://pkg.go.dev/net/http#Transport) can replay some
  requests on reused connections: the delivery design must state how its
  supported protocol/connection settings satisfy the one-attempt contract
  and prove mutations are not replayed. Do not infer safety by adding
  idempotency keys. Reuse transports only within the same immutable trust,
  proxy and credential-isolation policy, with explicit idle-resource cleanup;
  never mutate a shared/default transport or caller-owned TLS config/root
  pool while requests run.

## Required passage through cross-cutting layers

Paths below are incumbents to preserve or compose in their later Go owner,
not imports from foundation into Python/TypeScript or product layers.

| Layer and canonical owner | Required passage |
| --- | --- |
| Auth and endpoint admission: `api/deps.py`, `api/session.py`, `api/middleware/bff.py`, `api/schemas.py`; MCP `server.ts`/Ajv and `endpoint-url.ts`; `BrowserRoute` and gateway authorizer | Existing token/session, Host/Origin, role/capability and closed argument gates precede network effects. Foundation accepts an admitted request, grants no host/network authority, and adds no endpoint passthrough. Destination policy remains with the consumer, applied again to redirects. |
| Config/env/secret binding: `core/config.py:AptlConfig`, `core/env.py`, `utils/placeholders.py`, `core/_credential_sources.py:EnvironmentGrant`, deployment `_environment_bindings.py`, `_compose_environment.py`, `_realization_primitives.py` | Durable config remains non-secret; exact pack/consumer/variable grants, source selection, placeholder and environment-file representability checks stay authoritative. HTTP receives resolved values and never scans env, `.env`, netrc or credential stores. Add no config schema, env aliases or credential hydration. |
| Trust and filesystem: ADR-034, `core/soc_ca.py`, `core/collectors.py:_resolve_lab_ca_path`, sync `ServiceConfig`, MCP `config.ts` | Owners retain explicit CA / `APTL_LAB_CA_PATH` / `APTL_PROJECT_DIR` / project fallback and config-relative resolution. Root loading/admission precedes transport construction; use the contained-file contract of `internal/securefile` when its owner requires contained access. Transport receives roots, not lab paths or private CA keys. |
| Decode and service validation: `internal/canonical` strict decoder, ADR-065, manager probe token/status parsing, sync models, appliance download/seat image owners | Foundation returns bounded bytes/stream plus status/headers, not parsed `any` JSON or service DTOs. First-party models retain strict bounded decoding then semantic validation; external service models follow their service contract. Range/digest/signature/token-challenge checks remain in the owner. |
| Errors and observability: ADR-065, `deployment/errors.py`, `LabResult`/`LabStatus`, API envelopes, MCP `isError`; ADR-029, `utils/redaction.py`, MCP `redaction.ts`/telemetry | Return one safe classified result and actionable errors; no parallel exception tree. Classify private causes before projecting safe metadata. Raw `url.Error`, TLS/parser text, request/response dumps, headers, payloads and URLs cannot leak through wrapping, unwrapping, formatting, JSON, `slog` or spans. Preserve safe `errors.Is`/`As` semantics, especially cancellation, without retaining a secret-bearing error chain. Prefer no foundation logs; caller owns severity and the future shared Go redactor (port 07) owns output redaction. |
| Persistence and OS/runtime: `RunStorageBackend`/`LocalRunStore`, snapshot `to_dict()`, exporter, download cache, `DeploymentBackend` and ownership gates | HTTP persists nothing, starts no subprocess/listener and changes no host trust store, mounts or network exposure. Sensitive response bodies remain outside diagnostic metadata; existing redaction must run before persistence/export. Download/cache integrity and publication do not move into transport. |
| Repository gates: `.ground-control.yaml`, `.gc/plan-rules.md`, `.gc/pack-ownership.json`, `tools/check_pack_boundary.py`, `architecture/model.yaml`, `go.mod`, `.golangci.yml`, `.pre-commit-config.yaml`, `tools/ci/{select_checks.py,go-gates.sh}`, `.github/workflows/checks.yml` | Record one foundation component, exact dependencies and generated diagram through the existing architecture checker. No new linter, global dependency exemption, scenario facts or service constants. Use existing CI routing, race/shuffle, security and Sonar gates; no disabled checks or local whole-suite substitute. |

## Extension seam and evidence

Use a concrete client and the small `Do`/transport interface needed by its
consumer; no effects registry or provider-owned service interface. Per-client
trust/proxy/redirect policy and per-operation context/timeout/response bounds
are the variation points. Preserve a bounded streaming path for the already
existing downloader alongside small buffered JSON responses. Do not force a
future service to change a universal byte cap or add another transport merely
to stream. Avoid speculative option frameworks or authentication plugins.

Delivery evidence must include real loopback HTTP/TLS tests with a generated
test CA: correct roots, unrelated/empty roots, hostname mismatch, expired
certificate, explicit system versus supplied trust, invalid configured roots,
and isolation of verified clients from explicit insecure clients. Generate
test keys at runtime rather than adding a private-key-scanner exemption.
Typed seam tests cover otherwise nondeterministic OS/phase failures; real
sockets prove reachable TLS, EOF/reset, timeout and cancellation behavior.
Existing Python/MCP tests above are contract references, not permission to
copy their patch-heavy test structure.

Evidence must also distinguish all nine categories and the native-unreachable
disposition; preserve 401/403/500 and invalid-JSON status; prove deadline/body
completion, exact-limit and limit-plus-one/chunked/compressed reads, closure,
redirect loops/downgrades/cross-port and custom-header leakage, proxy isolation,
no unintended replay, and secret-free formatting/errors/logs. Use synthetic
secrets, local servers and temporary trust only, never external services.
`testing/synctest` is suitable for deterministic timer logic, not a replacement
for real network tests. Run targeted tests locally and staged `pre-commit run`;
CI owns full suites, whole-repository architecture/diagram/PR checks and the
existing mutation gate (`tools/mutation-thresholds.json`: 100% efficacy and
mutant coverage). A skipped, constant-only or fake-only test does not prove
the transport guarantee. This documentation-only preflight claims none of
the implementation acceptance gates.

Non-goals are caller migration, lab-CA discovery/generation, credentials or
token exchange, retries/readiness workflows, service JSON schemas, proxy or
WebSocket gateway implementation, persistence and a new redaction system.
Avoid conflating status with readiness, transport category with HTTP error,
certificate rejection with negotiation failure, timeout with cancellation,
or bounded sensitive bytes with safe diagnostic data.
