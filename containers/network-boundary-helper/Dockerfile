FROM alpine:3.24@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6

# Apply every pending Alpine update first, as operator-access-proxy does. The
# pinned base predates them; currently they are libcrypto3, libssl3 and zlib,
# whose 1.3.2-r1 fixes CVE-2026-85091. Then add the pinned packages.
# Each "~" pin fixes the upstream version and accepts any Alpine package
# release of it. Alpine removes an older -rN release when it publishes a
# new one, so an exact -rN pin stops the build.
RUN apk upgrade --no-cache \
    && apk add --no-cache iproute2~7.0.0 nftables~1.1.6 python3~3.14.10 \
    && adduser -D -H -u 65532 boundary

COPY containers/network-boundary-helper/helper.py /usr/local/bin/aptl-boundary-helper
COPY containers/network-boundary-helper/probe.py /usr/local/bin/aptl-boundary-probe

ENTRYPOINT ["python3", "/usr/local/bin/aptl-boundary-helper"]
