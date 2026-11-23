#!/bin/bash
# doc-tools v0.1.0 (MIT), source: 97866fad14d7fbb0d6752788ebdc5ae4f235573a.
# Keep LICENSE, THIRD_PARTY_NOTICES.md and skills/documentation/LICENSE intact.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=0.1.0
SHA=125104c0cc535698d1cc9bba3e57883bdf9d87db6da346ff583967c4ce42de6c
CACHE="$ROOT/.tools/doc-tools"
DEST="$CACHE/$VERSION"

if [[ ! -f "$DEST/.archive-sha256" ]] || [[ "$(cat "$DEST/.archive-sha256")" != "$SHA" ]]; then
  mkdir -p "$CACHE"
  WORK="$(mktemp -d "$CACHE/.install.XXXXXX")"
  trap 'rm -rf "$WORK"' EXIT
  curl --proto '=https' --fail --silent --show-error --location \
    "https://github.com/OpenRAE/doc-tools/releases/download/v$VERSION/doc-tools-$VERSION.tar.gz" \
    -o "$WORK/archive.tar.gz"
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL="$(sha256sum "$WORK/archive.tar.gz")"
  elif command -v shasum >/dev/null 2>&1; then
    ACTUAL="$(shasum -a 256 "$WORK/archive.tar.gz")"
  else
    echo 'No SHA-256 tool available; refusing installation.' >&2; exit 2
  fi
  if [[ "${ACTUAL%% *}" != "$SHA" ]]; then
    echo 'doc-tools checksum mismatch; refusing installation.' >&2; exit 1
  fi
  mkdir "$WORK/package"
  tar -xzf "$WORK/archive.tar.gz" -C "$WORK/package" --strip-components=1
  printf '%s\n' "$SHA" > "$WORK/package/.archive-sha256"
  # os.rename publishes a complete directory, without nesting it on a race.
  python3 - "$WORK/package" "$DEST" "$SHA" <<'PY'
import errno
import os
from pathlib import Path
import sys

try:
    os.rename(sys.argv[1], sys.argv[2])
except OSError as error:
    if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
        raise
    if Path(sys.argv[2], ".archive-sha256").read_text().strip() != sys.argv[3]:
        raise
PY
fi
printf '%s\n' "$DEST"
