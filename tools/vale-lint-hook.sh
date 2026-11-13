#!/bin/bash
# Check explicit Markdown paths with Vale (ADR-038).
# Install the pinned binary when absent. Installation failure stops the check.
# Local pre-commit does not invoke this wrapper; it runs staged hygiene only.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  exit 0
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALE_BIN="${REPO_ROOT}/.tools/vale/current/vale"
VALE_INI="${REPO_ROOT}/.vale.ini"
INSTALL_SCRIPT="${REPO_ROOT}/tools/install-vale.sh"

if [ ! -f "${VALE_INI}" ]; then
  echo "vale-lint-hook: missing ${VALE_INI}" >&2
  exit 1
fi

if [ ! -x "${INSTALL_SCRIPT}" ]; then
  echo "vale-lint-hook: ${INSTALL_SCRIPT} missing or not executable; cannot install Vale" >&2
  exit 1
fi
# The installer is idempotent and points VALE_BIN at the pinned version.
bash "${INSTALL_SCRIPT}" >&2

exec "${VALE_BIN}" --config="${VALE_INI}" "$@"
