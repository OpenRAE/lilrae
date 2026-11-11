"""In-sandbox launcher for the Bubblewrap containment engine (ADR-068).

Bubblewrap starts this file with the host's ``/usr/bin/python3 -I -S`` inside
the namespaces. It applies the remaining layers in order, reports each one on
its status descriptor, and then executes the target:

1. close every inherited descriptor except the status descriptor;
2. set ``no_new_privs``;
3. set resource limits;
4. restrict the filesystem and TCP with Landlock;
5. install the seccomp filter through libseccomp.

Any failure reports ``fail <layer> <detail>`` and exits before the target
starts. The status descriptor is close-on-exec, so the target cannot write to
it. The file imports only the standard library and keeps Python 3.12 syntax.
"""

import ctypes
import ctypes.util
import errno
import json
import os
import resource
import stat
import sys

_PR_SET_NO_NEW_PRIVS = 38
_SYS_LANDLOCK_CREATE_RULESET = 444
_SYS_LANDLOCK_ADD_RULE = 445
_SYS_LANDLOCK_RESTRICT_SELF = 446
_LANDLOCK_CREATE_RULESET_VERSION = 1
_LANDLOCK_RULE_PATH_BENEATH = 1

_FS_EXECUTE = 1 << 0
_FS_WRITE_FILE = 1 << 1
_FS_READ_FILE = 1 << 2
_FS_READ_DIR = 1 << 3
_FS_REFER = 1 << 13
_FS_TRUNCATE = 1 << 14
_FS_IOCTL_DEV = 1 << 15
_FS_FILE_ONLY = _FS_EXECUTE | _FS_WRITE_FILE | _FS_READ_FILE | _FS_TRUNCATE | _FS_IOCTL_DEV
_NET_ALL = (1 << 0) | (1 << 1)  # LANDLOCK_ACCESS_NET_BIND_TCP | CONNECT_TCP
_SCOPE_ALL = (1 << 0) | (1 << 1)  # LANDLOCK_SCOPE_ABSTRACT_UNIX_SOCKET | SIGNAL

_SCMP_ACT_ALLOW = 0x7FFF0000
_SCMP_COMPARE = {"eq": 4, "masked_eq": 7}

_LIMITS = {
    "core_bytes": resource.RLIMIT_CORE,
    "open_files": resource.RLIMIT_NOFILE,
    "cpu_seconds": resource.RLIMIT_CPU,
    "file_bytes": resource.RLIMIT_FSIZE,
    "address_space_bytes": resource.RLIMIT_AS,
}


class LayerError(Exception):
    """A layer could not apply; the target must not start."""

    def __init__(self, layer: str, detail: str) -> None:
        super().__init__(f"{layer}: {detail}")
        self.layer = layer
        self.detail = detail


class _RulesetAttr(ctypes.Structure):
    _fields_ = (
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    )


class _PathBeneathAttr(ctypes.Structure):
    # struct landlock_path_beneath_attr is packed: 8 + 4 bytes, no padding.
    _pack_ = 1
    _layout_ = "ms"
    _fields_ = (("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32))


class _ScmpArgCmp(ctypes.Structure):
    _fields_ = (
        ("arg", ctypes.c_uint),
        ("op", ctypes.c_int),
        ("datum_a", ctypes.c_uint64),
        ("datum_b", ctypes.c_uint64),
    )


class Status:
    """Line-oriented reports on the private status descriptor."""

    def __init__(self, fd: int) -> None:
        self.fd = fd

    def write(self, *fields: str) -> None:
        os.write(self.fd, (" ".join(fields) + "\n").encode())

    def ok(self, layer: str, detail: str = "") -> None:
        self.write("ok", layer, detail)

    def fail(self, layer: str, detail: str) -> None:
        self.write("fail", layer, detail.replace("\n", " ")[:200])


def _errno_name(code: int | None) -> str:
    return errno.errorcode.get(code or 0, str(code))


def close_descriptors(keep: int) -> int:
    """Close every descriptor above 2 except ``keep``; return how many closed."""
    try:
        open_fds = [int(name) for name in os.listdir("/proc/self/fd")]
    except OSError as exc:
        raise LayerError("descriptors", f"cannot list descriptors: {_errno_name(exc.errno)}") from exc
    closed = 0
    for fd in open_fds:
        if fd > 2 and fd != keep:
            try:
                os.close(fd)
                closed += 1
            except OSError:
                continue
    return closed


def no_new_privs(libc: ctypes.CDLL) -> None:
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise LayerError("no_new_privs", _errno_name(ctypes.get_errno()))


def set_limits(limits: dict[str, int]) -> None:
    for name, value in limits.items():
        try:
            resource.setrlimit(_LIMITS[name], (value, value))
        except (KeyError, ValueError, OSError) as exc:
            raise LayerError("limits", f"{name}: {exc}") from exc


def _syscall(libc: ctypes.CDLL, number: int, *args: object) -> int:
    result = libc.syscall(number, *args)
    if result < 0:
        raise OSError(ctypes.get_errno(), "")
    return result


def _fs_rights(abi: int) -> int:
    rights = (1 << 13) - 1
    if abi >= 2:
        rights |= _FS_REFER
    if abi >= 3:
        rights |= _FS_TRUNCATE
    if abi >= 5:
        rights |= _FS_IOCTL_DEV
    return rights


def _grant_mask(access: str, handled: int) -> int:
    read = _FS_READ_FILE | _FS_READ_DIR
    masks = {
        "read": read,
        "read_exec": read | _FS_EXECUTE,
        "device": read | _FS_WRITE_FILE | _FS_TRUNCATE | _FS_IOCTL_DEV,
        "write": handled,
    }
    return masks[access] & handled


def _ruleset(libc: ctypes.CDLL, abi: int) -> tuple[int, int]:
    attr = _RulesetAttr(_fs_rights(abi), _NET_ALL if abi >= 4 else 0, _SCOPE_ALL if abi >= 6 else 0)
    size = 24 if abi >= 6 else 16 if abi >= 4 else 8
    return _syscall(libc, _SYS_LANDLOCK_CREATE_RULESET, ctypes.byref(attr), size, 0), attr.handled_access_fs


def _add_grant(libc: ctypes.CDLL, ruleset: int, grant: dict[str, str], handled: int) -> bool:
    try:
        fd = os.open(grant["path"], os.O_PATH | os.O_CLOEXEC)
    except FileNotFoundError:
        return False
    try:
        mask = _grant_mask(grant["access"], handled)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            mask &= _FS_FILE_ONLY
        rule = _PathBeneathAttr(mask, fd)
        _syscall(libc, _SYS_LANDLOCK_ADD_RULE, ruleset, _LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(rule), 0)
    finally:
        os.close(fd)
    return True


def apply_landlock(libc: ctypes.CDLL, grants: list[dict[str, str]]) -> int:
    """Restrict this process; return the Landlock ABI that applied."""
    try:
        abi = _syscall(libc, _SYS_LANDLOCK_CREATE_RULESET, None, 0, _LANDLOCK_CREATE_RULESET_VERSION)
        ruleset, handled = _ruleset(libc, abi)
        try:
            for grant in grants:
                _add_grant(libc, ruleset, grant, handled)
            _syscall(libc, _SYS_LANDLOCK_RESTRICT_SELF, ruleset, 0)
        finally:
            os.close(ruleset)
    except (OSError, KeyError) as exc:
        detail = _errno_name(exc.errno) if isinstance(exc, OSError) else f"bad grant {exc}"
        raise LayerError("landlock", detail) from exc
    return abi


def load_libseccomp() -> ctypes.CDLL:
    try:
        library = ctypes.CDLL(ctypes.util.find_library("seccomp") or "libseccomp.so.2")
    except OSError as exc:
        raise LayerError("seccomp", "libseccomp does not load") from exc
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_init.argtypes = (ctypes.c_uint32,)
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_syscall_resolve_name.argtypes = (ctypes.c_char_p,)
    library.seccomp_rule_add_array.restype = ctypes.c_int
    library.seccomp_rule_add_array.argtypes = (
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(_ScmpArgCmp),
    )
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_load.argtypes = (ctypes.c_void_p,)
    library.seccomp_release.restype = None
    library.seccomp_release.argtypes = (ctypes.c_void_p,)
    return library


def _add_seccomp_rule(library: ctypes.CDLL, context: int, rule: dict) -> bool:
    number = library.seccomp_syscall_resolve_name(rule["syscall"].encode())
    if number < 0:
        return False
    args = rule["args"]
    array = (_ScmpArgCmp * max(1, len(args)))(
        *(_ScmpArgCmp(item["arg"], _SCMP_COMPARE[item["op"]], item["a"], item["b"]) for item in args)
    )
    action = 0x00050000 | (rule["errno"] & 0xFFFF)  # SCMP_ACT_ERRNO
    if library.seccomp_rule_add_array(context, action, number, len(args), array) < 0:
        raise LayerError("seccomp", f"rule {rule['syscall']} rejected")
    return True


def apply_seccomp(library: ctypes.CDLL, rules: list[dict]) -> int:
    """Install the deny rules; return how many applied on this architecture."""
    context = library.seccomp_init(_SCMP_ACT_ALLOW)
    if not context:
        raise LayerError("seccomp", "seccomp_init failed")
    try:
        added = sum(_add_seccomp_rule(library, context, rule) for rule in rules)
        if library.seccomp_load(context) < 0:
            raise LayerError("seccomp", "seccomp_load failed")
    finally:
        library.seccomp_release(context)
    return added


def apply_layers(status: Status, policy: dict) -> None:
    """Apply every layer in order and report each one."""
    libc = ctypes.CDLL(None, use_errno=True)
    library = load_libseccomp()
    status.ok("descriptors", f"closed={close_descriptors(status.fd)}")
    no_new_privs(libc)
    status.ok("no_new_privs")
    set_limits(policy["limits"])
    status.ok("limits")
    status.ok("landlock", f"abi={apply_landlock(libc, policy['landlock'])}")
    status.ok("seccomp", f"rules={apply_seccomp(library, policy['seccomp'])}")


def main(argv: list[str]) -> int:
    """``launcher.py <status-fd> <policy-path> -- <target argv>``."""
    status_fd = int(argv[1])
    os.set_inheritable(status_fd, False)
    status = Status(status_fd)
    target = argv[4:]
    try:
        with open(argv[2], encoding="utf-8") as stream:
            policy = json.load(stream)
        if argv[3] != "--" or not target:
            raise LayerError("arguments", "no target command")
        apply_layers(status, policy)
    except LayerError as exc:
        status.fail(exc.layer, exc.detail)
        return 126
    except (OSError, ValueError, KeyError) as exc:
        status.fail("policy", type(exc).__name__)
        return 126
    status.write("exec")
    try:
        os.execve(target[0], target, policy["environment"])
    except OSError as exc:
        status.fail("exec", _errno_name(exc.errno))
    return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv))
