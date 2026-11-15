# Design-check tool reference

The existing tools describe source structure and observe one selected acceptance case.
They do not grant permission to run behavior tests on the workstation.
[Architecture checks](../architecture/design-checks.md) explains their limits.

## Tool contracts

| Check | Tool | Contract |
| --- | --- | --- |
| Compile | `python -m compileall -q src tests tools` | Creates Python bytecode. It is not a type check. |
| Structure | `tools/check_architecture.py` | Reads the ADR-064 layer map and enrolled modules; reports structural findings. |
| Participant structure | `tools/check_lilrae_participant_architecture.py` | Checks the existing participant dependency model. |
| Wiring | `tools/design_wiring.py` | Prints module counts and observed component imports as text and Mermaid. |
| Acceptance | `tools/design_acceptance.py` | Runs one exact named case and emits a JSON observation. |

The wiring view reads the import graph and layer map without changing repository files.
Compilation creates bytecode caches; it is not a claim that the whole working directory stays unchanged.
The layer check applies to enrollment, not every target rule across the whole tree.

## The acceptance adapter

`tools/design_acceptance.py` runs one named test case.
Behavior tests run only in CI or an approved isolated VM.
The adapter reads one JSON object on standard input:

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

The adapter exits zero for a valid observation, including an observed failing test.
It exits nonzero when it cannot run or report.
Test-runner output goes to standard error.
Standard output contains only the result object.
