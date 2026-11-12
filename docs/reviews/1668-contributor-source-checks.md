# Contributor documentation source checks

This Reference records the contributor rewrite and final documentation inventory for issue #1668.
The implementation baseline is `809dacad67aa0d77dcd2c62506de4f02ac236576`.
Current claims use that source and the candidate tree. Historical claims retain their own revision and qualification limits.
The delivery PR records final check results and its candidate revision.

## Source correspondence

Each row applies to the maintained sections in its page group.
The [page inventory](../architecture/documentation-assignments.md#page-assignments) assigns each page a final route and source-check group.
The section inventory below identifies each rewritten heading.
A source check does not claim that a documented lab exercise ran during this rewrite.

| Group | Pages and source owners | Corrections and verification |
| --- | --- | --- |
| Entry points | `README.md`, `docs/index.md`; `pyproject.toml`, `src/aptl/cli/main.py`, `src/aptl/core/execution_boundary.py`, current installation and interface references | Remove duplicate installation procedures and alias-lifetime assumptions. Keep README links absolute for package-index readers. Keep safety limits, direct first-lab links, policy paths, and four reader routes. Existing user-journey tests check actual CLI, MCP, API, and route correspondence in CI. |
| Contributor policy | Root contributor, conduct, support, and security files; `docs/CODING_STANDARDS.md`; `pyproject.toml`, `.pre-commit-config.yaml`, `.ground-control.yaml`, ADR-064, `tools/check_architecture.py` | Correct Python support to 3.14. Keep one complete PR per issue, private reporting, host consent, dummy credentials, and all acceptance obligations. Separate targeted verification from contribution setup. |
| Release | `docs/releasing.md`, release contract, manual QA; `Makefile`, `.github/workflows/release-please.yml`, `release-please-config.json`, `tools/check_pr_title.py`, package scripts, ADR-068 | Preserve promotion/back-merge merge commits and feature squash commits. Correct the package filename, current command names, and 32 path-specific rows. Retain candidate hashes, human approval, TLS checks, reverse-target negative protocol harness, scoped teardown, and startup-bundle limits. Existing Shuffle/manual contracts run in CI. |
| Testing | `docs/testing/index.md`, fixture, parser, platform, and boot pages; `tools/run-targeted-tests.sh`, `tests/fixture_pack.py`, `scripts/ci/assert_boot_realization.py`, `assert_project_teardown.py`, `src/aptl/backends/raes_realization_envelope.py`, `.github/workflows/checks.yml`, branch baseline | Separate operating tasks from Reference coverage. Preserve native causal effects, project ownership, daemon-baseline comparison, and honest coverage gaps. Workstation behavior tests remain prohibited. Existing fixture, boot, teardown, parser, and platform contracts own behavior verification. |
| Historical qualification | Dated QA, participant, scoped-tool, OpenCode, CI-performance, and OpenSSF records; their stated commits, artifact digests, run links, and evidence files | Distinguish recorded candidates from later releases and current qualification. Keep original commands in old evidence, exact IDs, output, and all PASS/BLOCK limits. Paragraph breaks do not change observations. New reproduction instructions require CI or an approved VM. No new live qualification is claimed. |
| Agent guidance | `AGENTS.md`, `CLAUDE.md`, `.claude/skills/`, `.gc/plan-rules.md`, `.github/copilot-instructions.md`; current installed workflow skill and MCP schemas | Keep skill identities, invocation restrictions, approval boundaries, and sequential wave processing. Replace retired requirement-backend instructions with repository requirement files and the supported issue-scope writer. Resolve the workstation-test conflict. Quote the Copilot glob without changing its value. |
| Toolchain and Sonar | Documentation guide, toolchain Reference, `tools/sonar/README.md`; installers, prose wrappers, `.vale.ini`, project rules, Sonar helper and workflow | Keep package version, digest, notices, and local text processing. Enroll agent prose in existing Vale rules, with only the precise-tool-name exception. Correct the metadata-only Sonar failure claim and stale pre-commit-wrapper comment. |
| Source interfaces | CLI docstrings, API schemas/dependencies/routers, MCP definitions and server configurations, web API/types, tool argparse descriptions, build hook and asset manifest | Review generated help and schema text at its owning declarations. Correct asset-delivery and live-gate descriptions. Preserve registered legacy aliases despite their older planned removal target. Shorten raw-mode help while retaining omitted versus explicit-false behavior. No interface names, options, fields, defaults, validation, or effects change. |
| Earlier reader routes | User/workshop pages delivered by [PR #1684](https://github.com/OpenRAE/lilrae/pull/1684); interface/scenario pages delivered by [PR #1688](https://github.com/OpenRAE/lilrae/pull/1688); architecture pages delivered by [PR #1720](https://github.com/OpenRAE/lilrae/pull/1720) | Read back their assignments against candidate paths and routes. Reuse [interface source checks](../reference/interface-source-checks.md) and [architecture source checks](1667-architecture-source-checks.md) for unchanged text. Inventory additions from later issues at the current baseline. Earlier delivery is provenance, not a new qualification result. |

## Source documentation and generated text

The source inventory includes documentation inputs outside Markdown.
Docstrings and API/schema descriptions are Reference at their declarations.
Implementation reasons remain Explanation beside the relevant code.
Command examples describe their exact interface; they do not authorize execution.
Executable fixtures, directive comments, signatures, identifiers, and machine-consumed values retain their contracts.

CLI help comes from Typer declarations and function docstrings under `src/aptl/cli/`.
FastAPI/OpenAPI text comes from API route and model declarations under `src/aptl/api/`.
MCP tools use shared definitions and server configuration under `mcp/`.
Web comments describe the shared API/type boundary; the UI renderer is not the documentation-site renderer.
Tool help comes from existing `argparse` declarations and module descriptions.
`hatch_build.py` and `src/aptl/_asset_manifest.py` own bundled asset selection.

MkDocs has no configured docstring/API-generation plugin.
The maintained Markdown pages and navigation remain its source.
Release Please generates release notes from Conventional Commit history.
Edit maintained generator text at its owner, never generated releases by hand.
No new generator, checker, skill, or documentation service is introduced.

The source inventory records locations and reader purposes.
It does not certify every internal comment against the STE dictionary or establish runtime qualification.
Source review concentrates on documented contracts and text exposed through supported interfaces.
The live-gate help retains its exact reviewed pack-specific line for the existing ownership ledger.
It also retains the `DESTRUCTIVE` warning marker before the detailed cleanup conditions.
The advisory-report test selects the configured report command, independently of its display name.
The PR must not present inventory coverage as language certification.

## Preserved material

Generated releases, changelog fragments, third-party notices, license text, and non-Markdown evidence remain exact.
The fixture pack's digests and executable inputs remain unchanged.
The historical QA tables retain their observations and human-approval limits.
Qualification artifact identities do not identify a later rebuild.
Requirement files retain lifecycle states, statements, rationale, and traceability.

The old assignment register names two removed inputs: `.github/ISSUE_TEMPLATE/` and `web/svelte.config.js`.
No issue-template directory exists at this baseline.
Current tracked web inputs include `web/vite.config.ts`, `web/vitest.config.ts`, and `web/tsconfig.json`.
No replacement `svelte.config` file is inferred from the stale assignment.
Retained `.txt` documentation records remain tracked source records, not missing Markdown pages.

## Editorial review and check boundaries

Review reader purpose separately from prose-tool findings.
Use instructions within 20 words and descriptions within 25 words.
Keep paragraphs to one topic and at most six sentences.
Retain technical nouns, identifiers, quantities, conditions, obligations, and failure meanings.
Do not replace accurate code terminology to satisfy a false finding.

Explicit-path Vale and STE check rewritten maintained prose.
Preserved source bodies use the existing passage-check boundary for new descriptions.
A clean checker result does not certify full STE conformance.
No workstation behavior test, lab command, live provider call, or release operation is part of this rewrite.
CI owns targeted documentation contracts, full required checks, strict MkDocs, and corpus prose checks.

## Rewritten section inventory

The table below records the final headings of changed maintained pages.
All headings inherit the page purpose unless the page links to a separate form.

| Page | Headings |
| --- | --- |
| `.claude/skills/gh-workflow-monitor/SKILL.md` | ``Step 1: Check current branch.``, ``Step 2: Find its workflow run.``, ``Step 3: Monitor the workflow run for failures.``, ``Step 4: If the workflow run fails, propose a fix.``, ``Step 5: If the workflow run succeeds, report the status.`` |
| `.claude/skills/ship/SKILL.md` | ``Phase 1: Create PR``, ``Phase 2: CI Monitor``, ``Phase 3: SonarCloud Check``, ``Phase 4: Code Review``, ``Phase 5: Security Review``, ``Phase 6: Final Commit & CI``, ``Phase 7: Report (DO NOT MERGE)`` |
| `.claude/skills/stage/SKILL.md` | ``Step 1: Identify Changed Files``, ``Step 2: Stage Files``, ``Step 3: Pre-commit Loop``, ``Step 4: Report`` |
| `.claude/skills/wave-issue-coverage/SKILL.md` | ``Inputs``, ``Preconditions``, ``Workflow``, ``1. Resolve the requirement list``, ``2. Choose progress tracker``, ``3. Process sequentially; DO NOT parallelize``, ``4. Apply labels``, ``5. Report back``, ``Notes``, ``Quick reference; MCP calls`` |
| `.gc/plan-rules.md` | Whole document |
| `.github/copilot-instructions.md` | Whole document |
| `AGENTS.md` | All sections of the agent contract |
| `CLAUDE.md` | Whole document |
| `CODE_OF_CONDUCT.md` | ``Expected Behavior``, ``Scope``, ``Reporting``, ``Attribution`` |
| `CONTRIBUTING.md` | ``Before Opening a Pull Request``, ``Development Setup``, ``Making Changes``, ``Verification``, ``Documentation changes``, ``Safety Boundaries``, ``Host Privilege Escalation``, ``Changelog``, ``Security Reports``, ``Community Expectations`` |
| `README.md` | ``Status And Safety``, ``Quick Start``, ``Requirements``, ``Supported Interfaces``, ``Scenarios``, ``Documentation``, ``Project Links``, ``Ethics And Disclaimer``, ``License`` |
| `SECURITY.md` | ``Reporting a Vulnerability``, ``Scope``, ``Response Expectations`` |
| `SUPPORT.md` | ``Where to Ask``, ``What to Include``, ``Maintenance Expectations`` |
| `docs/CODING_STANDARDS.md` | ``Issue Delivery``, ``Architecture And Code Conventions``, ``Implementation And Verification`` |
| `docs/architecture/documentation-boundaries.md` | ``Components and contracts``, ``Data flows and trust boundaries``, ``Security and failure behavior``, ``Policy and executable architecture``, ``Shared package boundary``, ``Contributor migration completion boundary``, ``Authority and reader routes``, ``Coverage and source preservation``, ``Existing enforcement and runtime owners``, ``Verification and policy closure``, ``Sources`` |
| `docs/contributing-documentation.md` | ``Select a reader purpose``, ``Verify the facts``, ``Write the change``, ``Set up the shared tools``, ``Install the documentation skill``, ``Upgrade or roll back``, ``Run writing checks`` |
| `docs/index.md` | ``Run Your First Lab``, ``Supported Interfaces``, ``Help And Project Policies``, ``Design And Historical Records`` |
| `docs/reference/documentation-toolchain.md` | ``Shared package``, ``Rule coverage``, ``Execution and publication`` |
| `docs/reference/parser-boundaries.md` | Whole document |
| `docs/reference/release-contract.md` | ``PR titles``, ``Promotion title``, ``Baseline``, ``PyPI publisher``, ``Package names``, ``Seat artifacts`` |
| `docs/releasing.md` | ``Per PR (all contributors / agents)``, ``Promoting `dev` to `main```, ``How a release happens``, ``Baseline``, ``PyPI trusted publisher (one-time)``, ``Seat image cuts`` |
| `docs/security/openssf-best-practices.md` | ``User And Contributor Evidence``, ``Passing-Criteria Review``, ``Honest Limitations`` |
| `docs/security/update-assessment.md` | ``Review evidence``, ``Publish an approved assessment`` |
| `docs/testing/boot-realization-coverage.md` | ``Advertised concerns``, ``Beyond the envelope``, ``Declared dimensions APTL does not read back``, ``The dnf/RHEL systemd substrate has no live coverage``, ``Explicitly outside the small boot`` |
| `docs/testing/ci-performance.md` | ``Baseline``, ``Removed and consolidated work``, ``Measurements``, ``Qualification ownership`` |
| `docs/testing/evidence/1504/README.md` | Whole document |
| `docs/testing/index.md` | ``Select evidence``, ``Run targeted tests in an approved environment``, ``Check staged files``, ``Qualify a release or boundary`` |
| `docs/testing/issue-956-candidate-254bc40f-manual-qa.md` | ``Candidate and environment``, ``Path A: exact wheel``, ``Path-A bounded observations``, ``Path B: exact source commit``, ``Path-B bounded observations``, ``Release decision`` |
| `docs/testing/issue-956-candidate-e23fec55-manual-qa.md` | ``Candidate and environment``, ``Path A: candidate wheel``, ``Path-A bounded observations``, ``Path B: exact source commit``, ``Path-B bounded observations``, ``Release decision`` |
| `docs/testing/lab-fixture-pack.md` | ``Where it lives and why``, ``How tests use it``, ``Choose the input for a new test``, ``Changing the pack`` |
| `docs/testing/opencode-1504-qualification.md` | ``Boundary``, ``Installed candidate and GCP identity``, ``Docker lifecycle``, ``Bounded live trigger smoke``, ``Offline installed verification``, ``Cleanup`` |
| `docs/testing/participant-request-1419-qualification.md` | ``Native fixtures``, ``Contract and content evidence``, ``Reproduction`` |
| `docs/testing/participant-trial-1420-qualification.md` | ``Evidence sources``, ``Local qualification``, ``Native tracing inspection``, ``Local observer verification`` |
| `docs/testing/platform-pr-gates.md` | ``Required contexts``, ``Dependency checks``, ``Artifact and configuration scans``, ``Clean-install qualification`` |
| `docs/testing/property-based-parser-tests.md` | ``Scope``, ``Guardrails``, ``Boundary Ownership``, ``Non-Goals`` |
| `docs/testing/scoped-tools-1646-candidate.md` | Whole document |
| `docs/testing/scoped-tools-1646-qualification.md` | Whole document |
| `docs/testing/smoke-test-plan.md` | ``Candidate and environment record``, ``Install path A: candidate distribution``, ``Install path B: exact source commit``, ``Evidence rules``, ``Browser trust prerequisite``, ``Required actions``, ``QA-START: Complete startup and project inventory``, ``QA-LIVE: RAES live validation``, ``QA-WAZUH: Dashboard, agents, and events``, ``QA-DETECT: Attack and expected Wazuh rule``, ``QA-SURICATA: Network rule reaches the SIEM``, ``QA-SOAR: Real-alert Shuffle playbook``, ``QA-MISP: Seeded threat intelligence and round trip``, ``QA-MCP-RED: `mcp-red```, ``QA-MCP-WAZUH: `mcp-wazuh```, ``QA-MCP-INDEXER: `mcp-indexer```, ``QA-MCP-SOAR: `mcp-soar```, ``QA-MCP-TI: `mcp-threatintel```, ``QA-MCP-NET: `mcp-network```, ``QA-MCP-REVERSE: `mcp-reverse```, ``QA-ARCHIVE: Run evidence and integrity``, ``QA-TEARDOWN: Scoped removal``, ``Path A results: Candidate distribution``, ``Path B results: Exact source commit``, ``Release decision`` |
| `tools/sonar/README.md` | ``Layout``, ``New-issue gate`` |
