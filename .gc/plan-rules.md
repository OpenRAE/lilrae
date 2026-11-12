# LilRAE plan rules

Apply these constraints during `/implement` planning.

- Deliver one complete PR per issue, including its code, documentation, and verification.
  Extend an existing delivery PR. Do not divide one issue across PRs.
  If needed, create smaller linked issues with explicit acceptance criteria and one complete PR each.
  Keep their parent open until its criteria are satisfied.
- Select verification by changed behavior and risk. Reuse adequate existing tests.
  Add focused pytest or Vitest cases for uncovered behavior and important failure paths.
  Delete redundant, obsolete, or implementation-mirroring cases.
  Select property tests with `pytest -m fuzz`.
- For `mcp/aptl-mcp-common` changes, select targeted common-library and consumer tests.
  Every MCP server consumes that package. CI rebuilds and tests all dependent servers.
- For Compose assets, container Dockerfiles, or `config/` changes, include focused contract tests.
  CI owns clean `lilrae lab stop -v && lilrae lab start` qualification on a fresh machine.
  The lab is the primary product.
- Run targeted behavior tests and lab operations only in CI or an explicitly approved, isolated VM.
  Use the workstation for source edits, static checks, Git, and commit hygiene.
  CI owns full suites, `pre-commit run --all-files`, whole-tree checks, dependency checks, and coverage.
- Do not edit `CHANGELOG.md` or release versions.
  Use a clear Conventional Commit PR title; Release Please derives versions and release notes from it.
  Follow [Releasing](../docs/releasing.md) and its title reference.
- Use `lilrae` naming for new distributions, top-level packages, commands, services, variables, resources, and configuration files.
  New environment variables use `LILRAE_`.
  Within `src/`, name modules for their responsibility without a product prefix.
  Follow [ADR-064](../docs/adrs/adr-064-layered-architecture-and-code-conventions.md).
- Preserve identifiers when extending an existing interface.
  Examples include the `aptl` import root, `aptl.*` entry-point groups, existing fields, `APTL_*` variables, and runtime resource names.
  Add no alias, shim, or parallel `lilrae` spelling for an existing identifier.
  An identifier rename needs its own compatibility decision.
  Follow [ADR-062](../docs/adrs/adr-062-lilrae-name-and-naming-convention.md).
- Use `lilrae` and `lilrae-misp-suricata-sync` in new commands, scripts, messages, and documentation.
  Do not add callers of the old aliases.
  Issue #1403 tracks alias removal; package scripts determine current availability.
- Plans for Go code (ADR-065) MUST write the design record in the front matter
  of `docs/architecture/issue-<number>-<topic>-design.md` before any code. The
  plan phase runs `go run -C tools ./cmd/archcheck design -base
  origin/<base branch> <note>` and states the result in the plan. Fix each
  finding before the code phase.
