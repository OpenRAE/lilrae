# UI-008a: the SvelteKit app builds to a static SPA (adapter-static). The
# dev/preview container serves those static assets with Caddy and reverse-proxies
# /api/* to the FastAPI BFF (aptl-web-api). No Node server, no control-plane
# token, no SSR — the shipped delivery contract is `aptl web serve`.
FROM node:26-slim@sha256:193fe51b64e77981119c98c2002c9e32a70e2f006fb4d25068ce0558998917f0 AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# The upstream Caddy binary uses Go and golang.org/x/net releases with known
# CVEs. Build the same Caddy release with a patched toolchain and x/net.
FROM golang:1.26-alpine@sha256:3082400e369fa24d5fc60bca20edab3f6d604e0c5a690ec66b295eff4dd87ade AS caddy-builder

WORKDIR /src
COPY caddy-build/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/caddy . \
    && /out/caddy version

FROM caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
# Apply every pending Alpine update, as operator-access-proxy does. The pinned
# base predates them; currently they are libcrypto3, libssl3 and zlib, whose
# 1.3.2-r1 fixes CVE-2026-85091.
RUN apk upgrade --no-cache
COPY --from=caddy-builder /out/caddy /usr/bin/caddy
COPY --from=builder /app/build /srv
COPY Caddyfile /etc/caddy/Caddyfile

# Run unprivileged (issue #1193): Caddy listens on unprivileged port 3000 and
# only needs its own state directories writable.
RUN addgroup -S -g 10001 caddy \
    && adduser -S -D -H -u 10001 -G caddy caddy \
    && chown -R caddy:caddy /data /config
USER 10001:10001

EXPOSE 3000
