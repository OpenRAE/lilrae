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
| Python float text is the shortest text that reads back the same value. It uses the exponent form when the decimal point position is at most −4 or above 16, with at least two exponent digits. | `repr` of Python floats; vectors `float-exponent`, `float-one`. |
| `loads_strict` keeps integers exact, reads a literal with a fraction or an exponent as a float, and rejects duplicate names, invalid UTF-8, non-finite constants, and trailing data. | `strict-json` vectors; `utils/strict_json.py`. |
| `loads_strict` also accepts a number that overflows to infinity. #1610 fixes it on `dev`. | Probe of `loads_strict("1e400")`. |
| `github.com/gowebpki/jcs` v1.0.2 canonicalizes JSON text with the RFC 8785 rules. It rejects duplicate names, invalid UTF-8, and nesting deeper than 10000 levels. It is under the Apache 2.0 license. | Module source and its tests. |
| `encoding/json/jsontext` rejects duplicate names and invalid UTF-8 by default, and it gives the text of each number token. | Go 1.27 documentation and a probe. |

## Decisions

1. **One function for each scheme.** `canonical.RFC8785` returns the RFC 8785
   form, `canonical.SortedCompactJSON` returns the bytes of the
   `sorted-compact-json` scheme, and `canonical.DecodeStrict` decodes the
   `strict-json` scheme. `digest.SHA256Hex` and `digest.SHA256Ref` return the
   hex and the `sha256:` spellings. A scheme that holds a LilRAE concept stays
   with its owner (decision 3 of #1557). A variant that only an owner uses,
   for example raw UTF-8 or the default separators, comes with the Go port of
   that owner.
2. **One value model.** The encoders take, and `DecodeStrict` returns, a JSON
   value as `nil`, `bool`, `string`, `int`, `int64`, `*big.Int`, `float64`,
   `[]any`, or `map[string]any`. An integer and a float are different values,
   as in Python: `1` and `1.0` encode differently. An encoder rejects any
   other type, and each string that is not valid UTF-8.
3. **RFC 8785 through the library.** `RFC8785` rejects an integer outside
   ±(2^53 − 1) and each non-finite float, as the Python library does. Then it
   writes the value as JSON text and gives it to `jcs.Transform`. The library
   does the sort, the escapes, and the number form.
4. **Python text in one encoder.** No library writes the Python forms, so
   `SortedCompactJSON` writes them. It sorts names by code point, which is
   the byte order of UTF-8, and it escapes and formats as the evidence states.
   The Python vectors fix each byte, and the corpus gains a case with the
   float forms at each boundary of the exponent rule.
5. **Strict decoding.** `DecodeStrict` reads the tokens of `jsontext`. A
   number without a fraction or an exponent is an integer (`int64`, or
   `*big.Int` when it does not fit). Another number is a `float64`, and a
   number that overflows is rejected. The decoder reads one value and rejects
   trailing data. The overflow case gets a vector when `go-cutover` takes
   #1610.
6. **Errors with no input.** An error names the rule and the position, not
   the value, because the input can be a secret.
7. **Tests read the corpus.** The tests read `conformance/testdata/vectors/`
   and compare exact bytes, digests, and rejection stages. The `$int` and
   `$float` tags stay in the tests. Fuzz tests check that strict decoding
   never panics, that a decoded value survives a round trip through
   `SortedCompactJSON`, and that `RFC8785` returns its own input when it
   reads its own output. `tools/ci/go-gates.sh fuzz` runs each fuzz test for
   a bounded time in CI.

## Data flows and threat model

```text
caller value or bytes -> canonical / digest -> bytes, digest, or error
corpus files ----------> Go tests -----------> pass or fail with the case ID
```

| Threat | Mitigation |
| --- | --- |
| Two values encode to the same bytes, or one value to two forms, so a digest matches the wrong record. | One function for each scheme, exact vectors, and fuzzed round trips. Integers and floats stay distinct. |
| A crafted input exhausts memory or the stack. | `jsontext` and `jcs` limit the nesting. The callers limit the input size. |
| Invalid UTF-8 or a duplicate name makes two readers see different values. | The decoder and the encoders reject both. |
| An error or a log prints a secret. | Errors name the rule, not the value. |
