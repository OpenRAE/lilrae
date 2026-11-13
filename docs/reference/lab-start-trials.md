# Lab Start Trials

`lilrae lab start` can run one trial that a concrete trial SDL declares. It
starts the lab, starts the declared participants, stops them at the deadline or
on a stop request, and seals the run. This page gives the exact contract.

## Trial options

| Option | Value |
| --- | --- |
| `--run-id` | The run ID. It also names the run directory in the configured run store. |
| `--attempt-id` | The attempt ID. The trial record keeps it. |
| `--deadline` | The UTC deadline, in RFC 3339 form that ends in `Z`, for example `2026-11-06T12:00:00Z`. |

Supply all three options or none. Without them, `lilrae lab start` does not run
a trial. A run ID or an attempt ID matches `^\w[\w.-]{0,127}$` and does not
contain `..`. The run directory must not exist yet.

A partial option set, an unsafe ID, an invalid deadline, or an existing run
directory stops the command with exit status 2. The lab does not change.

```shell
lilrae lab start --scenario techvault-purpleteam \
  --run-id run-0042 --attempt-id attempt-1 --deadline 2026-11-06T12:00:00Z
```

## Start and ownership

The trial starts only when the lab start outcome is `ready` or
`degraded_usable`. Any other outcome starts no participant.

While startup holds the lifecycle lock, it claims the trial fence for the
attempt. Other lifecycle commands refuse until the trial seals its run and
releases the fence. The trial reads the SDL again and refuses it if its
SHA-256 digest differs from the SDL that startup admitted.

## Trial SDL contract

A participant is an SDL agent that meets these conditions:

- Its `interactive_access` nodes carry exactly one software component with a
  `model`. The model is a literal value, not a variable.
- It has one concrete exercise role.
- It selects at least one control-context asset.

An agent with no model component is not a participant. An agent with more than
one model component stops the trial before any participant starts.

```yaml
nodes:
  kali:
    runtime:
      software_components:
        - component_id: participant-harness
          name: participant-harness
          model: google-vertex/zai-org/glm-5.2-maas
agents:
  red-team-operator:
    role: red
    interactive_access:
      kali-ssh: {target_ref: kali, channel: ssh}
    control_context:
      preamble: {declaration_ref: red-preamble, asset_ref: {...}, disposition: selected}
      task: {declaration_ref: red-task, asset_ref: {...}, disposition: selected}
```

The prompt is the bytes of the selected assets, in authored order. Agent
selections come first, then selections from behavior specifications. RAES
checks each asset pin and scope. LilRAE reads each asset from the scenario pack
by its artifact ID. It checks the size, the checksum, and UTF-8 encoding. One
asset has at most 128,000 bytes.

The role selects the tool profile: `red`, `blue`, or `guided-blue`. A role
without a profile stops the trial. The tools are the profile servers that the
run's `.mcp.json` selects. The run selects only servers whose SDL nodes exist,
so a scenario without the `misp` node gives no threat-intelligence tools.

## Tool control

OpenCode receives the verified tools of each selected server as allow rules.
Every other tool is denied. MCP servers record each call in the run. MCP child
processes receive no provider credential and no credential file path.

## Project settings

Set these values in the `experiment` section of `aptl.json`:

| Setting | Use |
| --- | --- |
| `opencode_executable` | The absolute path of the installed OpenCode 1.19.5 executable. |
| `participant_credential_sources.opencode` | The source of the OpenRouter API key, for `openrouter/` models. |
| `participant_credential_sources.vertex` | The source of a Google Cloud service account key, or the host's attached service account, for `google-vertex/` models. |
| `participant_serving_providers` | The approved OpenRouter serving provider for each `openrouter/` model. |

```json
{
  "experiment": {
    "opencode_executable": "/opt/lilrae/opencode-1.19.5/opencode",
    "participant_credential_sources": {
      "opencode": {"kind": "process-environment", "variable": "OPENROUTER_KEY"},
      "vertex": {"kind": "process-environment", "variable": "VERTEX_SERVICE_ACCOUNT_KEY"}
    },
    "participant_serving_providers": {"openrouter/z-ai/glm-5.3": "z-ai"}
  }
}
```

A source names a process environment variable. It never holds the secret
value. A model whose prefix has no configured source, or an `openrouter/` model
without an approved serving provider, stops the trial before any participant
starts.

## Vertex AI participants

The `vertex` source variable holds the service account key JSON. For each
Vertex AI participant, LilRAE writes the key to a private file in the trial
work directory. The OpenCode child receives these values:

| Variable | Value |
| --- | --- |
| `GOOGLE_APPLICATION_CREDENTIALS` | The path of the private key file |
| `GOOGLE_CLOUD_PROJECT` | The `project_id` of the key |
| `METADATA_SERVER_DETECTION` | `none` |

The location is `global`. LilRAE removes the key file before it seals the run.
The key does not go into the SDL, the prompt, the trial record, or the run files.

### Attached service account

On a Google Cloud VM, the `vertex` source can select the VM's attached service
account. The account needs only Vertex AI invocation permission.

```json
"vertex": {"kind": "attached-service-account", "project": "example-project"}
```

The OpenCode child receives only `GOOGLE_CLOUD_PROJECT`. It gets short-lived
tokens from the metadata server, so no key file exists. The trial record
contains `vertex_access: attached-service-account` in its `cleanup` section.
The run provenance records the source kind and descriptor digest.

The OpenCode child runs on the host. Block participant containers from the
metadata server before the trial starts; LilRAE does not change host firewall
rules.

## Deadline and stop

Each participant runs one invocation. The invocation stops at the earlier of
3,600 seconds and the deadline. The trial checks the deadline and the stop
request every second.

At the deadline or on a stop request, the trial cancels every participant. It
waits at most 60 seconds for each participant to stop. Then it records the
participants, removes credentials, finalizes required transcripts, and seals.

Two actions request a stop:

- `lilrae lab stop` records a stop request. It waits at most 300 seconds for the
  seal, then stops the lab.
- `SIGTERM` to the `lilrae lab start` process.

If the trial process no longer exists, `lilrae lab stop` releases the fence and
stops the lab. That run stays unsealed and keeps its partial evidence.

## Trial record

The seal closes the run for collection. The run directory holds
`trial/record.json` with schema `lilrae-trial-record/v1`. This record is a
LilRAE record, not an RAES experiment-run record.

| Field | Content |
| --- | --- |
| `run_id`, `attempt_id` | The caller IDs |
| `scenario_sha256` | The digest of the trial SDL bytes |
| `deadline`, `started_at`, `ended_at` | UTC times |
| `terminal_cause` | `completed`, `deadline`, `stopped`, or `failed` |
| `participants` | Each address, role, model, asset names, prompt digest, status, times, failure, output path, and invocation facts |
| `cleanup` | `provider_access: removed`, and `transcripts: not-required`, `sealed-ready`, or `failed` |

A participant status is `completed`, `cancelled`, `failed`, or `not-started`.
A trial without a deadline or stop ends `failed` when a participant failed.
Participant output is under `trial/participants/` after secret redaction.

The seal marker lists every regular file in the run. Its run status is
`completed`, or `aborted` for a deadline or a stop, or `failed`. Its outcome
status is `not-evaluated`. A trial that did not complete adds the
`partial-trial` limitation.

## Exit status and JSON output

| Exit status | Meaning |
| --- | --- |
| `0` | The trial sealed with `completed`, `deadline`, or `stopped`. |
| `1` | The trial sealed with `failed`, the lab was not usable, or the trial did not reach a seal. |
| `2` | Invalid trial options or an existing run directory. |

With `--json`, the start object adds a `trial` field. It holds `run_id`,
`attempt_id`, `terminal_cause`, `participants` with `address` and `status`, and
`cleanup`. A trial that did not reach a seal reports `trial.error` instead.
