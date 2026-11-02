# Issue #1557: Go foundation design

This design splits Go port 06 into six sub-issues and records the decisions
that they share. It refines the [preflight](issue-1557-go-foundation-preflight.md).
Each sub-issue has its own design note, and the front matter of that note is
the design record of its packages.

## Decisions

1. **One sub-issue for each concern.** The concerns of #1557 have separate
   contracts, platform behavior, and tests. One pull request for all of them
   is too large to review with care, so `.gc/plan-rules.md` applies: each
   sub-issue delivers one pull request, and #1557 tracks them.

   | Sub-issue | Packages | Contracts |
   | --- | --- | --- |
   | 06a (#1604) | `internal/canonical`, `internal/digest` | The generic vectors of Go port 04 |
   | 06b (#1605) | `internal/securefile` | Contained access, atomic writes, file modes, and Windows ACLs |
   | 06c (#1606) | `internal/clock`, `internal/wait` | The timestamp vectors and the deadline waits |
   | 06d (#1609) | `internal/filelock` | Shared, exclusive, and Windows locks |
   | 06e (#1607) | `internal/process` | Argument arrays, process groups, output limits, and termination |
   | 06f (#1608) | `internal/httpclient` | The lab CA and the outcome categories of `curl_safe` |

2. **Foundation layer.** Each package is a component of the `foundation`
   layer of `architecture/model.yaml`, with no LilRAE concept. A package uses
   only the standard library, the modules of ADR-065, and other foundation
   packages. `tools/cmd/archcheck` enforces the layer. The `go-arch-lint`
   item of #1557 refers to the checker that ADR-065 replaced.
3. **Scheme ownership.** Foundation implements the generic schemes: RFC 8785,
   the sorted JSON forms of Python, strict JSON decoding, the SHA-256
   spellings, and the timestamp forms. Their vectors are `rfc8785`,
   `sorted-compact-json`, `strict-json`, `sha256-bytes`, `utc-now`, and
   `continuity-now`. A scheme that holds a LilRAE concept, for example a
   provenance identity or a trial plan, stays with the package that owns the
   concept. That package composes the foundation functions, and the Go port
   of its owner must pass its vectors.
4. **Compatibility encoders are not readers.** Some vectors record that the
   Python encoders write `NaN` and `Infinity`. The compatibility encoder of
   such a scheme writes the same bytes. A first-party reader stays strict, as
   ADR-065 states, and rejects those constants.
5. **Effects behind small interfaces.** The clock, file access, process runs,
   and HTTP have interfaces that the consumer defines, and fakes in tests.
   Real platform behavior has real tests: files, locks, and processes on
   Linux, macOS, and Windows, and TLS with a test CA.
6. **No weaker platform fallback.** A guarantee that the Python code gives
   on a platform, for example a private file mode or a Windows ACL, is a floor.
   When a Go API cannot give the guarantee, that operation is not delivered
   until it can.
7. **CI evidence.** Sub-issue 06b adds a Go test job on Windows, and 06a adds
   bounded fuzz runs for canonical encoding. 06b adds the fuzz runs for
   containment. A test that skips, a fake platform call, or a cross-compile is
   not evidence for platform behavior.
8. **Locks exclude the Python release.** A Python process can still run on a
   project when the Go release starts, for example during an upgrade. Thus
   06d uses the lock primitive of each Python caller, and a test proves that
   a Go lock and a Python lock on one file exclude each other.

## Data flows and threat model

```text
caller (later port) -> foundation function -> OS, network, or bytes
                    <- value, or an error with no secret
```

The assets are the files and directories that callers own, the secrets that
pass through process arguments and HTTP requests, and the bytes that records
store. Each sub-issue design gives the threats of its packages. These threats
apply to all of them:

| Threat | Mitigation |
| --- | --- |
| A path escapes its root through `..`, a link, or a special file. | 06b rejects the path before any access and opens each component without following links. |
| A secret leaks through an error, a log, or a process argument. | Errors carry operation names and categories, not values. Secrets pass through files or memory, not through argument arrays. |
| A canonical form changes, so a stored digest no longer matches. | The Go port 04 vectors fix the bytes, and the tests read the same corpus. |
| A wait, a lock, or a process outlives its deadline. | Each operation takes a context and a deadline, and the tests run with `testing/synctest` and real processes. |
| A TLS client trusts the wrong root or follows a redirect with credentials. | 06f takes the trust roots from the caller and copies the redirect rules of each current caller. |
