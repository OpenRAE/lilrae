#!/bin/bash
# Explicit paths only; all language checks belong to the upstream binary.
set -euo pipefail
if [[ $# -eq 0 ]]; then
  echo 'Usage: bash tools/ste-lint.sh [ste lint options] FILE [FILE ...]' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/.tools/ste/0.10.1/ste"
if [[ ! -x "$BIN" ]]; then
  bash "$ROOT/tools/install-ste.sh" >&2
fi
exec "$BIN" lint --config "$ROOT/.ste.yml" --no-baseline --fail-over 0 "$@"
