# Agent Instructions

LilRAE uses Ground Control for requirements and workflow automation.

## Execution boundary

Do not run LilRAE commands, lab lifecycle operations, or tests on the
developer workstation. Run them only in CI or an explicitly approved,
isolated test VM. Workstation work is limited to source edits, static
checks, Git operations, and commit hygiene. Remote test runs must still
use targeted test paths; full suites remain CI-only.

## Ground Control Context

This repo's Ground Control project id, workflow commands, SonarCloud
settings, and plan rules live in `.ground-control.yaml` at repo root
(with larger rule files under `.gc/`).
Read them with `gc_get_repo_ground_control_context`. The MCP tool returns the workflow configuration.

Read these configured values:

- Ground Control project: `aptl`
- GitHub repo: `OpenRAE/lilrae`
- Targeted test command in an approved test VM: `bash tools/run-targeted-tests.sh` (changed test files
  only, or pass explicit test paths)
- Local hygiene command: `pre-commit run` after staging the intended changes
- Full suites, coverage, whole-tree lint, and whole-tree prose checks: CI/CD
  only
- SonarCloud project key: `Brad-Edwards_aptl` (org: `brad-edwards`)
- Plan rules: `.gc/plan-rules.md`

## Skill Installation

Install the canonical implement and review-tests skills at the user level.
Their sources are `skills/implement/SKILL.md` and `skills/review-tests/SKILL.md` in Ground Control.
From an approved Ground Control checkout, run:

```bash
bin/install-skills.sh
```

That script symlinks the canonical skills into:

- `~/.claude/skills/` (Claude Code)
- `~/.codex/prompts/` (Codex)

Both clients read the same canonical files.
After updating Ground Control, rerun the installer.
Use `--copy` when symlinks are unavailable.
Use `--no-codex` when Codex is not installed.

Do not restore the repository copies removed by Ground Control PR #792.
Keep the existing `ship`, `stage`, `gh-workflow-monitor`, and `wave-issue-coverage` skills under `.claude/skills/`.

## RAES Asset Inventory Capture Skill

For inventory work, use the RAES methodology and capture tools.
Install its user-level skill from an approved RAES checkout:

```bash
bin/install-raes-inventory-skill.sh --raes-repo ../raes
```

For another checkout path, set `RAES_REPO=../raes2` or pass `--raes-repo <path>`.
The installer creates these skill links:

- `~/.claude/skills/raes-asset-inventory-capture`
- `~/.codex/skills/raes-asset-inventory-capture`
- `~/.codex/prompts/raes-asset-inventory-capture.md`

Use that installed skill together with the RAES inventory docs when
capturing evidence or encoding inventory results for APTL.

## Ground Control Overview

Read requirements in `docs/requirements/<UID>/requirement.md`.
Use their front matter for lifecycle state and their `## Traceability` sections for artifact links.
Use Git history for earlier revisions.
Ground Control MCP tools enforce workflow records and publication boundaries.
Check each tool's current schema before use. Do not assume retired backend tools remain available.

## Workflow

The `/implement` skill (installed at user level; see above) drives the
end-to-end loop. Summary for agents working in this repo:

1. **Read the requirement.** Read its exact UID path under `docs/requirements/`.
   Do not synthesize or rewrite requirement prefixes.
2. **Plan.** Apply `.gc/plan-rules.md`. Select evidence for changed behavior
   and risk. Existing tests can be sufficient; new tests are not required for
   every edit. Delete redundant or obsolete cases. Shared MCP changes select
   their consumers; lifecycle and configuration changes select installed-lab
   qualification. See [CI verification](docs/architecture/ci-verification.md).
3. **Implement.** Make the code change.
4. **Verify in an approved test VM or CI.** Run only tests targeted to the changed behavior. Use
   `bash tools/run-targeted-tests.sh` when the relevant test files changed, or
   pass explicit test paths to that script. Stage the intended changes and run
   `pre-commit run` for rapid hygiene and secret scanning. Do not run bare
   `pytest`, package-wide `npm test`, `pre-commit run --all-files`, or other
   full/whole-tree gates locally; CI/CD owns those runs.
5. **Create traceability.** Follow `/implement` to record `IMPLEMENTS` and `TESTS` links in the requirement file.
6. **Transition status.** Follow the configured lifecycle rules through `/implement`.
   Include status and traceability edits in the delivery PR before publication.
   Do not claim local edits are merged requirement state.

## Workflow Notes

### Documentation

Use the shared `documentation` skill from the pinned doc-tools package for documentation changes.
Existing user-level installations remain supported.
Follow `docs/contributing-documentation.md` for supported client setup.
`bash tools/install-doc-tools.sh` installs the reviewed package; do not copy its tools or skill here.

Select a Diataxis purpose from the reader's task. Verify technical claims
against code, configuration, and supported interfaces. Preserve technical meaning.

Follow [the documentation guide](docs/contributing-documentation.md) for
STE limits, explicit-path checks, and source records.
Record source paths, revision, checks, and corrected differences in the PR.
Keep the skill outside repository version control. Keep routine edits small.

### Delivery

- One issue = one PR. The issue's delivery PR must address all acceptance
  criteria, including code, documentation, and tests. Update an existing PR
  instead of splitting the issue across multiple PRs. If an issue is too large,
  create smaller linked issues with explicit acceptance criteria and one
  complete PR per smaller issue. See [coding standards](docs/CODING_STANDARDS.md).
- Pass full requirement UIDs exactly as they exist in Ground Control.
  Do not synthesize or rewrite requirement prefixes.
- Keep repo-native checks, docs, and Ground Control policy in sync.
  Do not rely on agent-specific user-level hooks as the only
  enforcement layer.
- Skipping tests or pre-existing problems as "not my scope" is not
  acceptable; surface them to the user (per repo `CLAUDE.md`).
