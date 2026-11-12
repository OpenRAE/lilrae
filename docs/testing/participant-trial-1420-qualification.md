# Per-trial participant evidence

This historical Reference preserves the issue’s recorded candidate and qualification limits.
Its commands and observations do not authorize workstation execution or qualify a later release.
Use [Verify a change](index.md) for current test boundaries.



The candidate uses native records and one approved local observer in the existing managed OpenCode path.
It adds no recording proxy or telemetry destination.
Qualification uses synthetic content, synthetic credentials and a local fake model provider.

It does not contact a live model or qualify the scientific matrix.

## Evidence sources

| Required fact | Source | Qualification and limit |
| --- | --- | --- |
| Exact authored prompt | User text in the private session database | Byte comparison and independently computed commitment; raw text is discarded |
| Authored placement | Native user message and exact composed bytes | The fake provider separately verifies a user-message prefix |
| Selected model and gateway | Native user and assistant model fields | Compared against the sealed request; this does not attest upstream serving identity |
| Session, message and step membership | Native database identifiers | Fresh contexts reject multiple sessions and ambiguous message membership |
| Per-step timing | Native part timestamps | Retained as native report timing, distinct from network timing |
| Input, output, reasoning and cache tokens | Native step-finish records | Separate counters; missing remains unknown and reported zero remains zero |
| Native cost | Native step-finish estimate | Retained as estimated cost, without a provider billing claim |
| Run, attempt, entry, participant and configuration | Sealed request, retained attempt and independent owner binding | Preserved in the existing invocation evidence sink |
| Outgoing routing, fallback, reasoning, sampling, seed omission, token and usage controls | Local provider-fetch observer and independent fake provider | Exact serialized values and required omissions checked before forwarding |
| Provider generation identifier | Response stream in the provider-fetch observer | Joined to each local call; absent on rejected or interrupted calls when not reported |
| Upstream model and provider claims | Response stream when reported | Claims are separate from requested identifiers and immutable serving attestation |
| Billing cost | Unavailable from this native source | A native estimate does not establish billed cost |

The metadata source is explicitly `native-session-history`.
Its unavailable fields include outgoing controls, provider generation identifiers, served identities and billing cost.
`require_fields()` refuses claims that the source cannot satisfy.

The separate `provider-fetch` source supplies actual request controls, generation joins and available response claims.
Its schema is `lilrae-provider-observation/v1`; missing provider fields remain unknown.
No matching digest or session estimate silently satisfies that requirement.


## Local qualification

The pinned Linux baseline is OpenCode 1.19.5.
Its executable SHA-256 is `7df4e4136301f16589b0f30bf91a61380fca5f8ef22dd36570f5ebe1d4ec802c`.
The existing installer verifies this identity.


The native tests compile sealed configurations through the public RAE compiler.
The fixed control runs first for both participant roles.
A separate variation case changes selected models and prompts across consecutive trials.

Focused lifecycle checks verify that trial serving configures participants before runtime advancement, preserves pending scopes, and releases leases only after terminal cleanup.
The fixed production trial uses 30-second action limits within a 90-second attempt.
This proves that invocation limits and the original attempt deadline remain separate.

Unsupported invocation limits fail application admission before placement or credentials.
Turn checks use one native assistant turn and fifty logical scenario steps to prevent an accidental equivalence between the two counters.
Scheduler qualification advances the public stepped clock and proves that consecutive one-step and two-step trials stop each role at their own horizon.

Separate consecutive deadline checks stop later dispatch at two and four seconds of the retained attempt clock.
Real supervised child processes expire at their remaining half-second and one-second allowances and are reaped.
The legacy selection path accepts a trial beyond 600 seconds when its original deadline permits it, then refuses a new selection at that deadline.

Each request is checked at the independent provider and in the native session history.
The cases require separate session identifiers and removal of private invocation directories.
Provider-rejection tests preserve partial native prompt-delivery evidence.

Unit tests cover missing and corrupted records, ambiguity, symlinks, byte limits, strict counters and secret exclusion.
Trial tests check scope substitution, missing owners, changed authoring input and original deadline exhaustion.
Existing managed-process tests cover timeout, cancellation, cleanup uncertainty and evidence-sink failure.


```bash
LILRAE_TEST_OPENCODE=/absolute/path/to/qualified/opencode \
  bash tools/run-targeted-tests.sh \
  tests/test_opencode_transport.py \
  tests/test_opencode_native_history.py \
  tests/test_trial_participant_configuration.py \
  tests/test_trial_participant_bounds.py \
  tests/test_opencode_observation.py \
  tests/test_trial_participant_transport.py
```

For reproduction, run only those targeted files in CI or an approved isolated VM.
CI owns complete suites, dependency auditing and installed-lab qualification.

## Native tracing inspection

An isolated probe also enabled native OpenTelemetry export while retaining pure mode.
The local synthetic receiver accepted native trace batches.
The final inspected probe contained 644 spans after one completed model request.

The inspected spans did not expose model-request control attributes or the provider generation identifier.
The debug log did not expose temperature, generation limit or the provider generation identifier.
This finding applies to the pinned binary and inspected execution path.

It is not a claim that all OpenCode tracing paths lack these fields.
The feature therefore consumes the native history facts it can verify and names the remaining gaps.

## Local observer verification

The pinned local module uses built-in filesystem and hashing APIs only.
Npm offline mode prevents dependency downloads during plugin loading.
Native qualification proves missing plugins and changed controls produce zero affected provider requests.

Split-stream tests preserve generation membership, reasoning-zero values and reported cost without private content.
Credential and tool-capability markers are excluded from retained metadata.
Missing usage remains unknown and fails a required usage claim.

Failed retries retain separate membership without duplicating completed-call usage.
Installed-wheel checks cover successful calls, rejection, admitted tools, timeout, cancellation and teardown uncertainty.
The shared RAE trial-serving tests execute fixed and varied sealed requests through the production application hook, including changed models and prompts for both roles.

The observer also verifies and records the native assistant-turn bound.
A second request after that many completed assistant turns is refused; failed request attempts remain separate.
Mutation checks cover request-control validation, secret exclusion and the native turn guard.
