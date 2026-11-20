# UI-008a: the SvelteKit app builds to a static SPA (adapter-static). The
# dev/preview container serves those static assets with Caddy and reverse-proxies
# /api/* to the FastAPI BFF (aptl-web-api). No Node server, no control-plane
# token, no SSR — the shipped delivery contract is `aptl web serve`.
FROM node:26.13.1-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc AS builder

WORKDIR /app
RUN test "$(node --version)" = "v26.13.0"
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Build the same Caddy release with patched Go dependencies and the local
# go-jose v3 security backport documented under caddy-build/third_party.
FROM golang:1.27.3-alpine@sha256:fa3d596898d9f126af7c01d14ee7597bab3f39cccf392ef36b69fe77cd681f18 AS caddy-builder

WORKDIR /src
COPY caddy-build/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/caddy . \
    && /out/caddy version

FROM caddy:2-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
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
