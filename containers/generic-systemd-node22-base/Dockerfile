# APTL backend substrate for nodes that require Node.js 22 and systemd-managed
# services.  The product/runtime state remains materialized from the admitted
# scenario; this image supplies only the selected language + init/SSH substrate.
# The backend selects it for a node declaring `nodejs` version 22, so the Node
# major is part of its contract: Dependabot refreshes the digest but never the
# major (issue #1193). The slim variant omits the full buildpack toolchain
# (desktop, media, and kernel-header packages) this substrate never uses.
# Resolve the offline npm cache inputs with the APTL runtime closure, which
# requires Python 3.14 (RAES 9). Debian 13 does not package it, so this build
# stage uses the official Python 3.14 image on the same Debian release and
# hands over only the verified lockfiles and their identity (issue #1407).
FROM python:3.14-slim@sha256:c3e521df8b2b498a7a682e7e18676771cb80c6b75b8699af886b2d554ce40151 AS npm-cache-input
COPY requirements/runtime.txt /tmp/aptl-runtime-requirements.txt
COPY src/aptl /tmp/aptl-cache-src/aptl
COPY src/aptl_techvault /tmp/aptl-cache-src/aptl_techvault
RUN set -eu; \
    install -d /opt/aptl; \
    python3 -m pip install --no-deps --require-hashes \
        --target /tmp/aptl-cache-deps -r /tmp/aptl-runtime-requirements.txt; \
    PYTHONPATH=/tmp/aptl-cache-src:/tmp/aptl-cache-deps \
        python3 -m aptl_techvault.build_cache \
        > /opt/aptl/npm-cache-input-identity.json

FROM node:22.23.4-trixie-slim@sha256:8eb619e402eaede1748a3c8173bffab391592812e85136452f781741c7242ddf
RUN test "$(node --version)" = "v22.23.4" \
    && apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus gnupg openssh-server ca-certificates \
        iputils-ping nmap python3 python3-pip curl wget dnsutils netcat-openbsd \
        smbclient ldap-utils sqlmap hydra python3-impacket \
    && rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub /etc/ssl/private/ssl-cert-snakeoil.key /etc/ssl/certs/ssl-cert-snakeoil.pem \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete
# Node 22 ships npm 10, whose bundled dependencies carry fixed advisories.
# Replace it with npm 11 (which supports Node >=22.9) from the registry
# tarball, verified against its published sha512 integrity (issue #1193).
# Also drop the unused yarn and corepack tooling (this substrate uses npm only)
# so their bundled dependencies cannot fail the image vulnerability scan.
ARG NPM_VERSION=11.21.0
ARG NPM_SHA512=668bfc2a16a63677a22dd10bb63e5800bb4d9895b82f87c22d3ce37e9cd71b6c3a3121dc7f453181d94ae6e9680ae92c593fbb986514ef08bbf5c3ba46a8af3e
RUN set -eu; \
    curl -fsSL "https://registry.npmjs.org/npm/-/npm-${NPM_VERSION}.tgz" -o /tmp/npm.tgz; \
    echo "${NPM_SHA512}  /tmp/npm.tgz" | sha512sum -c -; \
    rm -rf /usr/local/lib/node_modules/npm; \
    mkdir /usr/local/lib/node_modules/npm; \
    tar -xzf /tmp/npm.tgz -C /usr/local/lib/node_modules/npm --strip-components=1; \
    rm /tmp/npm.tgz; \
    rm -rf /opt/yarn-* /usr/local/bin/yarn /usr/local/bin/yarnpkg \
        /usr/local/lib/node_modules/corepack /usr/local/bin/corepack; \
    test "$(npm --version)" = "${NPM_VERSION}"
# npm (through 12.x) bundles postcss-selector-parser 7.1.4, which carries a
# fixed advisory (CVE-2026-104844, fixed in 7.1.6) that no npm release has
# adopted. npm's ci path requires the module, so upgrade the bundled copy in
# place to 7.1.6 (identical runtime deps cssesc/util-deprecate, already present)
# and verify its published sha512 integrity.
ARG PCSS_VERSION=7.1.6
ARG PCSS_SHA512=eea0123f384a17697628b6e8459bb1f0209344c746895d3cbd69b22b33f3db6a99ed98d004e798eeb37336808b49489fb49ec752ad061111e6c70fedd1d09d33
RUN set -eu; \
    curl -fsSL "https://registry.npmjs.org/postcss-selector-parser/-/postcss-selector-parser-${PCSS_VERSION}.tgz" -o /tmp/pcss.tgz; \
    echo "${PCSS_SHA512}  /tmp/pcss.tgz" | sha512sum -c -; \
    pcss=/usr/local/lib/node_modules/npm/node_modules/postcss-selector-parser; \
    rm -rf "$pcss"; mkdir -p "$pcss"; \
    tar -xmzf /tmp/pcss.tgz -C "$pcss" --strip-components=1; \
    rm /tmp/pcss.tgz; \
    test "$(node -p "require('$pcss/package.json').version")" = "${PCSS_VERSION}"
# npm 11.21.1 still bundles ip-address 10.7.2 and undici 6.29.0, below the
# fixes for CVE-2026-111997, CVE-2026-109869 and CVE-2026-109924. Replace
# only these dependency-free packages with compatible, integrity-pinned fixes.
# Use tar -m for replacements: npm archives share a fixed timestamp, and
# BuildKit can omit a same-size replacement from the layer if its mtime is
# unchanged. Undici's old and fixed package.json are both 6290 bytes.
ARG IP_ADDRESS_VERSION=10.7.4
ARG IP_ADDRESS_SHA512=0d604c2b278cdb90fbd27ac889392042d879f7f1be9da28e4dea7a86e17d8fe1a678adc3303eb466fc60e5de6a427cfedfc007828bba79a9f62c4097fa5aca0e
ARG UNDICI_VERSION=6.29.1
ARG UNDICI_SHA512=12f46552dfd0a8012f5dd41e44c6147f0390b1fce90f3b7292b1b6a3018413fac1381a18bfdb85dfd673b0d0e1e254c51e14ebd973998ca91882e783d7666618
# npm (through 12.2.1) bundles glob 13.0.6 and minimatch 10.2.5, below the
# fixes for CVE-2026-118773 (glob 14.0.2) and CVE-2026-118764 (minimatch
# 11.0.1). npm calls only the API that the new majors keep: minimatch(),
# minimatch.match(), Minimatch#match, and glob(). Replace both, update
# path-scurry and brace-expansion, which only they use, and add the new
# minimatch dependency. Each tarball is integrity-pinned.
ARG GLOB_MATCH_VERSION=1.0.3
ARG GLOB_MATCH_SHA512=488ee4c8a1eae175c3468cf0fabf4695166489ad59905ae92d6f7caf6202d81a6bf18905184ddfbe3ce6c421b4c7bf00fbeebd1e60cdac3bd23180599871a928
ARG BRACE_EXPANSION_VERSION=5.0.12
ARG BRACE_EXPANSION_SHA512=628bd0debce168b308ac38cd0cc90d4b4d6d79af77aa11211b9c72f1febe47497e770dca8bee6c0a822823de368ae2d94c75a881692d830543854d3d88d12299
ARG MINIMATCH_VERSION=11.0.3
ARG MINIMATCH_SHA512=8a7cbfe343c41a4349439fcfbfacf79e6e856d101bcb7d86799463094264d969cd0db80f49371d23e0c3bcbaac801743e1c0f9b0cb4c85ea8f3e77a10826bc37
ARG PATH_SCURRY_VERSION=3.0.0
ARG PATH_SCURRY_SHA512=d694db42a1f5c08c0c8bf7a5790e657854d30a4cc5b0f7205cd8f0380f181865bf5b8fe41d3dddb2c13b67a347fb3baa34b3b3381d2e683eb5ca5edc01c56182
ARG GLOB_VERSION=14.0.3
ARG GLOB_SHA512=035be32300b7aa9742b28e39230d76ee09e9eec3e1aa063c9544210eb02b22cf866e67da6953c5ba8cb2ed6c8b4fd10f642459ee3eda2ddc1485098759eb04a3
RUN set -eu; \
    patch_bundle() { \
        package="$1"; version="$2"; digest="$3"; \
        curl -fsSL "https://registry.npmjs.org/${package}/-/${package##*/}-${version}.tgz" -o /tmp/npm-dependency.tgz; \
        echo "${digest}  /tmp/npm-dependency.tgz" | sha512sum -c -; \
        target="/usr/local/lib/node_modules/npm/node_modules/${package}"; \
        rm -rf "$target"; mkdir -p "$target"; \
        tar -xmzf /tmp/npm-dependency.tgz -C "$target" --strip-components=1; \
        rm /tmp/npm-dependency.tgz; \
        test "$(node -p "require('$target/package.json').version")" = "$version"; \
        node -e "require('$target')"; \
    }; \
    patch_bundle ip-address "${IP_ADDRESS_VERSION}" "${IP_ADDRESS_SHA512}"; \
    patch_bundle undici "${UNDICI_VERSION}" "${UNDICI_SHA512}"; \
    patch_bundle @isaacs/nonrecursive-glob-match "${GLOB_MATCH_VERSION}" "${GLOB_MATCH_SHA512}"; \
    patch_bundle brace-expansion "${BRACE_EXPANSION_VERSION}" "${BRACE_EXPANSION_SHA512}"; \
    patch_bundle minimatch "${MINIMATCH_VERSION}" "${MINIMATCH_SHA512}"; \
    patch_bundle path-scurry "${PATH_SCURRY_VERSION}" "${PATH_SCURRY_SHA512}"; \
    patch_bundle glob "${GLOB_VERSION}" "${GLOB_SHA512}"; \
    test "$(npm --version)" = "${NPM_VERSION}"
# This image's offline cache is an APTL-owned build integration. Resolve the
# exact compatible pack through the normal acquisition/artifact validators;
# retain dependency cache + identity evidence, never a second runtime source.
COPY requirements/runtime.txt /opt/aptl/runtime-requirements.txt
COPY --from=npm-cache-input /opt/aptl/npm-source /opt/aptl/npm-source
COPY --from=npm-cache-input /opt/aptl/npm-cache-input-identity.json \
    /opt/aptl/npm-cache-input-identity.json
ENV npm_config_cache=/opt/aptl/npm-cache
RUN set -eu; \
    for project in aptl-mcp-common mcp-indexer mcp-network \
        mcp-red mcp-reverse mcp-soar mcp-threatintel mcp-wazuh; do \
        npm --prefix "/opt/aptl/npm-source/$project" ci \
            --include=dev --ignore-scripts --no-audit --no-fund; \
    done; \
    rm -rf /opt/aptl/npm-source
# Ship no private keys; each container generates its own at boot (issue #1193).
COPY containers/_host-identity /tmp/aptl-host-identity
RUN sh /tmp/aptl-host-identity/install.sh && rm -rf /tmp/aptl-host-identity

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
