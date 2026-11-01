# Issue #1555: Serialization Vectors Design

This design records the persisted byte and identity schemes of the Python
implementation as language-neutral vectors. It refines the
[preflight](issue-1555-serialization-vectors-preflight.md). The change adds no
Go code and changes no product behavior, so it needs no design record and no
model change.

## Evidence

| Fact | Source |
| --- | --- |
| `src/` has 120 `hashlib.sha256` calls, 50 `json.dumps` calls with `sort_keys`, 33 `rfc8785.dumps` calls, 1 BLAKE3 call, 1 `hashlib.new` call, 1 MD5 call, 2 `uuid5` calls, and 49 random identifier calls, in 143 files. | AST scan of `src/` at the base of this branch. |
| The lock pins RAES 10.1.0, PyYAML 6.0.3, and rfc8785 0.1.4. | `uv.lock`. |
| `utils/strict_json.py` rejects duplicate members and non-finite constants; `json.loads` accepts both. | Source. |
| The Parquet projection decoded RFC 8785 bytes as ASCII, so a non-ASCII reference failed. #1599 fixes it on `dev`. | Reproduction; #1598. |

## Decisions

1. **One corpus beside the conformance cases.** The vectors are JSON files in
   `conformance/testdata/vectors/`, one file for each scheme. The Go ports read
   the same files. The Python tests call the existing owner of each scheme; no
   test computes its expected value with the code under test.
2. **Corpus format.** Each file has `corpus` (1), `scheme` (a stable ID),
   `version` (the scheme version that its owner states, or `current`),
   `owner` (the module and function), and `cases`. A case has an `id`, an
   input, and an expected result: the exact bytes as hex, the digest, or a
   rejection with its stage (`parse`, `validate`, or `serialize`).
3. **Inputs that JSON cannot carry.** Raw input bytes are hex
   (`input_hex`). A number that JSON text would change is a tagged string: an
   exact integer as `{"$int": "<decimal>"}`, and a float as
   `{"$float": "<repr>"}`, which includes `nan`, `inf`, `-inf`, and `-0.0`.
   The tags exist only in the corpus.
4. **Closed dispatch.** `tests/test_serialization_vectors.py` maps each scheme
   ID to one owner call. A corpus file with an unknown scheme, an unknown case
   field, or no cases fails the test. A failure names the scheme and the case
   ID; it prints no input and no expected bytes.
5. **Inventory.** `docs/reference/serialization-schemes.md` lists each scheme:
   its owner, input domain, byte form, hash and digest spelling, the records
   and fields that store or compare its output, and its vector file. It also
   lists the generated files whose digest a record stores, and the YAML files
   whose parse result feeds a digest or a decision. Each row names a vector
   file or states why the scheme has none, such as a random identifier.
6. **Current behavior.** A vector records what the Python code does now,
   including a rejection that a strict Go decoder would also give and a
   leniency that it would not. A conflict with the strict decoding of ADR-065
   is a row in the inventory with its disposition. The Parquet vector records
   the current failure; when `go-cutover` takes #1599, the vector changes with
   it.
7. **RAES data.** A scheme that hashes a RAES model gets its input through the
   public RAES models and corpus, not a local copy.
8. **Secrets.** A vector holds a synthetic secret only when its scheme needs
   one, such as redaction before a digest.
9. **Owner coverage.** Owner vectors pin the identities and digests that
   records store or compare: evidence records, provenance, source sets, trial
   plans, captures, correlation, bundles, seats, credentials, workspaces, and
   the participant digests. The inventory lists each other owner that uses
   the base serializers, by file and function. The Go port that ports an owner
   adds its owner vectors to the corpus.

## Verification

- The Python tests pass on every vector in CI.
- Each inventory row names its vector file, and the test fails when a vector
  file has no row or a row names a missing file.

## References

- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)
- [YAML 1.1 types](https://yaml.org/type/)
- [Conformance inventory](../reference/conformance-inventory.md)
