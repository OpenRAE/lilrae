#!/bin/sh
set -eu

ready=/run/aptl-samba-provider.ready
while [ ! -f "$ready" ]; do
    sleep 0.1
done

# The marker survives a stop and start of this container, so check the NT ACL
# store again before each Samba start (issue #976).
xattr_store=$(testparm -s --parameter-name=xattr_tdb:file 2>/dev/null) || {
    echo "smb.conf names no xattr_tdb store" >&2
    exit 1
}
python3 -I /usr/local/sbin/aptl-samba-acl-store verify "$xattr_store" /var/lib/samba/sysvol

exec /usr/sbin/samba -F --no-process-group
