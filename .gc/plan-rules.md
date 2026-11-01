# LilRAE plan rules

Mandatory constraints the `/implement` skill applies during plan phase.

- One issue = one PR. A delivery PR MUST address every acceptance criterion
  of its issue, including code, documentation, and tests. Extend the existing
  PR; do not distribute one issue across multiple PRs. If an issue is too large,
  create smaller linked issues with explicit acceptance criteria and one
  complete PR per smaller issue. The parent tracks their delivery.
- Verification follows changed behavior and risk. Existing tests can provide
  sufficient evidence; an edit does not require a new test. Add focused pytest
  or Vitest cases only for behavior or important failure paths not covered.
  Delete redundant, obsolete, and implementation-mirroring tests rather than
  preserving test counts or coverage percentages. Use `pytest -m fuzz` for
  property-based tests.
- Plans that touch `mcp/aptl-mcp-common` MUST account for the fact that
  every MCP server consumes it. Run only targeted common and consumer tests
  locally; CI/CD rebuilds and tests every dependent MCP before the change is
  considered complete.
- Plans that change any Compose asset (`docker-compose*.yml`), container
  Dockerfiles, or `config/` files MUST include focused local contract tests.
  CI/CD owns the clean `lilrae lab stop -v && lilrae lab start` validation on a
  fresh machine — the lab is the primary product, not the codebase.
- Local verification MUST remain change-scoped: targeted pytest or Vitest
  paths plus `pre-commit run` on staged files. Bare/full suites,
  `pre-commit run --all-files`, whole-tree prose checks, dependency checks, and
  coverage runs are CI/CD-only.
- Plans MUST NOT edit `CHANGELOG.md` or the version. Releases are automated by
  release-please from Conventional Commit PR titles: `feat:` (minor),
  `fix:`/`perf:` (patch), `feat!:` or a `BREAKING CHANGE:` footer (major);
  `docs`/`chore`/`refactor`/`test`/`ci`/`build` do not release. The PR title is
  the changelog entry, so make it a clear Conventional Commit. See
  `docs/releasing.md`.
- New code MUST use `lilrae` naming: a new distribution, top-level import
  package, command, service, environment variable (`LILRAE_`), resource name,
  or configuration file is named for LilRAE, not APTL. Module and package
  names inside `src/` state their responsibility and carry no product prefix
  ([ADR-064](../docs/adrs/adr-064-layered-architecture-and-code-conventions.md)).
  Code that extends an existing interface MUST keep
  that interface's current identifiers (for example the `aptl` import root,
  `aptl.*` entry-point groups, existing config fields, `APTL_*` variables, and
  runtime resource names); add no alias, shim, or parallel `lilrae` spelling.
  Renaming an existing identifier needs its own compatibility decision. See
  [ADR-062](../docs/adrs/adr-062-lilrae-name-and-naming-convention.md).
- The CLI command is `lilrae` (ADR-062 successor clause for #1402). New code,
  scripts, messages, and docs MUST call `lilrae` and
  `lilrae-misp-suricata-sync`. The `aptl` and `aptl-misp-suricata-sync`
  aliases exist only for existing users until 10.0.0 (#1403); do not add new
  callers of them.
- Plans for Go code (ADR-065) MUST write the design record in the front matter
  of `docs/architecture/issue-<number>-<topic>-design.md` before any code. The
  plan phase runs `go run -C tools ./cmd/archcheck design -base
  origin/<base branch> <note>` and states the result in the plan. Fix each
  finding before the code phase.
