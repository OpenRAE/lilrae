#!/bin/bash
# Explicit paths only; doc-tools owns the configuration and checks.
set -euo pipefail
if [[ $# -eq 0 ]]; then
  echo 'Usage: bash tools/ste-lint.sh [ste lint options] FILE [FILE ...]' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE="$(bash "$ROOT/tools/install-doc-tools.sh")"
exec bash "$PACKAGE/tools/ste-lint.sh" "$@"
