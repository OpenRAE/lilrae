#!/usr/bin/env bash
# Run changed or explicitly named tests without falling back to a full suite.
set -euo pipefail

# Sync the dependency selection of requirements/dev.txt, which CI installs.
# The installed-artifact tests build wheels with `python -m build
# --no-isolation`, so they need the hatchling backend from the build group.
uv_test_env=(--group build --no-default-groups --extra dev --extra web)

# run_go_tests runs the packages of Go test files, each from its module, with
# the flags of the CI test gate (ADR-065). A package runs whole, because a
# single test file can need the other files of its package.
run_go_tests() {
    local file dir module rel
    local -A packages=()
    for file in "$@"; do
        dir=$(dirname -- "$file")
        module=$dir
        while [[ ! -f "$module/go.mod" ]]; do
            if [[ "$module" == . || "$module" == / ]]; then
                echo "No go.mod above $file." >&2
                return 2
            fi
            module=$(dirname -- "$module")
        done
        rel=${dir#"$module"}
        packages["$module"]+=" ./${rel#/}"
    done
    for module in "${!packages[@]}"; do
        read -r -a package_dirs <<<"${packages[$module]}"
        (cd -- "$module" && go test -race -shuffle=on "${package_dirs[@]}")
    done
}

if (($#)); then
    go_tests=()
    pytest_args=()
    python_target=false
    for arg in "$@"; do
        case "$arg" in
            *_test.go) go_tests+=("$arg") ;;
            *)
                pytest_args+=("$arg")
                # A Python target is an existing .py file, or a node ID of one.
                # The value of an option, such as the . of --rootdir ., is not.
                target=${arg%%::*}
                if [[ "$target" == *.py && -f "$target" ]]; then
                    python_target=true
                fi
                ;;
        esac
    done
    # pytest without a target runs the whole suite, so other arguments need
    # a Python test path. Go tests take no extra arguments.
    if ((${#pytest_args[@]})) && [[ "$python_target" != true ]]; then
        echo "These arguments need a Python test path: ${pytest_args[*]}" >&2
        exit 2
    fi
    if ((${#go_tests[@]})); then
        run_go_tests "${go_tests[@]}"
    fi
    if ((${#pytest_args[@]})); then
        exec uv run "${uv_test_env[@]}" pytest "${pytest_args[@]}"
    fi
    exit 0
fi

# The base branch is the one that /implement uses (.ground-control.yaml
# workflow.base_branch, default dev), so a long-lived branch such as
# go-cutover does not select every test that differs from dev.
base_branch=$(sed -n 's/^  base_branch: *\([^ #]*\).*/\1/p' .ground-control.yaml 2>/dev/null | head -n 1)
base_ref="origin/${base_branch:-dev}"

declare -A seen=()
test_paths=()

add_path() {
    local path=$1
    [[ -n "$path" && -f "$path" ]] || return 0
    case "$path" in
        tests/test_*.py|tests/**/test_*.py|mcp/*/tests/*.test.ts|web/tests/*.test.ts)
            ;;
        web/caddy-build/*|*/testdata/*)
            return 0
            ;;
        *_test.go)
            ;;
        *)
            return 0
            ;;
    esac
    if [[ -z "${seen[$path]:-}" ]]; then
        seen[$path]=1
        test_paths+=("$path")
    fi
}

while IFS= read -r path; do
    add_path "$path"
done < <(
    {
        git diff --name-only --diff-filter=ACMR "$base_ref...HEAD" 2>/dev/null || true
        git diff --cached --name-only --diff-filter=ACMR
        git diff --name-only --diff-filter=ACMR
        git ls-files --others --exclude-standard
    } | sort -u
)

if ((${#test_paths[@]} == 0)); then
    echo "No changed test files found." >&2
    echo "Pass explicit targeted Python or Go tests, for example:" >&2
    echo "  bash tools/run-targeted-tests.sh tests/test_feature.py" >&2
    echo "  bash tools/run-targeted-tests.sh tools/internal/regression/check_test.go" >&2
    echo "For Vitest, run npx vitest with exact test paths in the package." >&2
    exit 2
fi

python_tests=()
go_test_files=()
declare -A vitest_packages=()
for path in "${test_paths[@]}"; do
    case "$path" in
        *_test.go)
            go_test_files+=("$path")
            ;;
        tests/*.py)
            python_tests+=("$path")
            ;;
        mcp/*/tests/*)
            package=${path%%/tests/*}
            relative=${path#"$package/"}
            vitest_packages["$package"]+=" $relative"
            ;;
        web/tests/*)
            relative=${path#web/}
            vitest_packages[web]+=" $relative"
            ;;
    esac
done

if ((${#go_test_files[@]})); then
    run_go_tests "${go_test_files[@]}"
fi

if ((${#python_tests[@]})); then
    uv run "${uv_test_env[@]}" pytest "${python_tests[@]}"
fi

for package in "${!vitest_packages[@]}"; do
    # The paths originate from git, where whitespace-bearing test paths are not
    # used. Keep package-local Vitest resolution and avoid a package-wide run.
    read -r -a package_tests <<<"${vitest_packages[$package]}"
    (
        cd "$package"
        npx vitest run "${package_tests[@]}"
    )
done
