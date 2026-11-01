#!/bin/sh
# Install Vale prose linter to .tools/vale/<version>/ and symlink to
# .tools/vale/current/vale.  Idempotent: exits successfully when the
# requested version is already installed.
#
# Usage: tools/install-vale.sh [--version v3.x.x]
# Default version: v3.26.0 (pinned; change here and update checksums)
#
# SHA-256 checksums sourced from:
#   https://github.com/vale-cli/vale/releases/download/v3.26.0/vale_3.26.0_checksums.txt
#
# v3.23.0 and later read Go doc comments by the Go convention: the name a doc
# comment opens with, [links], and tool directives are not prose (ADR-065).

set -eu

VALE_VERSION="${VALE_VERSION:-v3.26.0}"
# Strip leading 'v' for filename construction
VALE_VER_BARE="${VALE_VERSION#v}"

# Checksums for v3.26.0 (update when VALE_VERSION changes)
SHA256_LINUX_AMD64="22aa69a556558e4a9dfc63c17030777383d8d3c48dcdfad655fa98e839d666ed"
SHA256_LINUX_ARM64="3154179f4611140c9af54a8b3bc6a90bc02b73fe6c1f635369604dde0490406d"
SHA256_MACOS_AMD64="df42b317be6ece6a6a70d06b952deec581d047046eb93ea4632f58da56a86ff9"
SHA256_MACOS_ARM64="a6c3370f53bad93086c6b85f3163676e44e08049d69743afdcc13f3aab5b7482"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="${REPO_ROOT}/.tools/vale/${VALE_VERSION}"
CURRENT_LINK="${REPO_ROOT}/.tools/vale/current"
VALE_BIN="${INSTALL_DIR}/vale"

STYLES_DIR="${REPO_ROOT}/.vale/styles"
GOOGLE_STYLE_DIR="${STYLES_DIR}/Google"

# Run `vale sync` against the repo's .vale.ini to populate the configured
# styles (StylesPath / Packages) deterministically so the CI prose gate does not
# depend on developer-supplied style files.
sync_vale_styles() {
    if [ ! -f "${REPO_ROOT}/.vale.ini" ]; then
        return 0
    fi
    if [ -d "${GOOGLE_STYLE_DIR}" ]; then
        return 0
    fi
    printf 'Syncing Vale styles (.vale.ini → %s) ...\n' "${STYLES_DIR}"
    mkdir -p "${STYLES_DIR}"
    (cd "${REPO_ROOT}" && "${VALE_BIN}" sync)
}

if [ -x "${VALE_BIN}" ]; then
    printf 'vale %s already installed at %s\n' "${VALE_VERSION}" "${VALE_BIN}"
    # Point current at the pinned version, also after a version change.
    mkdir -p "$(dirname "${CURRENT_LINK}")"
    rm -f "${CURRENT_LINK}"
    ln -s "${INSTALL_DIR}" "${CURRENT_LINK}"
    sync_vale_styles
    exit 0
fi

OS="$(uname -s)"
ARCH="$(uname -m)"

case "${OS}" in
    Linux)
        case "${ARCH}" in
            x86_64)
                TARBALL="vale_${VALE_VER_BARE}_Linux_64-bit.tar.gz"
                EXPECTED_SHA256="${SHA256_LINUX_AMD64}"
                ;;
            aarch64|arm64)
                TARBALL="vale_${VALE_VER_BARE}_Linux_arm64.tar.gz"
                EXPECTED_SHA256="${SHA256_LINUX_ARM64}"
                ;;
            *)
                printf 'Unsupported Linux architecture: %s\n' "${ARCH}" >&2
                exit 1
                ;;
        esac
        ;;
    Darwin)
        case "${ARCH}" in
            x86_64)
                TARBALL="vale_${VALE_VER_BARE}_macOS_64-bit.tar.gz"
                EXPECTED_SHA256="${SHA256_MACOS_AMD64}"
                ;;
            arm64)
                TARBALL="vale_${VALE_VER_BARE}_macOS_arm64.tar.gz"
                EXPECTED_SHA256="${SHA256_MACOS_ARM64}"
                ;;
            *)
                printf 'Unsupported macOS architecture: %s\n' "${ARCH}" >&2
                exit 1
                ;;
        esac
        ;;
    *)
        printf 'Unsupported OS: %s\n' "${OS}" >&2
        exit 1
        ;;
esac

DOWNLOAD_URL="https://github.com/vale-cli/vale/releases/download/${VALE_VERSION}/${TARBALL}"

mkdir -p "${INSTALL_DIR}"
TMPDIR_VALE="$(mktemp -d)"
TARBALL_PATH="${TMPDIR_VALE}/${TARBALL}"

printf 'Downloading %s ...\n' "${DOWNLOAD_URL}"
if command -v curl > /dev/null 2>&1; then
    curl -fsSL -o "${TARBALL_PATH}" "${DOWNLOAD_URL}"
elif command -v wget > /dev/null 2>&1; then
    wget -q -O "${TARBALL_PATH}" "${DOWNLOAD_URL}"
else
    printf 'Neither curl nor wget is available.\n' >&2
    exit 1
fi

printf 'Verifying SHA-256 ...\n'
if command -v sha256sum > /dev/null 2>&1; then
    ACTUAL_SHA256="$(sha256sum "${TARBALL_PATH}" | awk '{print $1}')"
elif command -v shasum > /dev/null 2>&1; then
    ACTUAL_SHA256="$(shasum -a 256 "${TARBALL_PATH}" | awk '{print $1}')"
elif command -v openssl > /dev/null 2>&1; then
    ACTUAL_SHA256="$(openssl dgst -sha256 "${TARBALL_PATH}" | awk '{print $NF}')"
else
    printf 'No supported SHA-256 tool found (sha256sum, shasum, or openssl).\n' >&2
    printf 'Refusing to install unverified Vale binary; install one of these tools and retry.\n' >&2
    rm -rf "${TMPDIR_VALE}"
    exit 1
fi

if [ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]; then
    printf 'SHA-256 mismatch for %s\n  expected: %s\n  actual:   %s\n' \
        "${TARBALL}" "${EXPECTED_SHA256}" "${ACTUAL_SHA256}" >&2
    rm -rf "${TMPDIR_VALE}"
    exit 1
fi

printf 'Extracting to %s ...\n' "${INSTALL_DIR}"
tar -xzf "${TARBALL_PATH}" -C "${INSTALL_DIR}"
rm -rf "${TMPDIR_VALE}"

# The tarball may include a vale binary directly or inside a subdirectory.
VALE_FOUND=""
for candidate in "${INSTALL_DIR}/vale" "${INSTALL_DIR}/vale_${VALE_VER_BARE}"*; do
    if [ -x "${candidate}" ]; then
        VALE_FOUND="${candidate}"
        break
    fi
done

if [ -z "${VALE_FOUND}" ]; then
    # Fallback: find any executable named vale
    VALE_FOUND="$(find "${INSTALL_DIR}" -name "vale" -type f -perm -u+x | head -1)"
fi

if [ -z "${VALE_FOUND}" ]; then
    printf 'Could not find vale binary in %s after extraction.\n' "${INSTALL_DIR}" >&2
    exit 1
fi

# Normalize to ${INSTALL_DIR}/vale for the symlink target
if [ "${VALE_FOUND}" != "${VALE_BIN}" ]; then
    mv "${VALE_FOUND}" "${VALE_BIN}"
fi
chmod +x "${VALE_BIN}"

# Update the current symlink
mkdir -p "$(dirname "${CURRENT_LINK}")"
rm -f "${CURRENT_LINK}"
ln -s "${INSTALL_DIR}" "${CURRENT_LINK}"

printf 'Installed vale %s -> %s/vale\n' "${VALE_VERSION}" "${CURRENT_LINK}"
"${VALE_BIN}" --version

sync_vale_styles
