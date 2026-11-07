# Design-check tools

This repository keeps four manual design checks. Run them before you change the
architecture. `.ground-control.yaml` does not configure these checks.

## The four design checks

Run each check from the repository root. Each check needs no credentials and no
network access. Each check leaves the Git HEAD, the index, and the working tree
unchanged. Use the same `uv` environment as `tools/run-targeted-tests.sh`.

| Check | Purpose | Tool |
| --- | --- | --- |
| Compile | Byte-compile the Python source, tests, and tools. | `python -m compileall -q src tests tools` |
| Structure | Check the ADR-064 layer rules, the participant boundary, and the rule fixtures. | `tools/check_architecture.py`, `tools/check_lilrae_participant_architecture.py`, and the architecture fixture tests |
| Wiring | Print the component dependency view from the import graph. | `tools/design_wiring.py` |
| Acceptance | Run one named test case and report its result as JSON. | `tools/design_acceptance.py` |

This repository has no separate type checker. Byte-compilation is the native
compile check.

## The acceptance adapter

`tools/design_acceptance.py` runs one acceptance case. It
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
