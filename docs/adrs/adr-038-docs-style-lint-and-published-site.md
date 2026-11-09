# ADR-038: Documentation Style Lint and Published Docs Site

## Status

accepted

## Date

2026-06-11

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [documentation guide](../contributing-documentation.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

Issue #407, for DOC-001, found 12 missing navigation targets and only 12 of 38 ADRs listed. SDL, RAES, testing, and many component pages were omitted. The configured MkDocs Material site was unpublished, and the tree had no prose gate. Prose quality drifted unchecked because nothing
gated it, and nav drift went unnoticed because nothing built the site.

An upstream workflow already supplied pinned, checksum-verified Vale installation, a wrapper hook, Google error rules, and a small project overlay. The design reused that apparatus. Porting it is cheaper and better-tested than inventing a new
one.

## Decision

Adopt Vale as the prose linter and publish the docs site to GitHub
Pages, gated by a strict mkdocs build.

- **Vale, Google style, error level.** `.vale.ini` applies the Google
  package plus an `AptlProject` overlay (tracked under
  `.vale/styles/AptlProject/`) to all markdown, with
  `MinAlertLevel = error`. `tools/install-vale.sh` installs a pinned,
  SHA-256-verified Vale binary into the gitignored `.tools/` directory;
  `tools/vale-lint-hook.sh` is the pre-commit entry point and
  `tools/vale-lint-all.sh` lints the full corpus in CI.
- **Reasoned exclusions, not blanket ones.** Generated artifacts
  (`CHANGELOG.md`, `changelog.d/`), agent-facing contracts (`.claude/`,
  `.gc/`, `.github/`, `AGENTS.md`, `CLAUDE.md`), RAES inventory
  evidence bundles, and dated point-in-time records (`docs/history/`,
  `docs/known-issues/`, smoke-test results) carry empty
  `BasedOnStyles` blocks in `.vale.ini`: the record value of those
  files outweighs style conformance, and rewriting history to satisfy
  a linter is worse than not linting it.
- **`Google.Units` is disabled.** Lab docs quote literal config values
  (`512MB` memory limits, `300s` timeouts). Inserting a space between
  number and unit would make prose diverge from the strings that
  appear in compose files and CLI output.
- **Strict mkdocs build in CI.** The `docs` job in `checks.yml` runs
  `mkdocs build --strict`, so a nav entry pointing at a missing page or
  a broken internal link fails the build instead of rotting silently.
- **GitHub Pages deploy on `main`.** A dedicated workflow builds the
  site and deploys it via `actions/deploy-pages` on pushes to `main`.
  The `mike` version provider was dropped from `mkdocs.yml`: no
  versioned-docs workflow exists, and carrying the config without the
  apparatus misleads.

## Amendment: Dual Publishing On Read The Docs

Issue #1114 revisited hosting on 2026-09-22. Keep GitHub Pages as the canonical
site and publish a mirror on Read the Docs. This is an explicit dual-hosting
decision, not a migration.

- GitHub Pages retains the stable `https://brad-edwards.github.io/aptl/` URLs,
  avoiding broken inbound links and a redirect-only legacy deployment.
- Read the Docs builds the same `mkdocs.yml` from the same repository. It does
  not own a second navigation tree, copy of the prose, dependency list, or
  generated site output.
- `.readthedocs.yaml` installs the hash-locked `requirements/docs.txt` closure,
  installs APTL itself without resolving a second dependency graph, and treats
  MkDocs warnings as build failures.
- Both publishers build from full Git history for revision metadata. GitHub
  Actions uses `fetch-depth: 0`; Read the Docs must successfully unshallow its
  checkout when necessary.
- The GitHub Pages URL remains `site_url`, so canonical metadata from either
  rendering identifies one preferred site. The Read the Docs mirror is an
  additional discovery and version surface, not an independently edited site.

The repository configuration is necessary but not sufficient to publish the
mirror. A maintainer must import `Brad-Edwards/aptl` in Read the Docs and keep
the default version bound to the protected release branch. Pull-request builds
may be enabled, but they do not replace the repository's required strict docs
check.

## Amendment: STE checks and reader routes

Issue [#1664](https://github.com/OpenRAE/lilrae/issues/1664) adds the upstream
[ste-cli v0.10.1](https://github.com/TudorAndrei/ste-cli/tree/v0.10.1).
The tool uses the MIT license. `tools/install-ste.sh` pins release asset
SHA-256 checksums and installs the binary under `.tools/ste/0.10.1/`.
It verifies the archive before extraction or execution.

`tools/ste-lint.sh` requires explicit paths. `.ste.yml` selects sentence
length, paragraph length, and contractions.
The wrapper sets `--fail-over 0` to make findings fail.
Other STE rules are disabled initially. No second passive-voice gate is added.

Vale retains the Google error checks. Google contraction suggestions are disabled.
No dictionary import, remote analyzer, or custom prose checker is added.

During editing, run Vale and STE on explicit changed paths.
CI reports selected STE findings across tracked Markdown.
Legacy findings remain advisory during migration. Pages in `.ste-required.txt`
must pass. Each later rewrite adds its finished pages to this list.

Partial rewrites also require an explicit check of the rewritten passage.
The [documentation guide](../contributing-documentation.md) gives the commands.

Local pre-commit runs staged hygiene and secret checks only.
It does not install or run prose tools. This boundary replaces the earlier
first-commit installation statement below. CI runs corpus prose checks and
the strict MkDocs build. Behavior tests run only in CI or an approved isolated VM.
Targeted tooling and navigation tests cover the changed behavior.

MkDocs keeps Home and adds real routes for Tutorials, How-to guides,
Reference, and Explanation. Existing page paths remain intact.
Existing publishers and hash-locked dependencies remain the source of truth.
One user-level `documentation` skill serves both agent clients.
The repository holds guidance links, not a copy of that skill.

Preserve exact evidence, generated releases, quotations, licenses, and upstream notices.
Check historical narrative against its source revision.
Check current claims against candidate code. Rewrite owned descriptions in STE.
Edit maintained generator prose at its source.
The [assignment register](../architecture/documentation-assignments.md) records delivery ownership and reader purpose.

## Consequences

- Changed Markdown must pass the selected Google error rules. CI examines the full applicable corpus to catch drift and integration differences.
- The published site exposes nav rot immediately: a page that exists
  on disk but not in `nav` is visible in the strict build log, and a
  removed page fails the build.
- The two public hosts cannot acquire source-level content drift because both
  consume the same tree, configuration, and locked documentation dependencies.
  A host outage can still make one rendering temporarily stale.
- Contributors get one new local dependency, installed automatically
  and verified by checksum on first commit that touches markdown.
- The Google style is a US-English, developer-docs voice. Where it
  conflicts with deliberate house usage the fix is a tracked rule in
  `AptlProject/`, not a per-file waiver.

## Non-Goals

- Spell-checking and warning/suggestion-level style advice. The gate
  is errors only; raising `MinAlertLevel` later is a one-line change.
- Linting prose inside code comments, SDL YAML descriptions, or web UI
  strings. The gate covers markdown only.
- Versioned documentation. If a release-versioned site is wanted
  later, reintroduce `mike` together with the workflow that drives it.

## References

- Issue [#407](https://github.com/Brad-Edwards/aptl/issues/407), requirement DOC-001
- The upstream workflow platform's ADR-054 (Vale gate) and ADR-055 (style exclusions), the ported pattern
- [ADR-026](adr-026-advisory-ci-vulnerability-scanning.md): the checks.yml advisory/blocking job split this docs job slots into
