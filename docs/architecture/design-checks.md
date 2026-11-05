# Design checks for /implement

The `/implement` and `/quickfix` workflows run structural design checks before a
change ships. This page records the design-check configuration for this
repository. The configuration lives in `.ground-control.yaml`. It sets
`schema_version: 2`, the four `workflow.design` commands, and the
`architecture.modules` ownership map.

## The four design commands

The design review runs four commands from the repository root. Each command runs
in a credential-free environment with no network access. Each command leaves the
Git HEAD, the index, and the working tree unchanged. Each command uses the same
`uv` environment as `tools/run-targeted-tests.sh`, so the gate reuses the
installed development toolchain.

| Command | Purpose | Tool |
| --- | --- | --- |
| `compile_command` | Byte-compile the Python source, tests, and tools. | `python -m compileall` |
| `structural_command` | Check the ADR-064 layer rules, the participant boundary, and the rule fixtures. | `tools/check_architecture.py`, `tools/check_lilrae_participant_architecture.py`, and the architecture fixture tests |
| `wiring_command` | Print the component dependency view from the import graph. | `tools/design_wiring.py` |
| `acceptance_command` | Run one named test case and report its result as JSON. | `tools/design_acceptance.py` |

This repository has no separate type checker. Byte-compilation is the native
compile check.

## Module ownership

The `architecture.modules` map gives each repository path its implementation
files and its governing ADRs. The design review reads this map to find the owner
and the decisions for a changed path. All matching parent entries apply. The `.`
entry carries the repository-wide decisions.

The map covers these paths:

| Path | Scope |
| --- | --- |
| `.` | Repository-wide decisions (ADR-000, ADR-007, ADR-064). |
| `src/aptl` | Python control plane. |
| `src/aptl/backends` | RAES deployment adapters. |
| `src/aptl_techvault` | Scenario adapter plugin. |
| `mcp` | TypeScript MCP control plane. |
| `tests` | Test suite. |
| `tools` | Quality and architecture tooling. |

Add a path to the map when a change to that path needs its own governing
context. Use existing implementation files and existing ADR files. Do not add an
unrelated file to pass the check.

## The acceptance adapter

`tools/design_acceptance.py` runs one acceptance case for the design review. It
reads one JSON object on standard input:

```json
{"test_file": "tests/test_feature.py", "test_name": "test_rejects_empty_name"}
```

It writes one JSON object on standard output:

```json
{"test_name": "test_rejects_empty_name", "status": "failed", "matches": 1, "message": "AssertionError: expected two, received one"}
```

The `status` field is one of `failed`, `passed`, `missing`, `skipped`, or
`broken`. The `matches` field is the count of collected cases with that exact
name. A valid red case has the `failed` status, one match, and the real
assertion message.

The adapter exits zero when it reports a valid observation. A failing test is a
valid observation. The adapter exits nonzero only when it cannot run or report.
Test-runner output goes to standard error. Standard output holds only the one
JSON object.

## Run the checks

Run each command from the repository root. Install the development dependencies
first. For example, run the acceptance adapter like this:

```shell
echo '{"test_file": "tests/test_version.py", "test_name": "test_example"}' \
  | uv run --frozen --group build --no-default-groups --extra dev --extra web \
    python tools/design_acceptance.py
```

The workflow calls the `gc_get_design_context` and `gc_codex_design_review` tools
to run the full design review. See `.ground-control.yaml` for the exact commands.
