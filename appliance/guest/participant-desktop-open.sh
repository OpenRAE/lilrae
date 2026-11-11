#!/bin/sh
# Open the participant desktop that lab start published (issue #1273): the
# declared logins, the pack's guide, then each console URL in tab order.
# Usage: participant-desktop-open.sh [--wait-for-range] <desktop directory>
set -eu
wait_for_range=false
if test "${1:-}" = --wait-for-range; then
    wait_for_range=true
    shift
fi
desktop=${1:?usage: participant-desktop-open.sh <desktop directory>}
if "$wait_for_range"; then
    # The root-owned oneshot becomes active only after the range and hostname
    # publication succeed. PartOf stops/restarts it with the range; failures
    # never become ready. No participant-writable marker authorizes publication.
    until systemctl is-active --quiet lilrae-participant-hosts.service \
        && test -f "$desktop/credentials.html" \
        && test -f "$desktop/guide.html" \
        && test -f "$desktop/consoles.txt"; do
        sleep 2
    done
fi
set --
for page in credentials.html guide.html; do
    if test -f "$desktop/$page"; then set -- "$@" "file://$desktop/$page"; fi
done
if test -s "$desktop/consoles.txt"; then
    while IFS= read -r url; do set -- "$@" "$url"; done < "$desktop/consoles.txt"
fi
if test "$#" -eq 0; then set -- about:blank; fi
exec epiphany "$@"
