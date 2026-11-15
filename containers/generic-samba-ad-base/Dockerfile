# APTL backend substrate for an authored Active Directory identity authority.
# Domain identity and accounts are supplied later from the admitted plan; this
# image contains no scenario-specific realm, users, groups, or credentials.
FROM ubuntu:26.04@sha256:065aa8626841f16057b78b027b464cd59c4fac36c204c72dcbf48d66f5fa8a96

# Also removes the unused /usr/bin/pebble (CVE-2026-78667, -94439, -97031, -97032), as #1248 removed yarn/corepack.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        krb5-user \
        ldb-tools \
        samba \
        samba-ad-dc \
        samba-ad-provision \
        samba-dsdb-modules \
        samba-vfs-modules \
        smbclient \
        python3-samba \
        tini \
        winbind \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete \
    && rm -f /usr/bin/pebble

COPY provider-start.sh /usr/local/sbin/aptl-samba-provider-start
COPY provision-domain.sh /usr/local/sbin/aptl-provision-samba-domain
COPY acl-store.py /usr/local/sbin/aptl-samba-acl-store
RUN chmod 0755 \
        /usr/local/sbin/aptl-samba-provider-start \
        /usr/local/sbin/aptl-provision-samba-domain \
        /usr/local/sbin/aptl-samba-acl-store

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/sbin/aptl-samba-provider-start"]
