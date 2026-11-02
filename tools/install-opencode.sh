#!/usr/bin/env bash
# Install the qualified OpenCode build before participant execution.
set -euo pipefail

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'This OpenCode build supports Linux x86_64 only.' >&2
    exit 2
fi
if [[ $# != 1 || $1 != /* ]]; then
    echo 'Usage: bash tools/install-opencode.sh /absolute/install/directory' >&2
    exit 2
fi
opencode_install_dir=$1
opencode_download_dir=$(mktemp -d)
trap 'rm -rf "$opencode_download_dir"' EXIT
curl --fail --location --proto '=https' --tlsv1.2 --retry 2 \
    --output "$opencode_download_dir/opencode.tar.gz" \
    https://github.com/anomalyco/opencode/releases/download/v1.19.5/opencode-linux-x64-baseline.tar.gz
(
    cd "$opencode_download_dir"
    printf '%s\n' '17c200fd4b2289954cc01552559f9b6d03ec157b2ddfb5eb54144f491656333d  opencode.tar.gz' | sha256sum --check
    tar -xzf opencode.tar.gz opencode
    printf '%s\n' '7df4e4136301f16589b0f30bf91a61380fca5f8ef22dd36570f5ebe1d4ec802c  opencode' | sha256sum --check
)
install -d -m 0755 "$opencode_install_dir"
install -m 0755 "$opencode_download_dir/opencode" "$opencode_install_dir/opencode"
