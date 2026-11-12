"""The launcher policy: target environment, Landlock grants, seccomp rules, limits.

The seccomp rules, the socket-family and ioctl rules, and the denied environment
names follow RAPTOR ``core/sandbox`` and ``core/config`` at commit
``28c996ca997c0aeaf94080c88733788a3b26c9e5`` (see the case ledger). No RAPTOR
code is copied.
"""

import errno
from collections.abc import Mapping
from pathlib import Path

from aptl.containment.bubblewrap import INPUT_IN_SANDBOX, SANDBOX_HOME, SANDBOX_TMP
from aptl.core.containment import ExecutionRequest

LAUNCHER_POLICY_SCHEMA = "lilrae.containment.launcher-policy/v1"
_BASE_ENVIRONMENT = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": SANDBOX_HOME}
_OPEN_FILES = 4096
_MEBIBYTE = 1024 * 1024

# Names that load code, redirect configuration, or bypass the network policy.
_DENIED_NAMES = frozenset({
    "PATH", "HOME", "TMPDIR", "IFS", "CDPATH", "BASH_ENV", "ENV", "PROMPT_COMMAND",
    "TERMINAL", "BROWSER", "PAGER", "VISUAL", "EDITOR", "GCONV_PATH", "GLIBC_TUNABLES",
    "LOCPATH", "NLSPATH", "HOSTALIASES", "RES_OPTIONS", "LOCALDOMAIN", "MALLOC_CONF",
    "JE_MALLOC_CONF", "PERL5OPT", "PERLLIB", "PERL5LIB", "RUBYOPT", "RUBYLIB",
    "NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS", "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH", "OPENSSL_CONF", "SSLKEYLOGFILE",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "NIX_SSL_CERT_FILE", "GNUTLS_SYSTEM_PRIORITY_FILE", "KRB5_CONFIG", "KRB5CCNAME",
    "PHPRC", "PHP_INI_SCAN_DIR", "EMACSLOADPATH", "DOCKER_HOST", "VIRTUAL_ENV",
})
_DENIED_PREFIXES = ("LD_", "DYLD_", "PYTHON", "MALLOC_", "GIT_")

_DENIED_SYSCALLS = (
    "keyctl", "add_key", "request_key", "bpf", "userfaultfd", "perf_event_open",
    "io_uring_setup", "io_uring_enter", "io_uring_register", "pidfd_getfd", "kcmp",
    "open_by_handle_at", "name_to_handle_at", "ptrace", "process_vm_readv",
    "process_vm_writev", "unshare", "setns", "mount", "umount2", "pivot_root",
    "move_mount", "open_tree", "fsopen", "fsmount", "fsconfig", "fspick", "mount_setattr",
    "kexec_load", "kexec_file_load", "init_module", "finit_module", "delete_module",
    "swapon", "swapoff", "reboot", "acct", "syslog", "memfd_create",
)
_CLONE_NAMESPACE_FLAGS = (
    0x00000080,  # CLONE_NEWTIME
    0x00020000,  # CLONE_NEWNS
    0x02000000,  # CLONE_NEWCGROUP
    0x04000000,  # CLONE_NEWUTS
    0x08000000,  # CLONE_NEWIPC
    0x10000000,  # CLONE_NEWUSER
    0x20000000,  # CLONE_NEWPID
    0x40000000,  # CLONE_NEWNET
)
# AF_UNIX is denied too: a read-only bind does not stop a connect to a host
# socket inside a granted directory. Stream socketpair() stays allowed for local IPC.
# AF_UNIX, AF_KEY, AF_PACKET, AF_ALG, AF_VSOCK
_DENIED_SOCKET_FAMILIES = (1, 15, 17, 38, 40)
_SOCK_TYPE_MASK, _SOCK_DGRAM, _SOCK_RAW = 0xF, 2, 3
# The kernel reads int arguments from the low 32 bits only; compare those bits.
_INT_MASK = 0xFFFFFFFF
# TIOCSTI, TIOCLINUX
_DENIED_TTY_IOCTLS = (0x5412, 0x541C)
_AT_EMPTY_PATH = 0x1000

type Rule = dict[str, object]


def denied_environment_names(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Return the requested names that the policy refuses."""
    return tuple(
        name for name in environment
        if name in _DENIED_NAMES
        or name.startswith(_DENIED_PREFIXES)
        or name.lower().endswith("_proxy")
    )


def _rule(syscall: str, *args: dict[str, object], code: int = errno.EPERM) -> Rule:
    """One seccomp rule: the system call, the errno to return, and the argument tests."""
    return {"syscall": syscall, "errno": code, "args": list(args)}


def _arg(index: int, op: str, a: int, b: int = 0) -> dict[str, object]:
    """One libseccomp argument comparison."""
    return {"arg": index, "op": op, "a": a, "b": b}


def seccomp_rules() -> list[Rule]:
    """Return the deny rules; every other system call stays allowed."""
    rules = [_rule(name) for name in _DENIED_SYSCALLS]
    # glibc falls back to clone() when clone3() reports ENOSYS; clone flags are checkable.
    rules.append(_rule("clone3", code=errno.ENOSYS))
    rules += [_rule("clone", _arg(0, "masked_eq", flag, flag)) for flag in _CLONE_NAMESPACE_FLAGS]
    rules += [_rule("socket", _arg(0, "masked_eq", _INT_MASK, family)) for family in _DENIED_SOCKET_FAMILIES]
    rules.append(_rule("socket", _arg(1, "masked_eq", _SOCK_TYPE_MASK, _SOCK_RAW)))
    # A datagram socketpair can send to any named Unix socket; stream pairs cannot.
    # AF_UNIX accepts SOCK_RAW as a SOCK_DGRAM alias, so deny both type values.
    for sock_type in (_SOCK_DGRAM, _SOCK_RAW):
        rules.append(_rule("socketpair", _arg(1, "masked_eq", _SOCK_TYPE_MASK, sock_type)))
    rules += [_rule("ioctl", _arg(1, "masked_eq", _INT_MASK, request)) for request in _DENIED_TTY_IOCTLS]
    # An empty-path execveat executes a descriptor, which no Landlock path rule covers.
    rules.append(_rule("execveat", _arg(4, "masked_eq", _AT_EMPTY_PATH, _AT_EMPTY_PATH)))
    return rules


def _grants(request: ExecutionRequest, output_dir: Path) -> list[dict[str, str]]:
    """The Landlock grants; ``/tmp`` here is the sandbox's private tmpfs."""
    grants = [{"path": path, "access": "read_exec"} for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64")]
    grants += [
        {"path": "/etc", "access": "read"},
        {"path": "/proc", "access": "read"},
        {"path": "/dev", "access": "device"},
        {"path": SANDBOX_TMP, "access": "write"},
        {"path": str(output_dir), "access": "write"},
    ]
    if request.input_dir is not None:
        grants.append({"path": INPUT_IN_SANDBOX, "access": "read_exec"})
    return grants


def _limits(request: ExecutionRequest) -> dict[str, int]:
    """The resource limits; a core dump is always off."""
    limits = {"core_bytes": 0, "open_files": _OPEN_FILES}
    if request.limits.cpu_seconds is not None:
        limits["cpu_seconds"] = request.limits.cpu_seconds
    if request.limits.max_file_mb is not None:
        limits["file_bytes"] = request.limits.max_file_mb * _MEBIBYTE
    if request.limits.address_space_mb is not None:
        limits["address_space_bytes"] = request.limits.address_space_mb * _MEBIBYTE
    return limits


def launcher_policy(request: ExecutionRequest, output_dir: Path) -> dict[str, object]:
    """Build the document that the launcher applies before it executes the target."""
    return {
        "schema_version": LAUNCHER_POLICY_SCHEMA,
        "environment": {**_BASE_ENVIRONMENT, **request.env},
        "limits": _limits(request),
        "landlock": _grants(request, output_dir),
        "seccomp": seccomp_rules(),
    }
