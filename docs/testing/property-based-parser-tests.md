# Add parser property tests

Use this guide for parsers that accept operator-authored or untrusted strings.
Examples include credential rendering, environment parsing, strict configuration, redaction, and scenario-path resolution.
The former local SDL parser suite was removed after the ADR-035 RAES cutover.

## Scope

1. Identify the parsing or rendering boundary.
2. Find its canonical owner in the [parser boundary reference](../reference/parser-boundaries.md).
3. Keep known security-regression tests. Use property tests to explore additional inputs.
4. Run tests only in CI or an approved isolated VM.

## Guardrails

- Mark each property test with `pytest.mark.fuzz`.
- Select the exact path and `-m fuzz`, as described in [Verify a change](index.md#run-targeted-tests-in-an-approved-environment).
- Set Hypothesis deadlines for parser or performance regressions.
- Require either a valid result or the boundary's existing public error type.
- Reject unhandled `TypeError`, `KeyError`, or `AttributeError`, excessive CPU use, partial writes, and stale output.
- Use synthetic inputs. Do not read real `.env` files or expose generated secrets.
- Do not call Docker, start services, or cross process or network boundaries from these parser tests.
- Reuse canonical path helpers and source/rendered locations.
- Do not add caller-controlled output paths just for tests.
- For secret-shaped inputs, assert structure and redaction results instead of recording raw values.

## Boundary Ownership

Use the [canonical parser owners](../reference/parser-boundaries.md).
Exercise those owners directly. Do not add another schema, parser, or secret taxonomy in test helpers.
Keep RAES errors within its public types and redact diagnostics before CLI output.

## Non-Goals

Do not redesign parser APIs, error hierarchies, configuration ownership, or artifact locations through property tests.
Keep fuzz tests outside default selection unless the repository marker policy changes first.
