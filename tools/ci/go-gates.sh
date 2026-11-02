#!/usr/bin/env bash
# Run one Go gate of ADR-065 over each first-party Go module.
#
# Usage:
#   tools/ci/go-gates.sh modules
#   tools/ci/go-gates.sh lint
#   tools/ci/go-gates.sh test COVERAGE_DIR [MODULE...]
#   tools/ci/go-gates.sh vuln
#   tools/ci/go-gates.sh osv
#   tools/ci/go-gates.sh mutation [BASE [MODULE...]]
#   tools/ci/go-gates.sh fuzz [FUZZTIME]
#   tools/ci/go-gates.sh regression BASE ISSUE BUG
#   tools/ci/go-gates.sh architecture [BASE ISSUE PROMOTION]
#
# The modules are the go.mod files that Git tracks in the repository of the
# current directory, except web/caddy-build, which has its own checks, and
# test data. A MODULE list limits the test and mutation gates to those
# modules. The pinned tools, the lint configuration, and the mutation
# thresholds come from the repository that holds this script.
set -euo pipefail

home=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
repo=$(git rev-parse --show-toplevel)
bin=$(mktemp -d)
trap 'if [[ -n "$bin" ]]; then rm -rf -- "$bin"; fi' EXIT

# Measured on the tools packages (#1553): 4 workers on 16 CPUs and a
# coefficient of 10 gave no timed-out mutant. CI runners have 4 CPUs.
mutation_workers=2
mutation_timeout_coefficient=10

usage() {
    sed -n '4,12s/^# //p' "${BASH_SOURCE[0]}" >&2
    exit 2
}

module_list() {
    git -C "$repo" ls-files -z -- 'go.mod' '*/go.mod' \
        ':(exclude)web/caddy-build/**' ':(exclude)**/testdata/**' |
        while IFS= read -r -d '' file; do
            dirname -- "$file"
        done
}

# packages prints the packages of the module in the current directory.
packages() {
    go list ./...
}

# production_packages prints the packages of the module in the current
# directory that have Go files other than tests. Mutation testing needs them.
production_packages() {
    go list -f '{{if .GoFiles}}{{.ImportPath}}{{end}}' ./...
}

build_tool() {
    local module=$1 package=$2
    go build -C "$home/$module" -o "$bin/" "$package"
}

lint() {
    local dir goos pkgs
    build_tool tools/lint github.com/golangci/golangci-lint/v2/cmd/golangci-lint
    for dir in "${modules[@]}"; do
        echo "== $dir"
        cd -- "$repo/$dir"
        go mod tidy -diff
        pkgs=$(packages)
        if [[ -z "$pkgs" ]]; then
            echo "$dir: no packages"
            continue
        fi
        go vet ./...
        go fix -diff ./...
        for goos in linux darwin windows; do
            GOOS=$goos "$bin/golangci-lint" run --config="$home/.golangci.yml" ./...
        done
    done
}

test_modules() {
    local out dir pkgs name module prefix selected=("${@:2}")
    if ((${#selected[@]} == 0)); then
        selected=("${modules[@]}")
    fi
    mkdir -p -- "$1"
    out=$(cd -- "$1" && pwd)
    for dir in "${selected[@]}"; do
        echo "== $dir"
        cd -- "$repo/$dir"
        pkgs=$(packages)
        if [[ -z "$pkgs" ]]; then
            echo "$dir: no packages"
            continue
        fi
        name=${dir//\//-}
        if [[ "$name" == . ]]; then
            name=root
        fi
        go test -race -shuffle=on -covermode=atomic -coverprofile="$out/$name.out" ./...
        # SonarCloud reads repository paths. The profile names each file by
        # its import path.
        module=$(go list -m)
        prefix=${dir#.}
        prefix=${prefix#/}
        if [[ -n "$prefix" ]]; then
            prefix+=/
        fi
        sed -e "s#^${module//./\\.}/#${prefix}#" "$out/$name.out" >"$out/$name.out.tmp"
        mv -- "$out/$name.out.tmp" "$out/$name.out"
    done
}

vuln() {
    local dir pkgs tools patterns
    build_tool tools golang.org/x/vuln/cmd/govulncheck
    for dir in "${modules[@]}"; do
        echo "== $dir"
        cd -- "$repo/$dir"
        patterns=()
        pkgs=$(packages)
        if [[ -n "$pkgs" ]]; then
            patterns+=(./...)
        fi
        tools=$(go list tool)
        if [[ -n "$tools" ]]; then
            patterns+=(tool)
        fi
        if ((${#patterns[@]} == 0)); then
            echo "$dir: no packages and no tools"
            continue
        fi
        "$bin/govulncheck" "${patterns[@]}"
    done
}

osv() {
    local dir args=()
    for dir in "${modules[@]}"; do
        args+=(-L "$dir/go.mod")
    done
    cd -- "$repo"
    # Go call analysis uses a govulncheck that osv-scanner builds with an
    # older Go release. The govulncheck gate covers reachable code.
    osv-scanner scan source --no-call-analysis=go "${args[@]}"
}

mutation() {
    local base=${1:-} dir pkgs targets=() args=() selected=("${@:2}")
    if ((${#selected[@]} == 0)); then
        selected=("${modules[@]}")
    fi
    build_tool tools github.com/go-gremlins/gremlins/cmd/gremlins
    # A module with test files only, such as the conformance suite, has no
    # mutant, and its tests can need an installed binary.
    for dir in "${selected[@]}"; do
        pkgs=$(cd -- "$repo/$dir" && production_packages)
        if [[ -n "$pkgs" ]]; then
            targets+=("$dir")
        fi
    done
    args=(-repo "$repo" -gremlins "$bin/gremlins" -thresholds "$home/tools/mutation-thresholds.json"
        -workers "$mutation_workers" -timeout-coefficient "$mutation_timeout_coefficient")
    if [[ -n "$base" ]]; then
        args+=(-base "$base")
    fi
    go run -C "$home/tools" ./cmd/mutationcheck "${args[@]}" -- "${targets[@]}"
}

# fuzz runs each fuzz test of each package with production code for FUZZTIME,
# a value of go test -fuzztime (30s by default). go test -fuzz takes one fuzz
# test of one package at a time. A package whose tests do not build fails the
# gate.
fuzz() {
    local time=${1:-30s} dir pkgs pkg list target
    for dir in "${modules[@]}"; do
        cd -- "$repo/$dir"
        pkgs=$(production_packages)
        for pkg in $pkgs; do
            list=$(go test -list '^Fuzz' "$pkg")
            while IFS= read -r target; do
                if [[ "$target" == Fuzz* ]]; then
                    echo "== $pkg $target"
                    go test -run='^$' -fuzz="^${target}\$" -fuzztime="$time" "$pkg"
                fi
            done <<<"$list"
        done
    done
}

regression() {
    local base=$1 issue=$2 bug=$3 args
    args=(-repo "$repo" -base "$base" -issue "$issue")
    if [[ "$bug" == true ]]; then
        args+=(-bug)
    fi
    go run -C "$home/tools" ./cmd/regressioncheck "${args[@]}"
}

# architecture checks the repository against architecture/model.yaml and the
# generated diagram. With BASE, ISSUE, and PROMOTION, it also checks the change
# from BASE to HEAD against the design record of ISSUE, unless PROMOTION is
# true. It runs each check and fails when one fails.
architecture() {
    local archcheck=(go run -C "$home/tools" ./cmd/archcheck) args status=0
    if (($# == 0)); then
        "${archcheck[@]}" check -repo "$repo" || status=1
    else
        args=(-repo "$repo" -base "$1" -issue "$2")
        if [[ "$3" == true ]]; then
            args+=(-promotion)
        fi
        "${archcheck[@]}" pr "${args[@]}" || status=1
    fi
    "${archcheck[@]}" diagram -repo "$repo" || status=1
    return "$status"
}

gate=${1:-}
case $gate in
    modules | lint | test | vuln | osv | mutation | fuzz | regression | architecture) ;;
    *) usage ;;
esac
if [[ "$gate" == regression ]]; then
    (($# == 4)) || usage
    regression "$2" "$3" "$4"
    exit 0
fi
if [[ "$gate" == architecture ]]; then
    (($# == 1 || $# == 4)) || usage
    architecture "${@:2}"
    exit 0
fi
list=$(module_list)
if [[ -z "$list" ]]; then
    echo "go-gates: no Go module found below $repo" >&2
    exit 1
fi
modules=()
while IFS= read -r dir; do
    modules+=("$dir")
done <<<"$list"
case $gate in
    modules) printf '%s\n' "${modules[@]}" ;;
    lint) lint ;;
    test)
        (($# >= 2)) || usage
        test_modules "${@:2}"
        ;;
    vuln) vuln ;;
    osv) osv ;;
    mutation) mutation "${@:2}" ;;
    fuzz) fuzz "${2:-}" ;;
    *) usage ;;
esac
