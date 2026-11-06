# Validate a running scenario

Use this How-to guide only in CI or an approved isolated lab VM.
See the [live gate reference](techvault-live-validation-gate.md) for report semantics and limits.

## Prerequisites

Use an isolated, project-scoped Docker daemon with enough resources for the admitted scenario.
The default validation removes managed volumes and destroys their data.
Keep other workloads outside this daemon.

Install the locked dependencies with the RAES wheel and command.
Prepare the project's private runtime credentials through the supported startup configuration.
Do not copy secrets into evidence or command arguments.

## Running the gate

Run focused logic checks in the approved runner:

```shell
bash tools/run-targeted-tests.sh tests/test_techvault_live_gate.py
```

Run the destructive public gate:

```shell
lilrae lab validate-live
```

Before you confirm volume removal, examine the warning.
Use `--yes` only when automation explicitly authorizes the cleanup.
Use `--skip-clean-boot` to examine an existing deployment without the initial volume removal and reboot.

Use `--scenario` for a project-contained development SDL path.
Keep `--profile full-remote-control-plane` for the public startup route.
Use `--run-id` to select the archive identity.
Examine blocked and failed checks separately.

The targeted integration test has one more guard:

```shell
APTL_LIVE_GATE=1 bash tools/run-targeted-tests.sh tests/test_techvault_live_gate.py -m integration -q
```

Without `APTL_LIVE_GATE=1`, pytest skips that destructive test.
A gate pass does not establish a zero-event baseline or detection coverage for a new attack.
