# APTL Debian substrate with the offline TechVault package closure. Services,
# configuration, identities, and scenario content are still materialized from
# the admitted plan; no first-boot package repository is reachable or needed.
#
# Runs under APTL's systemd posture (issue #955): env container=docker,
# cgroupns=private, security-opt writable-cgroups=true, tmpfs
# /run+/run/lock+/tmp, NO added capabilities, the daemon's default seccomp and
# AppArmor profiles, /sbin/init. Requires Docker Engine 28.0+ for
# `writable-cgroups`. The retired recipe booted this substrate `degraded`:
# holding CAP_SYS_ADMIN made systemd attempt host operations
# (dev-hugepages.mount, sys-fs-fuse-connections.mount, logind) that then failed.
# The official Python 3.14 image is Debian 13 (trixie) plus CPython 3.14 under
# /usr/local. The APTL runtime closure requires Python 3.14 (RAES 9), which
# Debian 13 does not package (issue #1407).
FROM python:3.14-slim@sha256:c3e521df8b2b498a7a682e7e18676771cb80c6b75b8699af886b2d554ce40151
# gnupg: debian:12 ships gpgv (verify-only) but not the full gpg binary
# apt-key needs for some bookworm InRelease signature paths — without it,
# a materialized node's own first `apt-get update` intermittently fails
# with "Unknown error executing apt-key" (issue #581, caught only by a
# real fresh-machine boot with no pre-existing apt cache to mask it).
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus gnupg \
        bind9 dnsutils iptables postgresql samba python3-pip python3-venv \
    && rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub /etc/ssl/private/ssl-cert-snakeoil.key /etc/ssl/certs/ssl-cert-snakeoil.pem \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete
COPY requirements/runtime.txt /tmp/aptl-runtime-requirements.txt
# The venv carries the locked pip. The base image's own pip is unpinned and
# unused after that, so remove it together with its vendored certifi.
RUN /usr/local/bin/python3.14 -m venv /opt/aptl/venv \
    && /opt/aptl/venv/bin/pip install --require-hashes \
        -r /tmp/aptl-runtime-requirements.txt \
    && /opt/aptl/venv/bin/python -c "import pip._vendor.msgpack as m; assert m.Unpacker.__module__ == 'pip._vendor.msgpack.fallback'" \
    && rm /tmp/aptl-runtime-requirements.txt \
    && /usr/local/bin/python3.14 -m pip uninstall --yes pip
ENV PATH="/opt/aptl/venv/bin:${PATH}"
# Ship no private keys; each container generates its own at boot (issue #1193).
COPY containers/_host-identity /tmp/aptl-host-identity
RUN sh /tmp/aptl-host-identity/install.sh && rm -rf /tmp/aptl-host-identity

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
