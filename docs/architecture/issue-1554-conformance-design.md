---
design: 1
issue: 1554
packages:
  - path: conformance
    component: conformance-suite
    test_imports:
      - github.com/rogpeppe/go-internal
      - github.com/santhosh-tekuri/jsonschema/v6
model_changes:
  - component:conformance-suite
---

# Issue #1554: Conformance Design

This design adds the black-box conformance suite of
[ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md). It
refines the [preflight](issue-1554-conformance-preflight.md). The suite runs an
installed `lilrae` binary and checks the contracts of the CLI, the
configuration, and the persisted files. The front matter of this note is its
design record.

## Evidence

| Fact | Source |
| --- | --- |
| The CLI has 55 commands and groups, with their options, in the installed Python release. | Typer command tree of `aptl.cli.main:app`. |
| `doctor`, `lab start`, `lab stop`, and `lab reset` share the exit status contract and one JSON envelope: `command`, `schema_version` 1, and `ok`, which is true exactly when the exit status is 0. | `docs/reference/cli.md`; `src/aptl/cli/_common.py`. |
| `lab status --json` prints the redacted range snapshot without an envelope. | `docs/reference/cli.md`; `RangeSnapshot.to_dict`. |
| `aptl.json`, the execution boundary, and the bundle manifest have Pydantic models. The configuration models reject unknown fields. | `core/config.py`, `core/execution_boundary.py`, `core/evidence_bundle/envelope.py`. |
| RAES publishes the schemas of `experiment-run-v1` and `experiment-evidence-record-v1`. | `raes_contracts` package data. |
| `lab init` and `config validate` and `config show` run without a lab. | Probe with the installed release. |
| ADR-065 selects `testscript` for the CLI contract suite and `github.com/santhosh-tekuri/jsonschema/v6` for JSON Schema. Tests that need a Docker daemon carry the `integration` build tag, and the linters read it. | ADR-065; `.golangci.yml`. |
| The `clean-install-lab-boot` job installs the wheel in a clean environment and starts a product-neutral scenario on a dedicated daemon. | `.github/workflows/checks.yml`. |

## Decisions

1. **Boundary.** `conformance/` in the root module holds the suite. It has
   test files only, and it imports no product package. It observes the
   binary through its arguments, environment, exit status, output streams,
   and files.
2. **Binary seam.** `LILRAE_CONFORMANCE_BINARY` names the binary by an absolute
   path. The suite fails when the variable is not set, is not absolute, or
   does not name an executable file. Nothing skips a case.
3. **Harness.** `TestConformance` runs each script in `testdata/cases` with
   `testscript`. Each script has its own work directory, with `HOME`,
   `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`, and `DOCKER_CONFIG`
   below it, and `NO_COLOR` set. The suite adds these commands to the script
   language:

   | Command | Meaning |
   | --- | --- |
   | `lilrae ARG...` | Run the binary. `! lilrae` expects a nonzero exit status. |
   | `status N` | The last `lilrae` command exited with status `N`. |
   | `envelope COMMAND` | The standard output of the last `lilrae` command is one JSON object with this `command`, `schema_version` 1, and an `ok` that is true exactly when the exit status is 0. |
   | `schema NAME FILE` | The JSON file conforms to the published schema `NAME`. |
   | `doctor-counts FILE` | The `counts` of a doctor result equal the number of checks with each status. |

   A failure message names the case, the command, and the rule. It prints no
   input file and no schema instance.
4. **Lab cases.** `TestLab` runs each script in `testdata/lab`. Its file has
   the `integration` build tag, so only a job with a Docker daemon builds it.
   The `clean-install-lab-boot` job runs it with the installed wheel, a fresh
   project, and the product-neutral scenario that
   `LILRAE_CONFORMANCE_SCENARIO` names. The job keeps its own realization and
   teardown checks.
5. **Schemas.** `docs/reference/schemas/` holds the published JSON Schemas
   (draft 2020-12). The documentation site serves the same files that the
   suite reads, so no copy can drift. Each schema has an `$id` below
   `https://openrae.github.io/lilrae/reference/schemas/`. The suite loads each
   schema of the directory into a closed registry and resolves no reference
   from the network or from another file. The Schemas section lists them.
6. **Schema rules.** An action result permits additional fields, because a new
   field keeps its schema version. The configuration rejects unknown fields at
   each level, as its models do. A field that can be `null` and a field that
   can be absent are different rules. Pydantic models give the first draft of
   a schema; the published schema is reviewed, and the suite never makes a
   schema from the implementation that it tests.
7. **RAES records.** RAES owns `experiment-run-v1` and
   `experiment-evidence-record-v1`. The inventory names their published RAES
   schemas. This issue does not copy them.
8. **Inventory.** `docs/reference/conformance-inventory.md` lists each command,
   option, exit status, output stream, JSON result, and persisted file. Each
   row gives its source, its class (contract or detail), and its coverage: a
   case, a lab case, or the later port that owns its protocol. `TestInventory`
   fails when a row names a case that does not exist, or when no row names a
   case.
9. **Text rule.** Human-readable text keeps its facts. Only the strings that a
   document or a test locks, such as `Aborted.`, stay byte-identical. Help
   layout, tables, colors, file counts, timestamps, and generated paths are not
   contracts. A case checks options by name, not by help layout.
10. **Parser differences.** A case uses only input that a strict decoder and the
    Python decoder both accept, unless the case checks a documented rejection,
    such as an unknown configuration field.
11. **CI.** The `go-tests` job builds the wheel, installs it into a clean
    environment, and sets `LILRAE_CONFORMANCE_BINARY`, so `go-gates.sh test`
    runs the suite on the Python release. The selector sends
    `conformance/`, `docs/reference/schemas/`, and the inventory to the `go`
    lane and to the `lab` lane, because the lab job runs the lab cases.

## Schemas

| Schema | Instance |
| --- | --- |
| `cli-result.schema.json` | The envelope of the action results. |
| `doctor-result.schema.json` | `lilrae doctor --json`. |
| `lab-start-result.schema.json` | `lilrae lab start --json`. |
| `lab-stop-result.schema.json` | `lilrae lab stop --json`. |
| `lab-reset-result.schema.json` | `lilrae lab reset --json`. |
| `execution-boundary.schema.json` | `aptl.execution-boundary/v1`, also inside a start result. |
| `range-snapshot.schema.json` | `lilrae lab status --json` and `--output`, and the snapshot of a run. |
| `aptl-config.schema.json` | `aptl.json`. |
| `run-record.schema.json` | `aptl.run-record/v2`. |
| `evidence-bundle.schema.json` | `bundle.json`, `aptl-evidence-bundle/v1`. |

## Architecture

```mermaid
flowchart LR
    B[LILRAE_CONFORMANCE_BINARY] --> H[testscript harness]
    C[testdata/cases] --> H
    L[testdata/lab, integration tag] --> H
    S[docs/reference/schemas] --> H
    H --> R[exit status, streams, files]
    I[conformance-inventory.md] --> T[TestInventory]
    C --> T
    L --> T
```

| Component | Package | Responsibility |
| --- | --- | --- |
| conformance-suite | `conformance` | Runs the contract cases against an installed binary. |

## Failure behavior

| Condition | Result |
| --- | --- |
| The binary variable is missing or names no executable file. | The test fails. |
| A case finds a different exit status, stream, field, or file. | The case fails with the rule. |
| A schema is invalid or has an unresolved reference. | The test fails. |
| An inventory row names a missing case, or a case has no row. | `TestInventory` fails. |
| The lab job has no daemon or no scenario. | `TestLab` fails. |

## Data flows and security

```text
Case script + fixtures [repository]
  -> lilrae binary [installed artifact, isolated HOME and XDG]
  -> exit status, stdout, stderr, files in the work directory
  -> schema and rule checks <- docs/reference/schemas [repository]
  -> test result [CI log]
```

- The binary runs with argument arrays and no shell.
- Each case has its own work directory and home. No operator project, run
  store, credential, or Docker configuration reaches a case.
- Synthetic secrets appear only in the redaction cases.

## Verification

- Each case passes on the installed Python release in CI.
- `TestInventory` proves that each inventory row names an existing case.
- The lab cases pass in the `clean-install-lab-boot` job.

## References

- [testscript](https://pkg.go.dev/github.com/rogpeppe/go-internal/testscript)
- [santhosh-tekuri/jsonschema v6](https://pkg.go.dev/github.com/santhosh-tekuri/jsonschema/v6)
- [JSON Schema draft 2020-12](https://json-schema.org/draft/2020-12)
- [CLI reference](../reference/cli.md)
