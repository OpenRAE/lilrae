#!/usr/bin/env bash
# Acquire the official Node.js runtime and authenticate it against the release
# signature before it is admitted to the offline appliance payload.
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 OUTPUT_DIRECTORY" >&2
  exit 2
fi

output=$1
source_root=$(git rev-parse --show-toplevel)
lock="$source_root/appliance/guest/node-runtime.sha256"
image='ubuntu:26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78'
version=22.23.4
archive="node-v${version}-linux-x64.tar.xz"
release_key_commit=481637f813e912c4aa3622d7964ab426c97b8e8d
release_key_fingerprint=5BE8A3F6C8A5C01D106C0AD820B1A390B168D356
release_key_sha256=5115095e2f8010c75da052ecb1cfb3af630e084f0f8daa93a863557b01b0f90a

test ! -e "$output" || {
  echo "staging directory already exists: $output" >&2
  exit 1
}
test "$(wc -l <"$lock")" -eq 1
grep -Eq "^[0-9a-f]{64}  ${archive}$" "$lock"
install -d -m 0700 "$output"

docker run --rm \
  --volume "$output:/output" \
  --volume "$lock:/node-runtime.sha256:ro" \
  --env "NODE_VERSION=$version" \
  --env "NODE_ARCHIVE=$archive" \
  --env "NODE_RELEASE_KEY_COMMIT=$release_key_commit" \
  --env "NODE_RELEASE_KEY_FINGERPRINT=$release_key_fingerprint" \
  --env "NODE_RELEASE_KEY_SHA256=$release_key_sha256" \
  "$image" sh -ec '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update >/dev/null
    apt-get install --no-install-recommends -y ca-certificates curl gnupg >/dev/null

    key=/tmp/node-release-key.asc
    manifest=/tmp/SHASUMS256.txt.signed
    verified_manifest=/tmp/SHASUMS256.txt
    keyring=/tmp/node-release-keyring.gpg
    export GNUPGHOME=/tmp/node-gnupg
    install -d -m 0700 "$GNUPGHOME"
    curl --proto "=https" --tlsv1.2 --fail --silent --show-error --location \
      "https://raw.githubusercontent.com/nodejs/release-keys/${NODE_RELEASE_KEY_COMMIT}/keys/${NODE_RELEASE_KEY_FINGERPRINT}.asc" \
      --output "$key"
    printf "%s  %s\n" "$NODE_RELEASE_KEY_SHA256" "$key" |
      sha256sum --check --strict
    observed_fingerprint=$(gpg --batch --show-keys --with-colons "$key" |
      awk -F: '\''$1 == "fpr" { print $10; exit }'\'')
    test "$observed_fingerprint" = "$NODE_RELEASE_KEY_FINGERPRINT"
    gpg --batch --no-default-keyring --keyring "$keyring" --import "$key" \
      >/dev/null 2>&1

    release_url="https://nodejs.org/dist/v${NODE_VERSION}"
    curl --proto "=https" --tlsv1.2 --fail --silent --show-error --location \
      "$release_url/SHASUMS256.txt.asc" --output "$manifest"
    gpgv --keyring "$keyring" --output "$verified_manifest" "$manifest"
    expected=$(cat /node-runtime.sha256)
    grep -Fqx "$expected" "$verified_manifest"

    curl --proto "=https" --tlsv1.2 --fail --silent --show-error --location \
      "$release_url/$NODE_ARCHIVE" --output "/output/$NODE_ARCHIVE"
    (cd /output && sha256sum --check --strict /node-runtime.sha256)
    chmod 0644 "/output/$NODE_ARCHIVE"
  '

expected=$(sed -n 's/^[0-9a-f]\{64\}  //p' "$lock")
actual=$(find "$output" -maxdepth 1 -type f -printf '%f\n')
test "$actual" = "$expected" || {
  echo 'staged Node.js runtime does not match the lock' >&2
  exit 1
}
(cd "$output" && sha256sum --check --strict "$lock")
