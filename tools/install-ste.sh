#!/bin/bash
# ste-cli v0.10.1, MIT: https://github.com/TudorAndrei/ste-cli
# SHA-256 pins: release checksums.txt and GitHub release asset digests.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=0.10.1
DEST="$ROOT/.tools/ste/$VERSION"
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) PLATFORM=linux-x64; SHA=d4a9fa77dec2b4623db324fc0951a0a0af6284de3cb42d1717c174bc5762e937 ;;
  Linux/aarch64|Linux/arm64) PLATFORM=linux-arm64; SHA=f788410fab9302606c80a15cb30925d40cff010e49f7279da17c71db0ec0e08e ;;
  Darwin/x86_64) PLATFORM=darwin-x64; SHA=267f11730731a3942e38c148ff80c652800986cf913097e1388d600820b1d374 ;;
  Darwin/arm64) PLATFORM=darwin-arm64; SHA=9365f616fe7053f8d9b1ec5d40cc92d74ef964ddcd07d24b727cec5937bb6c51 ;;
  *) echo 'Unsupported ste-cli platform; use Linux or macOS (x64 or arm64).' >&2; exit 2 ;;
esac

if [[ ! -x "$DEST/ste" ]]; then
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  ASSET="ste-$VERSION-$PLATFORM.tar.gz"
  curl --fail --silent --show-error --location \
    "https://github.com/TudorAndrei/ste-cli/releases/download/v$VERSION/$ASSET" \
    -o "$WORK/archive.tar.gz"
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL="$(sha256sum "$WORK/archive.tar.gz")"
  elif command -v shasum >/dev/null 2>&1; then
    ACTUAL="$(shasum -a 256 "$WORK/archive.tar.gz")"
  else
    echo 'No SHA-256 tool available; refusing installation.' >&2; exit 2
  fi
  if [[ "${ACTUAL%% *}" != "$SHA" ]]; then
    echo 'ste-cli checksum mismatch; refusing installation.' >&2; exit 1
  fi
  tar -xzf "$WORK/archive.tar.gz" -C "$WORK"
  mkdir -p "$DEST"
  install -m 755 "$WORK/ste" "$DEST/ste"
fi
"$DEST/ste" version
