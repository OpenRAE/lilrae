#!/bin/bash
# Run Vale over the full lintable markdown corpus (ADR-038) and the comments
# of the first-party Go code (ADR-065).
#
# Single source of truth for which tracked .md and .go files are prose-linted.
# The exclusions mirror the per-path `BasedOnStyles =` resets in
# .vale.ini (generated artifacts, agent-facing contracts, dated
# point-in-time records) plus files Vale cannot parse. The
# former vale-prose-lint hook carried the same
# regex in its `exclude:` — keep the two in sync.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALE_BIN="${REPO_ROOT}/.tools/vale/current/vale"

# The installer is idempotent and points VALE_BIN at the pinned version.
bash "${REPO_ROOT}/tools/install-vale.sh" >&2

cd "${REPO_ROOT}"
{
  git ls-files '*.md' \
    | grep -vE '^(\.claude/|\.gc/|\.github/|changelog\.d/|CHANGELOG\.md|AGENTS\.md|CLAUDE\.md)'
  # web/caddy-build holds vendored Go code, and test data holds fixtures.
  git ls-files '*.go' | grep -vE '^web/caddy-build/|(^|/)testdata/'
} | xargs "${VALE_BIN}" --config=.vale.ini
