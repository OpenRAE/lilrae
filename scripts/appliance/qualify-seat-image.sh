#!/usr/bin/env bash
# Qualify one immutable signed image through the real seat launcher and first boot.
set -euo pipefail
umask 077

source_root=$PWD
image=${1:?signed image digest is required}
public_key=${2:-}
if ! [[ "$image" =~ ^[a-z0-9][a-z0-9._/:~-]{0,254}@sha256:[a-f0-9]{64}$ ]]; then
  echo 'qualify an exact signed image digest, not a disk path or mutable tag' >&2
  exit 2
fi
aptl_cli=${APTL_SEAT_CLI:-$source_root/.venv/bin/lilrae}
test -x "$aptl_cli" || {
  echo 'installed LilRAE CLI is required' >&2
  exit 2
}
test -r /dev/kvm && test -w /dev/kvm || {
  echo 'seat qualification requires access to /dev/kvm' >&2
  exit 2
}

work=$(mktemp -d "${TMPDIR:-/tmp}/lilrae-seat-qualification.XXXXXXXX")
seat_root=$work/seat
image_cache=$work/cache
running=0
cleanup() {
  if test "$running" = 1; then
    "$aptl_cli" seat stop --seat-root "$seat_root" >/dev/null 2>&1 || true
  fi
  if test "${APTL_SEAT_QUALIFY_KEEP_WORK:-0}" = 1; then
    echo "seat qualification workspace: $work" >&2
  else
    rm -rf -- "$work"
  fi
}
trap cleanup EXIT

image_args=(
  --seat-root "$seat_root"
  --image-cache "$image_cache"
  --image "$image"
  --yes
)
if test -n "$public_key"; then
  image_args+=(--public-key "$public_key")
fi

# This first start verifies the signature into an empty cache, uses the normal
# launcher, mounts its private launch record, runs the real first-boot service,
# and requires the fatal appliance boundary gate before returning ready.
"$aptl_cli" seat start "${image_args[@]}" --desktop-mode event >"$work/clean-start.json"
running=1
"$aptl_cli" seat status --seat-root "$seat_root" >"$work/clean-status.json"
"$aptl_cli" seat stop --seat-root "$seat_root" >"$work/clean-stop.json"
running=0

# A warm restart must retain the same selected immutable image and re-run the
# current-generation readiness and boundary observations.
"$aptl_cli" seat start "${image_args[@]}" >"$work/warm-start.json"
running=1
"$aptl_cli" seat status --seat-root "$seat_root" >"$work/warm-status.json"
"$aptl_cli" seat stop --seat-root "$seat_root" >"$work/warm-stop.json"
running=0

# Reset destroys the overlay. The final start is therefore another clean
# installed-lab boot, not evidence inherited from the first one.
"$aptl_cli" seat reset "${image_args[@]}" --desktop-mode event >"$work/reset.json"
"$aptl_cli" seat start "${image_args[@]}" >"$work/reset-start.json"
running=1
"$aptl_cli" seat status --seat-root "$seat_root" >"$work/reset-status.json"
"$aptl_cli" seat stop --seat-root "$seat_root" >"$work/reset-stop.json"
running=0

echo "protected seat qualification passed: $image"
