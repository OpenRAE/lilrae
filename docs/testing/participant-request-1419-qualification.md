# Participant request qualification

Issue #1419 qualifies published request configurations through the installed package and existing native adapters.
The tests build a candidate wheel and install it into a separate directory without fetching dependencies.
Child interpreters load that installation outside the source checkout.

## Native fixtures

The qualification uses local fake APIs, synthetic prompt content and fake credentials.
Private homes exclude user configuration and account state.
No model-service access or model availability is established by these tests.

| Executable | Version | SHA-256 |
| --- | --- | --- |
| Claude Code | 2.1.316 | `fd13c70000fec3f2116dfbcbb6121210b4a29328bf0e46210a59dd594a67d824` |
| Codex CLI | 0.166.0 | `b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8` |
| OpenCode | 1.19.5 | `7df4e4136301f16589b0f30bf91a61380fca5f8ef22dd36570f5ebe1d4ec802c` |

The Claude and Codex tests select reviewed profiles for `claude-sonnet-5-5` and `gpt-5.2-codex` respectively.
They inspect outgoing model identifiers, every retained effort level, omitted sampling fields and the exact authored prefix.
The tests require both the documented version and executable hash before native work.
An additional native case qualifies Codex disabled reasoning.
Claude's native build retained adaptive thinking when given attempted disable and budget controls.
The adapter therefore rejects those modes before dispatch.
Successful native responses preserve reported token usage through the installed adapter and local run store.
Provider rejection must return a bounded failure without switching the requested model.
Native retry timing can reach the explicit process deadline on this failure path.
Recording-runner tests separately check explicit native fallback restrictions and executable-pin rejection before a second request.

The pinned OpenCode tests inspect the outgoing no-fallback provider restriction, reasoning, temperature, omitted top-p and generation limit.
Each retained effort level must reach the fake provider unchanged.
They also qualify disabled reasoning, explicit reasoning budgets and explicit top-p.
They check success and provider rejection, exact prefix bytes, reported usage and unknown served identity.
See the [existing transport qualification](opencode-1504-qualification.md) for its broader isolation evidence.

## Contract and content evidence

Public installed RAES schemas round-trip the published manifests and sealed configuration results.
The public RAE compiler realizes fixed selections and independent per-participant model and prompt factors for all three implementations.
Native adapters receive the resulting owner-verified requests through their existing launch inputs.

Content tests reject wrong participant scope, stale descriptors, missing slots and changed bytes.
Reconstruction tests replace the prompt and hash, then the retained content and descriptor.
Each attempt fails against the original selected asset commitment.
Dispatch tests independently retain the trusted owner and expected participant.
They reject peer configurations and incompatible scope at launch and before later native work, with unchanged content bytes and asset pins.
Checksum tests cover every algorithm supported by the installed RAES contract.

## Reproduction

Set `LILRAE_TEST_CLAUDE`, `LILRAE_TEST_CODEX` and `LILRAE_TEST_OPENCODE` to the explicitly selected executable paths.
Run only the affected tests:

```bash
bash tools/run-targeted-tests.sh \
  tests/test_installed_participant_controls.py \
  tests/test_participant_request_dispatch.py \
  tests/test_participant_request_content.py \
  tests/test_participant_request_manifests.py \
  tests/test_participant_request_binding.py \
  tests/test_participant_agent_usage.py
```

Native qualification cases skip when their executable variable is absent.
CI installs the pinned OpenCode build and runs its request qualification automatically.
Claude and Codex native qualification currently requires the documented binaries and an explicit manual run.
Their adapter, binding, content and usage regressions run in the ordinary Python checks with recording runners.
Full suites, dependency audits and installed-lab qualification remain CI responsibilities.
