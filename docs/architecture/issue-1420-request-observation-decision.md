# Native participant observation assessment

Status: native sources inspected with OpenCode 1.19.5; the local observer is approved.
The implementation now consumes bounded native session facts through the existing invocation evidence sink.

## Existing OpenCode records

An isolated native invocation creates a session database and a local log.
The session database records exact user content, selected model and gateway provider, assistant content, message identifiers and timing.
It also records reported input, output, reasoning and cache tokens, cost and finish state.
These are native session observations, rather than a copy of the requested configuration.
They can establish more application evidence than the current stdout reducer retains.
Selected gateway identity does not attest the upstream serving provider.

The pinned binary also exports native OpenTelemetry traces without a plugin.
A synthetic local collector received these traces with pure mode still enabled.
The probe enabled `experimental.openTelemetry` and selected a loopback OTLP endpoint.
A second probe used debug logging and a short trace export interval.
It received 644 spans after one completed model request.
Neither probe exposed model-request control attributes or a generation identifier in its trace spans.
The debug log did not contain temperature, generation limit or the generation identifier.
These findings apply to the inspected execution path and pinned binary.
They do not establish that every supported native path has the same limits.

The independent fake provider observed the model, high reasoning effort, temperature 0.2 and generation limit 128.
It also observed the exclusive provider route, fallback denial and parameter-support requirement.
This observation qualifies transport construction; it is separate from evidence retained during an experimental trial.

## Existing Claude Code proof

`tests/test_installed_participant_controls.py` runs the qualified native binary against a local fake API.
It inspects the received model, effort, omitted sampling fields and exact authored prefix.
It tests provider rejection and compares reported token totals with the received requests.
These tests prove request construction for the qualified binary and selected profiles.

The current managed adapter uses JSON output and disables session persistence.
`AgentUsageRecorder` retains invocation token reports, requested model, participant and configuration identity in the existing run store.
It explicitly leaves served-model and served-provider claims unknown.
It does not retain complete HTTP requests during ordinary execution.
The qualification evidence must not be described as continuous runtime request capture.

## Implementation implications

Native logs, exported history and supported traces must be assessed before adding an observation mechanism.
The initial plugin proposal preceded native inspection and was withdrawn.
The completed inspection leaves outgoing request controls and provider generation identifiers without a native source on this path.
The user approved one repository-owned local plugin through OpenCode's supported provider-fetch interface.
Observed trial invocations select that pinned local file and disable blanket pure mode.
Private configuration, disabled ambient discovery, default plugins and tool restrictions remain enforced.
The child uses npm offline mode, so the local observer requires no package downloads.
The request URL and credential remain unusable until the observer initializes.
The implementation retains actual safe controls and available response claims through the existing evidence sink.
The [qualification matrix](../testing/participant-trial-1420-qualification.md) maps required evidence fields to their native or observer source.
Missing observations must remain unknown, or fail admission when a capture contract requires them.
Generated configuration and matching digests cannot replace missing actual-request observations.
Raw histories and traces require safe reduction before they enter the retained metadata evidence.
The inspection used only synthetic content, synthetic credentials and local fake services.

## References

- [OpenCode native trace exporter](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/core/src/observability/otlp.ts): version 1.19.5, endpoint configuration and OTLP export.
- [OpenCode interactive trace](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/cli/cmd/run/trace.ts): version 1.19.5, interactive JSONL trace scope.
- [OpenCode plugin loading](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/plugin/index.ts): version 1.19.5, configuration hooks and pure-mode restriction.
- [OpenCode provider fetch](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/provider/provider.ts): version 1.19.5, supported custom fetch composition.
- [Existing native qualification](../testing/participant-request-1419-qualification.md): executable identities, request assertions and limitations.
- [Architecture preflight](issue-1420-trial-participant-configuration-preflight.md): required distinctions between selected intent and actual delivery.
