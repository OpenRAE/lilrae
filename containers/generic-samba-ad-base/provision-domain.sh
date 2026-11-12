#!/bin/sh
set -eu

domain=${1:-}
realm=${2:-}
for value in "$domain" "$realm"; do
    case "$value" in
        "" | *[!A-Za-z0-9.-]*)
            exit 2
            ;;
    esac
done

private_root=/var/lib/samba/private
provisioned_marker="$private_root/.provisioned"
saved_config=/var/lib/samba/smb.conf.provisioned
# The SYSVOL share root. Conversion and verification start here.
sysvol_tree=/var/lib/samba/sysvol

# Issue #976: keep NT ACLs and other extended attributes in a root-only TDB.
# The kernel's security.NTACL store needs CAP_SYS_ADMIN for each write.
# The store lives on the persistent volume together with sysvol.
xattr_store="$private_root/xattr.tdb"
vfs_option="vfs objects = dfs_samba4 acl_xattr xattr_tdb"
store_option="xattr_tdb:file = $xattr_store"
acl_store_tool="python3 -I /usr/local/sbin/aptl-samba-acl-store"

# A volume from before #976 holds its ACLs in kernel xattrs, which Samba
# cannot see through xattr_tdb. Copy them unchanged into the store.
convert_acl_store() {
    configured_store=$(testparm -s --parameter-name=xattr_tdb:file 2>/dev/null) || true
    if [ "$configured_store" != "$xattr_store" ]; then
        $acl_store_tool convert "$xattr_store" "$sysvol_tree"
        sed -i "/^\[global\]/a\\	$vfs_option\\n	$store_option" /etc/samba/smb.conf
        cp /etc/samba/smb.conf "$saved_config"
    fi
}

if [ ! -f "$provisioned_marker" ]; then
    rm -f /etc/samba/smb.conf "$xattr_store"
    admin_password="A1!$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
    samba-tool domain provision \
        --server-role=dc \
        --use-rfc2307 \
        --dns-backend=SAMBA_INTERNAL \
        --realm="$realm" \
        --domain="$domain" \
        --adminpass="$admin_password" \
        --option="$vfs_option" \
        --option="$store_option"
    cp "$private_root/krb5.conf" /etc/krb5.conf
    cp /etc/samba/smb.conf "$saved_config"
    touch "$provisioned_marker"
else
    if [ -f "$saved_config" ]; then
        cp "$saved_config" /etc/samba/smb.conf
    fi
    if [ -f "$private_root/krb5.conf" ]; then
        cp "$private_root/krb5.conf" /etc/krb5.conf
    fi
    convert_acl_store
fi

# A missing or damaged store must not reach readiness. To recover, restore the
# volume, or run `samba-tool ntacl sysvolreset` to write the default ACLs.
$acl_store_tool verify "$xattr_store" "$sysvol_tree"

touch /run/aptl-samba-provider.ready
