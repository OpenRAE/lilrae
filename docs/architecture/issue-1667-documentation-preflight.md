# Issue #1667 documentation preflight

## Record status

This historical Reference records the architecture preflight for issue #1667 on 2026-11-07.
The source revision is `6d35d245f11a7fffcaac1645cd25ccfafbad4599`.
It records design constraints, not implementation completion or qualification results.

The source contains the #1664 tooling change, merged in `3c9a2547` through PR #1671.
The existing [Diataxis design](diataxis-adoption.md) and
[documentation guide](../contributing-documentation.md) cover the documentation architecture.
No new ADR, schema, tool, skill, or publishing system is needed.

## Documentation boundaries

Current architecture reasons serve Explanation. Task instructions serve How-to guides.
Exact contracts serve Reference. A directory name does not determine reader purpose.
The [assignment register](documentation-assignments.md) owns migration scope, including pages split into other directories.
Existing Reference and operating pages from #1666 remain the sources for their facts.

ADR identifiers, dates, status, rationale, and amendment links keep their meaning.
An editorial rewrite does not reverse an accepted decision or accept a proposed decision.
[ADR-000](../adrs/adr-000-use-adrs.md) owns decision governance.
An older decision and its successor remain separate records.
Current explanations link the applicable amendments and replacements.

Historical requirements, preflights, reviews, and qualification reports record their source revision and limits.
Unknown provenance stays explicit; the rewrite date is not an evidence date.
Requirement front matter, UIDs, lifecycle states, and traceability identifiers retain their recorded values.
This issue does not change the GRC workflow platform's state.

Owned summaries can explain historical records in STE.
Exact quotations, outputs, evidence files, signed bytes, and generated records remain intact.
Historical commands retain their spelling. They do not become current operating instructions.
Current commands use `lilrae`; existing import roots and configuration identifiers retain their supported names.

## Contract owners and security boundaries

These paths are relative to the repository root.
They identify existing owners to inspect, not new implementations to add.
Examples and explanations must preserve each applicable gate.
The documentation change adds no runtime authorization path.

| Layer | Canonical owners | Constraint on the rewrite |
| --- | --- | --- |
| Configuration and secret locators | `src/aptl/core/config.py`, `src/aptl/core/_credential_sources.py` | Preserve Pydantic fields, discriminators, forbidden extra fields, and bounded names. Environment grants name a pack, consumer, variable, and source. They do not contain secret values. |
| Environment delivery | `src/aptl/core/deployment/_environment_bindings.py`, `_generated_environment_bindings.py`, `_compose_environment.py` | Preserve source classification and exact generated-output identity. A matching ambient variable name is not a grant. Missing or unsafe values cause refusal before mutation. |
| MCP configuration and calls | `src/aptl/core/mcp_configuration.py`, `mcp/aptl-mcp-common/src/config.ts`, `server.ts`, `lilrae-tool-admission.ts` | Keep configuration loading, advertised argument schemas, and participant admission distinct. Ajv checks advertised arguments without coercion. Admission does not replace schema validation. |
| Participant policy | `src/aptl/core/mcp_policy.py`, `participant_mcp_policy.json`; `src/aptl/workbench/dispatch.py` | Preserve role ceilings, admitted inventory, and method authorization. Legacy host access and current participant action admission have different owners. |
| HTTP and browser authentication | `src/aptl/api/deps.py`, `session.py`, `middleware/bff.py`, `routers/terminal.py`; `web/src/lib/session.ts`, `bff.ts`; `web/Caddyfile` | Preserve bearer authentication, Host checks, same-origin mutation checks, cookie plus session-header checks, and separate WebSocket authentication. Loopback binding alone does not authenticate a caller. |
| External HTTP transport | `src/aptl/utils/curl_safe.py`; `mcp/aptl-mcp-common/src/http.ts` | Preserve existing timeout, TLS, and CA handling. The curl helper keeps secret headers and bodies in private files. Do not replace it with credentials in command arguments or disable verification for convenience. |
| Response and error boundaries | `src/aptl/api/schemas.py`, `src/aptl/core/deployment/errors.py`, `src/aptl/core/mcp_results.py`, `mcp/aptl-mcp-common/src/server.ts`, `lilrae-tool-outcome.ts` | Reuse existing response models, typed failures, and tool results. Distinguish known failure from an unknown outcome. Do not expose raw exceptions, credentials, arguments, or private paths in examples. |
| Logging and telemetry | `src/aptl/utils/logging.py`, `redaction.py`; `src/aptl/core/telemetry.py`, `telemetry_export.py`; `mcp/aptl-mcp-common/src/redaction.ts`, `telemetry.ts`, `telemetry-export.ts` | Keep diagnostic logging, trace export, and research evidence distinct. Preserve existing redaction boundaries. A telemetry module does not prove that a service runs in the admitted scenario. |
| Persistence and signed input | `src/aptl/core/runstore.py`, `runstore_internals.py`; `src/aptl/utils/pathsafe.py`, `strict_json.py`; `src/aptl/appliance/policy.py` | Preserve private storage, sealing, and path containment. Structured writes are redacted; opaque bytes are not. Keep duplicate-key rejection and signed-document versions distinct from prose formats. |
| Host and guest exposure | `src/aptl/core/execution_boundary.py`, `src/aptl/core/deployment/`, `src/aptl/appliance/`; `scripts/appliance/`, `containers/`, `config/`, `docker-compose*.yml` | Check listeners, transport, permissions, process arguments, and guest boundaries against their owners. Examples must not put credentials in process arguments or reusable URLs. Localhost does not mean VM containment. |

Real credentials and private runtime files are not documentation inputs.
The user-level secret file remains off limits.
No new hosting, publication, or external text processing is authorized.
Use existing local prose checkers and existing CI.

The static site and runtime UI use different renderers.
`web/src/lib/markdown.ts` uses DOMPurify; this is not a MkDocs validation gate.
The rewrite adds no scripts or remote embeds.

## Architecture distinctions

[ADR-064](../adrs/adr-064-layered-architecture-and-code-conventions.md) describes a staged refactor.
Its target package structure is not proof of current dependency direction.
`pyproject.toml` owns the layer map and enrollment.
`tools/check_architecture.py` owns executable layer checks.
`tools/check_lilrae_participant_architecture.py` owns the participant dependency check.
Neither static check establishes runtime isolation.

`tools/check_pack_boundary.py` and `.gc/pack-ownership.json` own the pack boundary check.
Keep that existing static check; do not introduce another ownership register for runtime content.

`src/aptl/core/scenario_catalog.py` owns scenario selection and the RAES parser boundary.
`src/aptl/backends/scenario_family.py` owns the family provider extension contract.
`src/aptl_techvault/` owns TechVault-specific adapter behavior.
Keep portable RAES schemas, deployment realization, and scenario content distinct.
Do not copy an upstream schema or infer current pack contents from root Compose assets.
Repository manifests and locks describe different dependency facts; discrepancies need explicit evidence, not an editorial dependency update.

The architecture overview still uses `aptl` commands.
`src/aptl/cli/main.py` identifies `lilrae` as the current command and `aptl` as its deprecated alias.
Correct current instructions without changing historical command evidence.
Web specifications and seat records also have different delivery boundaries.
The API authentication sources above do not establish current VM-seat delivery.
Removal claims need code and history, plus the relevant successor decision, such as ADR-063.

## Navigation and future changes

`mkdocs.yml` remains the only site navigation configuration.
Keep useful paths and heading fragments, including links into ADR amendments.
When content moves, the old path and fragment retain a short link to the canonical destination.
Do not retain a second copy of the contract to preserve a URL.
Root policies and historical evidence do not move merely to match a Diataxis route.

The extension seam is the existing page and section assignment, plus ordinary Markdown links.
New split pages retain #1667 ownership and an explicit reader purpose.
Later topics use this seam without a new page schema, generator, or classification service.
Historical snapshot notices belong beside their records; current facts belong in maintained canonical pages.

## Evidence and verification limits

Each rewritten section needs its source paths, source revision, checks, and corrected differences in the delivery PR.
[Interface source checks](../reference/interface-source-checks.md) provide an existing correspondence-record example.
Historical claims use source history. Current claims use the candidate revision.
Missing source evidence remains a stated limit, not an inferred success.

This preflight used repository source and history inspection only.
It did not run behavior tests or inspect an external checkout.

Vale and STE use the explicit-path wrappers in the documentation guide.
Review Diataxis purpose, STE rules, and technical terms separately.
Finished pages join `.ste-required.txt`; partial rewrites use its documented passage-check method.
Do not rewrite exact evidence or add broad exclusions to obtain a passing result.

`.github/workflows/checks.yml` owns documentation checks and the strict MkDocs build.
`tests/test_docs_publishing.py` and `tests/test_docs_user_journey.py` cover existing routes and interface correspondence.

`tools/ci/select_checks.py` selects checks from changed paths.
Page-only changes select the documentation lane.
`.ste-required.txt` currently uses the unknown-input fallback, which selects all lanes.
Do not weaken that fallback to avoid checks during this rewrite.
Claims that need those tests require explicit targeted CI or approved-VM evidence.
Existing architecture cases include `tests/test_check_architecture.py` and `tests/test_lilrae_participant_architecture.py`.

Historical probe instructions do not override the workstation execution boundary.
Local pre-commit retains staged hygiene, secret checks, and its existing pack ownership check.

## Non-goals

This preflight does not rewrite the assigned corpus or provide an implementation plan.
The delivery changes no runtime behavior, dependencies, authority, schemas, error hierarchy, or persistence format.
It adds no custom tooling, skill, full local suite, or test that only asserts rewritten wording.
It does not qualify a lab, promote a release, or change a requirement's lifecycle state.
