# Install and configure managed OpenCode

Use this How-to guide only in CI or an approved isolated lab VM.
See the [reference](opencode-participants.md) for interface facts and limits.

## Install

Install LilRAE with Python 3.14. Use the [package installation instructions](../getting-started/installation.md).
Before you start a trial, install OpenCode:

```shell
bash tools/install-opencode.sh "$HOME/.local/lib/lilrae-opencode-1.19.5"
"$HOME/.local/lib/lilrae-opencode-1.19.5/opencode" --version
```

For a wheel-only installation, use the official [1.19.5 archive](https://github.com/anomalyco/opencode/releases/tag/v1.19.5).
Read the [build identities](opencode-participants.md#supported-build-and-route) and [verification contract](opencode-participants.md#installation-verification).
Before extraction, calculate the archive SHA-256 digest.
Compare it with the [reference digest](opencode-participants.md#supported-build-and-route).

Install the executable in an operator-owned directory.
Calculate the executable SHA-256 digest.
Compare it with the reference digest.
Pass its absolute path to `OpenCodeOptions.executable`.

## Configure and invoke

Set the approved model and credential-variable reference in the project:

```json
{
  "experiment": {
    "participant_models": {"opencode": "openrouter/approved-vendor/approved-model"},
    "participant_credential_sources": {
      "opencode": {"kind": "process-environment", "variable": "APPROVED_MODEL_CREDENTIAL"}
    }
  }
}
```

Replace the example model with an approved selection.
Pass the selected credential through the approved environment source.
Never put it in a command argument, prompt, or project JSON file.

Read the [factory contract](opencode-participants.md#factory-contract).
Set the absolute executable and an operator-owned work root outside the checkout.
Pass the configured model, credential source, and explicit source-environment mapping.

Do these steps separately for each participant address:

1. Create `opencode_manifest(version=...)` from `aptl.backends.lilrae_participant_configuration`.
1. Realize the seven manifest targets through RAES `realize_participant_configuration()`.
1. Resolve the prompt through the experiment's admitted artifact owner.
1. Create `OpenCodeParticipantRequest` from `aptl.workbench.opencode_bootstrap` with the admitted configuration, manifest, prompt, reference, and model domain.
1. Pass it to `managed_opencode_executor()` from the same module.
1. Bind the executor and its configuration digest through `LilraeParticipantBinding`.
1. Admit the bindings through `ScenarioAdmissionSource.autonomous_bindings`.
1. Execute with `run_participant_workload()` and the existing experiment evaluator.
1. Cancel and drain the runtime before you leave the managed executor context.

See the [OpenCode reference](opencode-participants.md#configuration-targets) for these contracts.
