# Conformance Inventory

This inventory lists the external contracts of the `lilrae` command: each
command, option, exit status, output stream, JSON result, and persisted file
that users or other systems use. The
[conformance design](../architecture/issue-1554-conformance-design.md) gives
the harness. Each row has one of these classes:

- `contract`: the Python release and the Go build must both keep it. The
  Coverage column names the case in `conformance/testdata` that checks it, or
  the later Go port that owns its protocol.
- `detail`: an implementation detail. No case checks it.

The suite runs the binary that `LILRAE_CONFORMANCE_BINARY` names by an absolute
path:

```shell
LILRAE_CONFORMANCE_BINARY="$PWD/.venv/bin/lilrae" go test -C conformance ./...
```

The cases in `lab/` need a Docker daemon that only the lab uses. CI runs them
in the clean-install lab job. `go test -C conformance -tags integration -run
TestLab ./...` runs them with `LILRAE_CONFORMANCE_SCENARIO` set to the
absolute path of the scenario file.

## Text rule

Human-readable text keeps its facts. Only the strings that a document or a test
locks stay byte-identical; the Text facts table lists them. Help layout, tables,
colors, file counts, timestamps, and generated paths are not contracts. A case
checks options by name, not by help layout or by the format of a default.

## Commands and options

| ID | Item | Source | Class | Coverage |
| --- | --- | --- | --- | --- |
| cli.root | `lilrae`: `--version/-V` | CLI reference; installed help | contract | `cases/options-root.txtar` |
| cli.root.details | `lilrae`: `--install-completion`, `--show-completion` | Installed help | detail | Hidden or completion options are not supported interfaces. |
| cli.doctor | `lilrae doctor`: `--project-dir/-d`, `--json/-j` | CLI reference; installed help | contract | `cases/options-doctor.txtar`, `cases/doctor.txtar`, `cases/redaction.txtar`, `cases/usage-errors.txtar` |
| cli.lab.continuity-audit | `lilrae lab continuity-audit`: `--project-dir/-d`, `--target/-t`, `--whitelist`, `--json`, `--run-id` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 24 |
| cli.lab.init | `lilrae lab init`: `DIRECTORY`, `--force/-f` | CLI reference; installed help | contract | `cases/options-lab.txtar`, `cases/lab-init.txtar` |
| cli.lab.enforce | `lilrae lab enforce`: `--project-dir/-d`, `--grace-minutes` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 23 |
| cli.lab.monitor | `lilrae lab monitor`: `--project-dir/-d`, `--interval`, `--max-ticks`, `--grace-minutes` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 23 |
| cli.lab.qualify-profile | `lilrae lab qualify-profile`: `--project-dir/-d`, `--profile`, `--report`, `--public-key`, `--run-id` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 24 |
| cli.lab.start | `lilrae lab start`: `--project-dir/-d`, `--skip-seed`, `--scenario`, `--scenario-path`, `--clean/-c`, `--yes/-y`, `--teardown-on-failure`, `--offline-staged`, `--appliance-launch-descriptor`, `--appliance-release-public-key`, `--appliance-qualification-public-key`, `--json/-j` | CLI reference; installed help | contract | `cases/options-lab.txtar`, `cases/lab-json-failures.txtar`, `cases/usage-errors.txtar`, `cases/declined-confirmations.txtar`, `lab/lifecycle.txtar` |
| cli.lab.start.details | `lilrae lab start`: `--appliance-readiness-challenge`, `--appliance-readiness-device`, `--appliance-access-request`, `--appliance-access-device`, `--appliance-access-output-dir`, `--appliance-candidate-trust` | Installed help | detail | Hidden or completion options are not supported interfaces. |
| cli.lab.info | `lilrae lab info`: `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 23 |
| cli.lab.scenarios | `lilrae lab scenarios`: `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 17 |
| cli.lab.stop | `lilrae lab stop`: `--volumes/-v`, `--yes/-y`, `--project-dir/-d`, `--json/-j` | CLI reference; installed help | contract | `cases/options-lab.txtar`, `cases/lab-json-failures.txtar`, `cases/usage-errors.txtar`, `cases/declined-confirmations.txtar`, `lab/lifecycle.txtar` |
| cli.lab.reset | `lilrae lab reset`: `--yes/-y`, `--project-dir/-d`, `--json/-j` | CLI reference; installed help | contract | `cases/options-lab.txtar`, `cases/lab-json-failures.txtar`, `cases/usage-errors.txtar`, `cases/declined-confirmations.txtar`, `lab/lifecycle.txtar` |
| cli.lab.status | `lilrae lab status`: `--project-dir/-d`, `--json/-j`, `--output/-o` | CLI reference; installed help | contract | `cases/options-lab.txtar`, `cases/lab-json-failures.txtar`, `lab/lifecycle.txtar` |
| cli.lab.validate-live | `lilrae lab validate-live`: `--project-dir/-d`, `--scenario`, `--profile`, `--run-id`, `--skip-clean-boot`, `--yes/-y` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 24 |
| cli.lab.policy.show | `lilrae lab policy show`: `--project-dir/-d`, `--json` | CLI reference; installed help | contract | `cases/options-lab.txtar`; behavior: Go port 23 |
| cli.config.show | `lilrae config show`: `--project-dir/-d`, `--json` | CLI reference; installed help | contract | `cases/options-config.txtar`, `cases/config.txtar` |
| cli.config.validate | `lilrae config validate`: `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-config.txtar`, `cases/config.txtar`, `cases/redaction.txtar` |
| cli.config.migrate | `lilrae config migrate`: `--project-dir/-d`, `--scenario` | CLI reference; installed help | contract | `cases/options-config.txtar`; behavior: Go port 08 |
| cli.container.list | `lilrae container list`: `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-container.txtar`, `lab/lifecycle.txtar` |
| cli.container.logs | `lilrae container logs`: `NAME`, `--follow/-f`, `--tail`, `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-container.txtar`; behavior: Go port 12 |
| cli.container.shell | `lilrae container shell`: `NAME`, `--shell`, `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-container.txtar`; behavior: Go port 12 |
| cli.runs.list | `lilrae runs list`: `--project-dir/-d`, `--limit/-n` | CLI reference; installed help | contract | `cases/options-runs.txtar`, `cases/runs.txtar`, `lab/lifecycle.txtar` |
| cli.runs.show | `lilrae runs show`: `RUN_ID`, `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-runs.txtar`, `cases/runs.txtar` |
| cli.runs.path | `lilrae runs path`: `RUN_ID`, `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-runs.txtar`, `cases/runs.txtar` |
| cli.runs.export | `lilrae runs export`: `RUN_ID`, `--project-dir/-d`, `--output-dir/-o`, `--s3-bucket`, `--s3-prefix` | CLI reference; installed help | contract | `cases/options-runs.txtar`, `cases/runs.txtar`; behavior: Go port 11 (S3 upload) |
| cli.runs.export-bundle | `lilrae runs export-bundle`: `RUN_ID`, `--project-dir/-d`, `--output-dir/-o`, `--projection/-p`, `--verify/--no-verify` | CLI reference; installed help | contract | `cases/options-runs.txtar`, `cases/runs-bundle.txtar` |
| cli.runs.verify-bundle | `lilrae runs verify-bundle`: `BUNDLE_PATH` | CLI reference; installed help | contract | `cases/options-runs.txtar`, `cases/runs-bundle.txtar` |
| cli.web.serve | `lilrae web serve`: `--host`, `--port`, `--reload/--no-reload`, `--project-dir`, `--web-root`, `--api-only`, `--public-origin` | CLI reference; installed help | contract | `cases/options-web.txtar`; behavior: Go port 28 |
| cli.kill | `lilrae kill`: `--containers/-c`, `--project-dir/-d` | CLI reference; installed help | contract | `cases/options-kill.txtar`; behavior: Go port 12 |
| cli.experiment.admit | `lilrae experiment admit`: `SPEC_PATH`, `--manifest`, `--base-dir/-d`, `--allow-uncertified-apparatus` | CLI reference; installed help | contract | `cases/options-experiment.txtar`; behavior: Go port 17 |
| cli.seat.stage | `lilrae seat stage`: `--seat-root`, `--seat-id`, `--image`, `--public-key`, `--image-cache`, `--yes/-y`, `--mapping`, `--desktop-mode` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.start | `lilrae seat start`: `--seat-root`, `--seat-id`, `--image`, `--public-key`, `--image-cache`, `--yes/-y`, `--mapping`, `--access-owner`, `--access-public-key`, `--access-identity-file`, `--access-project-dir`, `--access-profile`, `--access-client`, `--access-hours`, `--no-check`, `--desktop-mode`, `--sudo-password-file` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.stop | `lilrae seat stop`: `--seat-root` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.rescue | `lilrae seat rescue`: `--seat-root` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.reset | `lilrae seat reset`: `--seat-root`, `--seat-id`, `--image`, `--public-key`, `--image-cache`, `--yes/-y`, `--desktop-mode` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.recover | `lilrae seat recover`: `--seat-root`, `--seat-id`, `--image`, `--public-key`, `--image-cache`, `--yes/-y`, `--desktop-mode`, `--sudo-password-file` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.reconcile | `lilrae seat reconcile`: `--seat-root` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.status | `lilrae seat status`: `--seat-root` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.open-kiosk | `lilrae seat open-kiosk`: `--participant-port`, `--seat-root`, `--browser-command`, `--dry-run` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.update | `lilrae seat update`: `--seat-root`, `--image`, `--public-key`, `--image-cache`, `--yes/-y`, `--to`, `--desktop-mode` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.seat.images | `lilrae seat images`: `--image-cache`, `--yes/-y`, `--prune` | CLI reference; installed help | contract | `cases/options-seat.txtar`; behavior: Go port 27 |
| cli.mcp-access.configure | `lilrae mcp-access configure`: `--access-record`, `--grant`, `--host-public-key`, `--expected-host-key`, `--identity-file`, `--username`, `--owner-id`, `--seat-id`, `--instance-id`, `--project-dir`, `--client` | CLI reference; installed help | contract | `cases/options-mcp-access.txtar`; behavior: Go port 25 |
| cli.mcp-access.dispatch | `lilrae mcp-access dispatch`: `--binding`, `--grant-id`, `--key-fingerprint` | Hidden command | detail | Not a supported interface (CLI reference). |
| cli.mcp-access.prepare-guest | `lilrae mcp-access prepare-guest`: `--request`, `--output-dir` | CLI reference; installed help | contract | `cases/options-mcp-access.txtar`; behavior: Go port 25 |
| cli.mcp-access.refresh | `lilrae mcp-access refresh`: `--binding`, `--output` | CLI reference; installed help | contract | `cases/options-mcp-access.txtar`; behavior: Go port 25 |
| cli.mcp-access.revoke | `lilrae mcp-access revoke`: `--binding`, `--grant-id` | CLI reference; installed help | contract | `cases/options-mcp-access.txtar`; behavior: Go port 25 |

## Exit statuses and streams

| ID | Item | Source | Class | Coverage |
| --- | --- | --- | --- | --- |
| exit.done | Exit status 0: `doctor`, `lab start`, `lab status`, `lab stop`, and `lab reset` did what they report. A degraded start also exits with status 0. | CLI reference | contract | `lab/lifecycle.txtar` |
| exit.failed | Exit status 1: the command could not do it. | CLI reference | contract | `cases/lab-json-failures.txtar`, `cases/doctor.txtar` |
| exit.usage | Exit status 2: invalid usage, such as an unknown option, conflicting scenario selectors, or `--json` with a destructive option but without `--yes`. | CLI reference | contract | `cases/usage-errors.txtar` |
| exit.declined | A declined confirmation prints `Aborted.`, changes nothing, and exits with status 0. | CLI reference | contract | `cases/declined-confirmations.txtar` |
| stream.json | With `--json`, one JSON object on standard output, and start progress on standard error. | CLI reference | contract | `cases/lab-json-failures.txtar`, `lab/lifecycle.txtar` |
| stream.usage | A usage error prints no JSON object and goes to standard error. | CLI reference | contract | `cases/usage-errors.txtar` |
| stream.redaction | Free-form text in a JSON result is redacted. Without a lab, no input reaches a free-form field, so the case checks that no input credential reaches an output stream. | CLI reference; ADR-029 | contract | `cases/redaction.txtar` |

## JSON results

The schemas are in [the schema directory](schemas/cli-result.schema.json) and
on the documentation site at `reference/schemas/`.

| ID | Item | Source | Class | Coverage |
| --- | --- | --- | --- | --- |
| json.envelope | `command`, `schema_version` 1, and `ok`, which is true exactly when the exit status is 0. A new field keeps the version. Schema: `cli-result.schema.json`. | CLI reference | contract | `cases/doctor.txtar`, `cases/lab-json-failures.txtar`, `lab/lifecycle.txtar` |
| json.doctor | `lilrae doctor --json`; its counts match its checks. Schema: `doctor-result.schema.json`. | CLI reference | contract | `cases/doctor.txtar` |
| json.lab-start | `lilrae lab start --json`. Schema: `lab-start-result.schema.json`. | CLI reference | contract | `cases/lab-json-failures.txtar`, `lab/lifecycle.txtar` |
| json.lab-stop | `lilrae lab stop --json`. Schema: `lab-stop-result.schema.json`. | CLI reference | contract | `cases/lab-json-failures.txtar`, `lab/lifecycle.txtar` |
| json.lab-reset | `lilrae lab reset --json`. Schema: `lab-reset-result.schema.json`. | CLI reference | contract | `cases/lab-json-failures.txtar`, `lab/lifecycle.txtar` |
| json.execution-boundary | `aptl.execution-boundary/v1` in a start result. Schema: `execution-boundary.schema.json`. | CLI reference | contract | `cases/lab-json-failures.txtar` |
| json.status | `lilrae lab status --json` and `--output`: the redacted range snapshot, with no envelope. Schema: `range-snapshot.schema.json`. | CLI reference | contract | `lab/lifecycle.txtar` |
| json.config-show | `lilrae config show --json`: the resolved configuration with its defaults, with no envelope. Schema: `aptl-config.schema.json`. | Configuration models | contract | `cases/config.txtar` |

## Persisted files

| ID | Item | Source | Class | Coverage |
| --- | --- | --- | --- | --- |
| file.aptl-json | `aptl.json`: each object rejects an unknown field. Schema: `aptl-config.schema.json`. | Configuration models | contract | `cases/config.txtar`, `cases/lab-init.txtar` |
| file.lab-assets | The lab assets and the default `aptl.json` that `lilrae lab init` writes; it refuses to overwrite them without `--force`. | DEP-008; installed assets | contract | `cases/lab-init.txtar` |
| file.run-store | The run store `<run_storage.local_path>/<run_id>/manifest.json`, with `./runs` by default. | Run store | contract | `cases/runs.txtar`, `lab/lifecycle.txtar` |
| file.run-record | `aptl.run-record/v2`, the `manifest.json` of a lab start. Schema: `run-record.schema.json`. | Run record writer | contract | `lab/lifecycle.txtar` |
| file.legacy-manifest | A flat run manifest of an earlier release stays readable. | Run store readers | contract | `cases/runs.txtar` |
| file.raes-records | RAES `experiment-run-v1` and `experiment-evidence-record-v1` records. RAES publishes their schemas, and an evidence bundle carries the exact published schema bytes. | RAES contracts | contract | `cases/runs-bundle.txtar` exports and verifies a run with an RAES evidence record. |
| file.bundle | `bundle.json`, `aptl-evidence-bundle/v1`, in an evidence bundle. Schema: `evidence-bundle.schema.json`. | Evidence bundle reference | contract | `cases/runs-bundle.txtar` |
| file.workspace-ownership | `.aptl/lifecycle/workspace-ownership-v1.json`: `{"schema": 1, "workspace_id": ...}`, with 32 lower-case hexadecimal digits, written once. `WorkspaceOwnership.load` reads it. The workspace identifier sets the Compose project name and the container names, so a later stop or reset finds the resources of an earlier start. | Compose resource ownership | contract | Go port 09 |
| file.resource-receipts | `.aptl/lifecycle/resource-receipts-v1/<kind>/<SHA-256 of the native ID>.json`: one receipt, written once, for each container, network, and volume that a start creates. Cleanup, network operations, and native evidence read them. | Compose resource ownership | contract | Go port 09 |
| file.cleanup-actions | `.aptl/lifecycle/cleanup-actions-v1/` (`aptl-lifecycle-cleanup-action/v1` and `/v2`) and `cleanup-actions-completed-v1/` (`aptl-lifecycle-cleanup-completion/v1`), and the `startup-reset-v1/` and `startup-reset-completed-v1/` receipts of earlier releases, which stay readable. The next `lab stop -v` finishes each pending cleanup and writes its completion marker. | Startup reset state | contract | Go port 23 |
| file.project-state | `.aptl/`: the session, the lifecycle policy, the operator groups, and the capture state. Each has its own owner and reader. Locks, caches, staged packs, rendered Compose files, and generated secrets are details. | Preflight | detail | No portable format. |

## Text facts

| ID | Item | Source | Class | Coverage |
| --- | --- | --- | --- | --- |
| text.aborted | `Aborted.` | CLI reference | contract | `cases/declined-confirmations.txtar` |
| text.version | `lilrae --version` prints `lilrae` and the version. | CLI reference; lab job | contract | `cases/options-root.txtar` |
| text.init | `Initialized lab project in` and the directory. | `lab init` | contract | `cases/lab-init.txtar` |
| text.no-runs | `No experiment runs found.` | `runs list` | contract | `cases/runs.txtar` |
| text.bundle | `seal: UNSEALED` with the `seal-absent` limitation, and `OK: bundle verified`. | Evidence bundle reference | contract | `cases/runs-bundle.txtar` |
