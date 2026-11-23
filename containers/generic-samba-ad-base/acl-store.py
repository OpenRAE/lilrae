"""Convert and verify the Samba provider's xattr_tdb store (issue #976).

convert STORE TREE
    Copy every Samba-visible kernel extended attribute under TREE into STORE.
    A volume provisioned before #976 keeps its NT ACLs in kernel
    `security.NTACL` attributes. Reads need no capability. The bytes are copied
    unchanged, so custom ACLs and DOS attributes keep their meaning.

verify STORE TREE
    Fail unless STORE is a root-only file that holds a valid NT ACL for TREE and
    each directory to two levels below it.
"""

import os
import stat
import sys

import samba.xattr_native
import samba.xattr_tdb
from samba.dcerpc import xattr
from samba.ndr import ndr_unpack

# POSIX ACLs stay in the kernel; Samba does not read them through xattr_tdb.
_KERNEL_ONLY_PREFIX = "system."
# The share root, the realm directory, and its Policies and scripts directories.
_VERIFIED_DEPTH = 2


def _paths(tree):
    yield tree
    for root, dirs, files in os.walk(tree):
        for name in sorted(dirs) + sorted(files):
            yield os.path.join(root, name)


def _directories(tree, depth):
    found = [tree]
    if depth:
        for entry in sorted(os.scandir(tree), key=lambda item: item.name):
            if entry.is_dir(follow_symlinks=False):
                found += _directories(entry.path, depth - 1)
    return found


def convert(store, tree):
    copied = 0
    for path in _paths(tree):
        if os.path.islink(path):
            continue
        for name in os.listxattr(path):
            if name.startswith(_KERNEL_ONLY_PREFIX):
                continue
            value = samba.xattr_native.wrap_getxattr(path, name)
            samba.xattr_tdb.wrap_setxattr(store, path, name, value)
            copied += 1
    os.chmod(store, 0o600)
    print(f"copied {copied} extended attributes into {store}")


def verify(store, tree):
    try:
        info = os.lstat(store)
    except OSError as error:
        raise SystemExit(f"{store} is unavailable: {error}")
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise SystemExit(f"{store} must be a regular file owned by root with mode 0600")
    checked = _directories(tree, _VERIFIED_DEPTH)
    for path in checked:
        try:
            blob = samba.xattr_tdb.wrap_getxattr(store, path, xattr.XATTR_NTACL_NAME)
            ndr_unpack(xattr.NTACL, blob)
        except Exception as error:
            raise SystemExit(f"{store} has no valid NT ACL for {path}: {error}")
    print(f"{store} holds NT ACLs for {len(checked)} sysvol paths")


def main(argv):
    if len(argv) != 4 or argv[1] not in {"convert", "verify"}:
        raise SystemExit("usage: aptl-samba-acl-store convert|verify STORE TREE")
    action, store, tree = argv[1:]
    (convert if action == "convert" else verify)(store, tree)


if __name__ == "__main__":
    main(sys.argv)
