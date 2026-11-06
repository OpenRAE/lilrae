# Validate a scenario

Use this How-to guide in CI or an approved isolated test VM.
The [static gate reference](techvault-static-validation-gate.md) states the checks and failure conditions.

## Running the gate

Install the locked development dependencies and LilRAE in the approved runner.
The installed RAES wheel gives its contract corpus and `raes` command.
No separate corpus checkout is required.

Run the focused gate-logic checks:

```shell
bash tools/run-targeted-tests.sh tests/test_techvault_static_gate.py
```

In CI or the approved VM, run the full selected scenario's integration gate:

```shell
bash tools/run-targeted-tests.sh tests/test_techvault_static_gate.py -m integration -q
```

Examine every failed stage in the `GateReport`.
Resolve imported-module changes through the upstream RAES lock workflow.
Do not accept a missing conformance command as a warning.
After a static pass, use [live validation](live-validation.md) for runtime evidence.
