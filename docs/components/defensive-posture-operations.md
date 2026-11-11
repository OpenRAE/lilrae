# Change defensive posture

Use an approved isolated lab VM and an admitted scenario.
The [posture reference](default-defensive-posture.md) separates detection from response coupling.

## Inspect the baseline

1. Read the admitted scenario and startup diagnostics.
2. Use `lilrae lab info` to discover current endpoints and credential locations.
3. Examine the connected MCP servers and their schemas.
4. Before you change detection or response, record the run identity.

5. Separate startup verification events from participant events.

## Change a response

1. Use [Wazuh response configuration](wazuh-response-operations.md).
2. Select a specific detection rule and a bounded response.
3. Examine the whitelist behavior before a source-IP response test.
4. Trigger a bounded event within the authorized scenario.

5. Examine the detection and response action separately.
6. Examine timeout cleanup or do explicit recovery.

## Extend the maintained baseline

1. Reuse the existing rule, service, and scenario owners.
2. Keep new response coupling disabled until the exercise enables it.
3. Describe whether the surface is a weakness, enabled detection, or inactive response.
4. Cite the source configuration and observed runtime evidence.

5. When the design decision changes, update the governing ADR.
6. Run relevant contract tests in CI or an approved isolated VM.
