#!/bin/bash
# Compatibility entry point; doc-tools owns ste-cli installation and pins.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE="$(bash "$ROOT/tools/install-doc-tools.sh")"
exec bash "$PACKAGE/tools/install-ste.sh" "$@"
