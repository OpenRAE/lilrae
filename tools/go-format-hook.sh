#!/usr/bin/env bash
# pre-commit check of the staged Go files with the gofmt of the toolchain that
# go.mod pins (ADR-065). "go env GOROOT" resolves that toolchain, so an older
# gofmt on the PATH cannot accept or reject other code than CI does.
set -euo pipefail

if (($# == 0)); then
    exit 0
fi
gofmt="$(go env GOROOT)/bin/gofmt"
unformatted=$("$gofmt" -l -- "$@")
if [[ -n "$unformatted" ]]; then
    echo "go-format-hook: these files are not gofmt-formatted; run gofmt -w on them:" >&2
    echo "$unformatted" >&2
    exit 1
fi
