---
design: 1
issue: 1608
packages:
  - path: internal/httpclient
    component: host-http
model_changes:
  - component:host-http
---

# Issue #1608: Host HTTP client design

This design implements the [HTTP preflight](issue-1608-host-http-client-preflight.md).
The [foundation design](issue-1557-go-foundation-design.md) and ADR-070 apply.
The architecture model adds only `host-http` in the foundation layer.
The package uses only the standard library.
Consumers define their small HTTP interfaces.
No existing consumer changes in this issue.

## Contracts and decisions

`New` constructs a concrete client from explicit options.
Options supply a TLS configuration, operation and phase timeouts, header and body limits, proxy selection, and redirect admission.
Timeouts and byte limits must be positive.
The client copies the TLS configuration and its root pool.
Go 1.27 revalidates cached TLS chains against the current roots.
A shared-session regression test proves rejection under an empty pool.
An explicit TLS configuration with nil roots selects system trust.
An empty supplied pool trusts no certificate.
Wiring must reject a malformed configured bundle before construction.
The package reads no files, environment variables, or credentials.
An existing explicit insecure exception can pass its own TLS configuration.
It changes no other client.

`Do(ctx, request)` returns a response with a category, status, and safe error.
The response implements `io.ReadCloser` for bounded streaming.
Consumers can use `io.ReadAll` for small responses or `io.Copy` for artifacts.
Headers and the final URL are available through explicit accessors.
Default pointer and value formatting and JSON expose no headers, URL, or body.
The package writes no logs.
Every raw failure is classified before its text and error chain are discarded.
Cancellation remains detectable with `errors.Is` and `context.Canceled`.

One context budget covers connection, TLS, redirects, headers, and body reads.
The earlier caller deadline wins.
The phase timeout bounds connection, TLS negotiation, and response headers.
The operation deadline remains active until body close or completion.
The body reader checks actual bytes and closes on EOF, error, overflow, or caller close.
It never drains an oversized response.
Compression is disabled, so byte limits apply to raw response bytes.
The consumer owns any decompression and its decoded-byte limit.

The transport uses HTTP/1 with connection reuse disabled.
Thus the standard transport cannot replay a request on a reused connection.
There is no retry loop, cookie jar, authentication, or JSON decoding.
Nil proxy selection means direct access.
Wiring can explicitly supply `http.ProxyFromEnvironment` for existing proxy consumers.

Redirects are disabled by default.
An artifact consumer can enable a finite count and supply a destination admission function.
Only bodyless GET or HEAD requests can redirect, and every hop must remain on HTTPS.
The admission function checks every destination before network access.
Userinfo is rejected on initial and redirected URLs.
Cross-origin redirects remove every request header, including custom credentials.
Origin comparison includes scheme, case-insensitive hostname, and effective port.
Redirects always remove Referer.
A Host override that differs from the URL authority prevents redirects.
The client uses the standard transport for each hop.
It admits redirects before the next hop, without the default HTTP client redirect parser.
A refused or malformed redirect returns its real 3xx response.
The original operation budget still applies.

## Compatibility and caller evidence

The source audit in the preflight identifies every Python host consumer.
`curl_json` collapses nonzero exits into no payload.
Collectors, sync, and attestation consume that payload policy.
`curl_request` is used by manager and indexer probes in `core/services.py`.
They retain the exit in `WazuhApiProbe` and display it when no status exists.
Their policy uses category, status, and payload, never a particular exit number.
The native result has no invented curl exit code.
Later consumer ports retain their status, phase, payload, and display contracts.

| Category | Native evidence, in precedence order |
| --- | --- |
| `http_response` | A final status exists. A later body failure is a separate safe read error. |
| `request_timeout` | The encompassing operation context reaches its deadline. |
| `curl_error` | Caller cancellation, with `context.Canceled` preserved. |
| `timeout` | A typed `net.Error` reports a phase timeout before the operation deadline. |
| `curl_error` | Typed certificate verification or DNS failure. Certificate rejection preserves curl exit 60 semantics. |
| `tls_handshake` | The TLS handshake callback reports negotiation failure, after the preceding distinctions. |
| `connection_refused` | A typed `net.OpError` reports a dial or proxy-connect failure. This includes connect failures beyond refused connections on supported operating systems. |
| `empty_reply` | EOF before final HTTP response headers. |
| `connection_reset` | Unexpected EOF or a typed network read/write failure before final headers. |
| `curl_error` | Other request, protocol, or transport failure. |
| `curl_unavailable` | Compatibility vocabulary only. Native HTTP starts no executable, so this category has no native producer. |

The shared cases are in `conformance/testdata/http-outcomes.json`.
The Python conformance test runs them through the released curl wrapper first.
Go tests use those expectations with typed native causes.
The unavailable case proves its vocabulary and absence from native producers.
No fake curl process is added to Go.

## Data flows and security

```text
[trusted host process]
caller configuration -> New -> private TLS roots and transport
admitted request, context -> Do -> syntax and redirect admission
response metadata <- Do <- HTTP parser
caller sink <- bounded Read <- response body
safe categories and errors <- classification <- private transport failures
                       |
---------------- network trust boundary ----------------
                       |
DNS, explicit proxy, remote HTTP/TLS peer <-> transport
```

The response stream is transient memory, not a persistent store.
The caller owns its sink, credentials, endpoint authority, decoding, and persistence.
Entry authentication and MCP/API argument gates still precede this package.
No new network listener, external destination, or storage service is introduced.

| Asset and threat | Control and verification |
| --- | --- |
| Credentials leak through redirects or diagnostics. | Reject userinfo; strip cross-origin headers and Referer; safe result formatting; synthetic-secret destination and formatting tests. |
| A remote peer uses an untrusted, expired, or wrong-host certificate. | Clone caller trust; chain and hostname verification; real TLS tests with a generated test CA. |
| One insecure caller changes another caller's trust. | Private cloned TLS configurations and pools; isolation tests. |
| A peer consumes unlimited time or memory. | Positive limits; one context budget; streaming read bound; exact-limit, chunked, timeout, and closure tests. |
| A mutation is repeated or sent to another peer. | Fresh HTTP/1 connections; no body or mutating-method redirects; server request-count tests. |
| Ambient proxies expose credentials. | Direct transport unless wiring explicitly supplies proxy selection; proxy isolation tests. |
| A partial body appears complete. | Preserve status and return a safe read error; truncated and oversized response tests. |

The caller must admit the initial destination and any configured proxy.
Response bytes and explicit accessor values remain sensitive.
The later shared redactor protects their presentation and persistence.
Cancellation is cooperative for a caller-supplied request body reader.
The client starts no goroutine to abandon such a reader.

## References and design coverage

| Source | Version and section | Use |
| --- | --- | --- |
| [net/http](https://pkg.go.dev/net/http) | Go 1.27.3, Client, Transport, Protocols | Context lifetime, redirect admission, HTTP/1 replay constraints, and raw reads. |
| [crypto/tls](https://pkg.go.dev/crypto/tls) | Go 1.27.3, Config and CertificateVerificationError | Trust copies and typed certificate failures. |
| [crypto/x509](https://pkg.go.dev/crypto/x509) | Go 1.27.3, CertPool | Explicit system trust and copied caller roots. |
| [httptrace](https://pkg.go.dev/net/http/httptrace) | Go 1.27.3, ClientTrace | Typed handshake-phase evidence. |
| [curl errors](https://curl.se/libcurl/c/libcurl-errors.html) | libcurl, codes 6, 7, 28, 35, 52, 56, 60 | Compatibility distinctions and absent native exit codes. |
| [Sonar analysis scope](https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/project-analysis/setting-analysis-scope/setting-initial-scope) | SonarQube Cloud, Initial scope | Explicit source and test roots, with disjoint file patterns. |
| [ASD-STE100](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf) | Issue 9, sections 1, 5, 6 | Technical terms, short sentences, and one subject per sentence. |

The model and generated component diagram describe package dependencies.
The data flow and threat table describe the network boundary and its controls.
No new ADR is needed: these choices implement ADR-070 and the accepted foundation boundary.
No deployment diagram changes: this package creates no service or deployment resource.
The architecture model and existing CI gates provide the policy checks.
The Sonar configuration includes `internal/` as source and test scope.
File patterns separate product tests from production files.
The scope contract test checks every Go file below that directory.
CI owns whole-repository architecture checks and the 100% mutation gate.
Local verification uses only the affected package and changed documents.
