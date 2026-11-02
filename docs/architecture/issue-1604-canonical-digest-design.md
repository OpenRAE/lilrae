---
design: 1
issue: 1604
packages:
  - path: internal/canonical
    component: canonical-forms
    imports:
      - github.com/gowebpki/jcs
    test_imports:
      - github.com/google/go-cmp
  - path: internal/digest
    component: digest
  - path: tools/internal/mutation
    component: mutation-check
    imports:
      - github.com/OpenRAE/lilrae/tools/internal/git
      - github.com/OpenRAE/lilrae/tools/internal/golayout
    test_imports:
      - github.com/google/go-cmp
      - github.com/OpenRAE/lilrae/tools/internal/gittest
model_changes:
  - component:canonical-forms
  - component:digest
---

# Issue #1604: Canonical forms and digests design

This design adds the first two foundation packages of Go port 06
([#1557](issue-1557-go-foundation-design.md)): the generic canonical JSON
forms and the SHA-256 digest spellings. The front matter of this note is its
design record.

## Evidence

| Fact | Source |
| --- | --- |
| RFC 8785 sorts member names by UTF-16 code units and writes numbers in the ECMAScript form. The Python `rfc8785` library rejects an integer outside ±(2^53 − 1), and each non-finite float. | `rfc8785` vectors: `key-order-utf16`, `integers`, `integer-above-safe-range`, `nan`. |
| `json.dumps(sort_keys=True, separators=(",", ":"))` sorts names by code point, escapes each character outside U+0020 to U+007E, writes Python float text, and writes `NaN`, `Infinity`, and `-Infinity`. | `sorted-compact-json` vectors; the Python `json` module. |
| With `ensure_ascii=False` and `allow_nan=False`, `json.dumps` escapes only `"`, `\`, and the control characters, and it rejects each non-finite float. `lilrae_runtime_evidence._json_bytes` is the only Python caller of that sorted form. | `runtime-evidence-json` vectors; a search of `src/`. |
| Python float text is the shortest text that reads back the same value. It uses the exponent form when the decimal point position is at most −4 or above 16, with at least two exponent digits. | `repr` of Python floats; vectors `float-exponent`, `float-one`. |
| `loads_strict` keeps integers exact, reads a literal with a fraction or an exponent as a float, and rejects duplicate names, invalid UTF-8, non-finite constants, and trailing data. | `strict-json` vectors; `utils/strict_json.py`. |
| `loads_strict` also accepts a number that overflows to infinity. #1610 fixes it on `dev`. | Probe of `loads_strict("1e400")`. |
| Python reads and writes no integer with more than 4300 decimal digits by default. | `sys.get_int_max_str_digits()`; probes of `loads_strict` and `json.dumps`. |
| `github.com/gowebpki/jcs` v1.0.2 canonicalizes JSON text with the RFC 8785 rules. It rejects duplicate names, invalid UTF-8, and nesting deeper than 10000 levels. It is under the Apache 2.0 license. | Module source and its tests. |
| `encoding/json/jsontext` rejects duplicate names and invalid UTF-8 by default, and it gives the text of each number token. | Go 1.27 documentation and a probe. |

## Decisions

1. **One function for each scheme.** `canonical.RFC8785` returns the RFC 8785
   form, `canonical.SortedCompactJSON` returns the bytes of the
   `sorted-compact-json` scheme, and `canonical.DecodeStrict` decodes the
   `strict-json` scheme. `canonical.SortedCompactUTF8JSON` returns the same
   sorted form with raw UTF-8 and no text for a non-finite float; the
   `runtime-evidence-json` vectors, whose owner uses that form, define its
   bytes. `digest.SHA256Hex` and `digest.SHA256Ref` return the hex and the
   `sha256:` spellings. A scheme that holds a LilRAE concept stays with its
   owner (decision 3 of #1557). The form with the default separators also
   converts unknown types with `str`, so it comes with the Go port of its
   owner.
2. **One value model.** The encoders take, and `DecodeStrict` returns, a JSON
   value as `nil`, `bool`, `string`, `int`, `int64`, `*big.Int`, `float64`,
   `[]any`, or `map[string]any`. An integer and a float are different values,
   as in Python: `1` and `1.0` encode differently. An encoder rejects any
   other type, and each string that is not valid UTF-8. As in Python, no
   function reads or writes an integer with more than 4300 digits, which
   also bounds the cost of a long number.
3. **RFC 8785 through the library.** `RFC8785` rejects an integer outside
   ±(2^53 − 1) and each non-finite float, as the Python library does. Then it
   writes the value as JSON text and gives it to `jcs.Transform`. The library
   does the sort, the escapes, and the number form.
4. **Python text in one encoder.** No library writes the Python forms, so
   `SortedCompactJSON` writes them. It sorts names by code point, which is
   the byte order of UTF-8, and it escapes and formats as the evidence states.
   The Python vectors fix each byte, and the corpus gains a case with the
   float forms at each boundary of the exponent rule, and cases at the
   integer digit limit.
5. **Strict decoding.** `DecodeStrict` reads the tokens of `jsontext`. A
   number without a fraction or an exponent is an integer (`int64`, or
   `*big.Int` when it does not fit). Another number is a `float64`, and a
   number that overflows is rejected. The decoder reads one value and rejects
   trailing data. The overflow case gets a vector when `go-cutover` takes
   #1610.
6. **Errors with no input.** An error names the rule that the input breaks,
   and a decode error gives the byte offset. No error holds the input, because
   the input can be a secret. `jcs` errors can quote the input, so `RFC8785`
   replaces them.
7. **Tests read the corpus.** The tests read `conformance/testdata/vectors/`
   and compare exact bytes, digests, and rejection stages. The `$int` and
   `$float` tags stay in the tests. Fuzz tests check that strict decoding
   never panics, that a decoded value survives a round trip through
   `SortedCompactJSON` and `SortedCompactUTF8JSON`, and that `RFC8785`
   is stable on its canonical byte output. Re-decoding that output through
   the Python-shaped value model is not always a valid idempotence check:
   a large float can become integer text outside the RFC encoder's integer
   domain. Check byte stability with the JCS transform in that case; do not
   discard every second-encoding error as an acceptable fuzz result.
   `tools/ci/go-gates.sh fuzz` runs each fuzz test for a bounded time in CI.

## Data flows and threat model

```text
caller value or bytes -> canonical / digest -> bytes, digest, or error
corpus files ----------> Go tests -----------> pass or fail with the case ID
```

| Threat | Mitigation |
| --- | --- |
| A caller selects the wrong form or changes a projection, so a digest identifies the wrong record. | Named schemes and exact vectors. Python forms preserve integer/float spelling and signed float zero; RFC 8785 intentionally merges some spellings, including `1`/`1.0` and signed zero. Canonicalization is not an injective encoding of Go types. |
| A crafted input exhausts memory or the stack. | Bound encoder traversal before calling JCS, as well as decoder nesting. The callers limit input size and projected output size. |
| Invalid Unicode or a duplicate name makes two readers see different values. | Strict decoding rejects duplicates, including escaped aliases at every level. Encoders validate string values and keys; maps cannot retain duplicate names for later detection. |
| An error or a log prints a secret. | Errors name the rule, not the value. |

## Repository guardrails

The existing [foundation preflight](issue-1557-go-foundation-preflight.md)
supplies the shared security rules. These are the passages specific to 06a;
they do not authorize porting its consumers in this issue.

| Layer / canonical incumbent | Required boundary |
| --- | --- |
| Authentication and request shapes: `src/aptl/api/{deps,session,schemas}.py`, `api/middleware/bff.py`, MCP common `src/server.ts` | Existing token/session, Host/Origin, capability and closed argument-schema gates remain before application calls. These packages add no entry point. A digest does not authenticate a request or authorize access. |
| Configuration and environment: `core/config.py:AptlConfig`, `core/_credential_sources.py:EnvironmentGrant`, `core/env.py`, deployment `_environment_bindings.py` and `_compose_environment.py` | Owners validate exact descriptor, grant and environment shapes before projecting values. Hash the credential descriptor, never resolve its variable to a secret. Foundation accepts explicit values and reads no environment or configuration. |
| Syntax versus semantic admission: `utils/strict_json.py`, ADR-025/065, RAES public models, `core/experiment/{spec_loading,resolver,policy}.py` | `DecodeStrict` validates generic JSON syntax only. A later typed reader must still enforce exact field names, unknown-field rejection, required/null/zero rules and semantic validation before effects. Do not marshal the generic map back to JSON merely to validate a DTO, or copy RAES schemas into foundation. |
| Errors and observability: ADR-029/065, `utils/{redaction,logging}.py`, MCP redaction and telemetry, existing CLI/API/MCP error presentation | Return safe rule/offset metadata without raw parser errors, offending keys, tokens, values or partial output. Wrapping an unsafe cause with `%w` still leaks it. Add no exception hierarchy without a caller that branches on it. Foundation does not log or export spans; entry owners retain error envelopes and redaction. |
| OS and persistence: `utils/pathsafe.py`, `core/runstore.py`, `core/runstore_internals.py`, evidence content store and archival/bundle owners | Production functions perform no file, process or network I/O, so they need no argv, temporary files, environment binding or file permissions. Later owners supply contained reads, size limits, redaction, locks and atomic publication. A hash neither redacts low-entropy secrets nor supplies a MAC/signature. Do not hash a redacted substitute when the owner's contract requires original bytes. |
| Architecture and delivery: `architecture/model.yaml`, root `go.mod`/`go.sum`, `.golangci.yml`, `.gc/pack-ownership.json`, `.ground-control.yaml`, `.gc/plan-rules.md` | Keep `canonical-forms` and `digest` as separate foundation components. JCS belongs only to canonical; SHA-256 uses `crypto/sha256` and `encoding/hex`. Neither component needs a dependency on the other, product packages, tools, plugins or scenario facts. Retain the existing machine-readable design record and generated diagram. |

Reuse `docs/reference/serialization-schemes.md`, the corpus contract in the
[#1555 design](issue-1555-serialization-vectors-design.md), and
`tests/test_serialization_vectors.py` with `tests/serialization_owner_schemes.py`.
They define the owner, framing, options, expected bytes and rejection stage;
the Go tests must not invent a second corpus schema or regenerate expectations
with the Go encoder. Check corpus version, scheme, closed fields and nonempty
cases. Type tags stay test-only, even when an ordinary caller map happens to
contain `$int` or `$float` keys.

## Encoding limits and compatibility edges

- **Bound the whole traversal.** Each encoder permits at most 10000 nested containers. The JCS depth check runs after the Go value
  has been serialized. It cannot protect that traversal, and it does not
  protect either Python encoder. Bound container depth during every encoder
  traversal, including cyclic maps/slices, with a documented limit aligned
  with the JSON libraries. Reject safely instead of panicking, recovering a
  stack overflow, or accepting unbounded recursion. A depth bound can reject
  cycles without a general object-identity framework. Permit repeated,
  noncyclic children. Check huge integer magnitude before expensive decimal
  conversion; checking the resulting string length alone does not bound that
  work. Input/output byte budgets belong to the consuming boundary, not a
  product-wide settings schema here.
- **Keep the number domains separate.** Preserve arbitrary integers for the
  Python forms and strict reader within the stated digit limit. Do not pass
  them through `float64`, including in tests. RFC rejects unsafe *integer*
  inputs but accepts finite binary64 floats whose magnitude exceeds that
  range. Preserve the sign of `-0.0`; integer `-0` decodes to integer zero.
  Python exponent cutovers, exponent padding, subnormals, underflow and
  shortest-round-trip ties need independent byte evidence, not an assumption
  that Go's default float formatting is Python's. `1e400` rejection is the
  explicit strictness decision above, not evidence of Python parity; retain
  the #1610 compatibility dependency when reconciling its vector.
- **Validate Unicode without rewriting it.** Do not normalize strings,
  HTML-escape markup, replace invalid UTF-8/surrogates with U+FFFD, or use Go
  map iteration order as canonical order. Test escaped duplicate names and
  malformed surrogate escapes as well as invalid raw UTF-8. The strict Go
  reader rejects malformed Unicode even where Python accepts an escaped
  lone surrogate; record this as ADR-065 strictness, not an encoding repair.
  Outputs have no BOM or final LF. Owners add their own framing where their
  vectors require it.
- **Keep values stable during a call.** No input map, slice or `*big.Int` is
  mutated by these functions. Callers must not mutate shared inputs
  concurrently. No reflection-based DTO serializer, custom marshal hook or
  `Stringer` fallback expands the explicit value model. Define nil containers
  consistently with empty JSON containers; `nil` itself represents null and
  a nil `*big.Int` remains an error.

The extension seam is owner composition: project and validate a value, choose
one named encoder, add the owner's explicit domain/framing, then hash bytes
and choose the stored spelling. The existing private Python writer shares
escape/number mechanics between its fixed forms. Add another named generic
form only when an owner and vectors require it; no public options bag, scheme
registry, algorithm negotiation or domain-aware `HashMapping` helper.

## Verification boundary and non-goals

`tools/ci/go-gates.sh fuzz [FUZZTIME]` already discovers fuzz targets, and
`.github/workflows/checks.yml` runs it with `30s` per target. Reuse that
parameter and `tools/ci/select_checks.py`; ordinary seed execution alone does
not satisfy the bounded fuzz acceptance criterion. Fuzz round trips do not
replace exact vectors. Include direct encoder evidence for cycles/depth,
arbitrary float inputs and map-order independence; byte-only strict-reader
fuzzing cannot construct cycles or non-finite compatibility values. Compare
float sign bits explicitly because ordinary equality loses signed zero.
Failure diagnostics and saved fuzz inputs must contain synthetic data only.

Use the existing mutation gate and `tools/mutation-thresholds.json` without
lowering thresholds or adding suppressions. The required pre-code gate is
`go run -C tools ./cmd/archcheck design -base origin/go-cutover
docs/architecture/issue-1604-canonical-digest-design.md`. A pass now validates
the current record; since code already exists in this checkout, it does not
prove that the check preceded implementation. CI owns whole-repository
architecture/diagram checks, race/shuffle, full suites and mutation evidence;
local tests stay targeted through `tools/run-targeted-tests.sh`.

Non-goals are caller migrations, YAML, new digest algorithms, digest parsing
or normalization, domain projections/identities, DTOs, validation policy,
redaction implementation, persistence, authentication and workflow changes.
The UTF-8 sorted form shares generic encoding mechanics and is justified by
its existing owner vectors; the runtime-evidence concept remains outside.
This preflight changes guidance only and is not an implementation plan or a
claim that the issue's delivery gates have passed.

## Mutation module boundary

Gremlins v0.6.0 walks nested modules, but the Go coverage run excludes them.
The mutation gate excludes each nested module directory from its parent run.
It finds these directories from go.mod files and quotes their paths as regular expressions.
Each nested production module keeps its own mutation run and thresholds.
This prevents false uncovered mutants without removing any module from verification.
A two-module fixture must fail before this repair and pass afterwards.
The gate still receives fixed argument arrays and no secrets.
