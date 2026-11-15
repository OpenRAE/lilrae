"""Escape-probe payload for the containment proof.

Run with the system Python 3: ``python3 -I probe_payload.py <probe-id> [args]``.
Each probe prints ``LILRAE-PROBE reached <probe-id>`` before its operation and
``LILRAE-PROBE result <probe-id> <denied|allowed> <detail>`` after it. The
``detached-descendant`` probe prints only the reached marker; the harness
observes its heartbeat instead.
"""

import os


def _descriptor_table():
    """Describe each open descriptor above 2; the listing's own is closed by then."""
    table = []
    for name in sorted(os.listdir("/proc/self/fd"), key=int):
        descriptor = int(name)
        if descriptor <= 2:
            continue
        try:
            mode = os.fstat(descriptor).st_mode
            target = os.readlink(f"/proc/self/fd/{descriptor}")
        except OSError:
            continue
        table.append((descriptor, mode, target))
    return table


# Read the descriptor table as the payload inherited it at exec, before any
# import can open a file of its own. Inside the engine's seccomp filter, for
# example, libffi keeps its own library open when memfd_create is denied.
_INHERITED_DESCRIPTORS = _descriptor_table()

import errno  # noqa: E402
import socket  # noqa: E402
import stat  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

_KEYCTL = {"x86_64": 250, "aarch64": 219}
_KEYCTL_GET_KEYRING_ID = 0
_KEY_SPEC_PROCESS_KEYRING = -2


_DETAIL = []


def _emit(kind, probe_id, *fields):
    print("LILRAE-PROBE", kind, probe_id, *fields, flush=True)


def _read_file(path, canary):
    with open(path, encoding="utf-8") as stream:
        return stream.read() == canary


def _create_file(directory):
    path = os.path.join(directory, f"escape-{os.getpid()}")
    with open(path, "x", encoding="utf-8") as stream:
        stream.write("escape")
    return True


def _read_environ(pid, canary):
    with open(f"/proc/{pid}/environ", "rb") as stream:
        return canary.encode() in stream.read()


def _signal(pid):
    os.kill(int(pid), 0)
    return True


def _tcp_connect(port):
    with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
        return True


def _unix_connect(address):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(address)
    return True


_SOCKET = {"x86_64": 41, "aarch64": 198}


def _raw_domain_connect(path):
    """socket(2) with upper domain bits set; the kernel reads only the low 32 bits."""
    import ctypes
    import platform

    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.syscall(_SOCKET[platform.machine()], ctypes.c_long(0x100000001), 1, 0)
    if fd < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    with socket.socket(fileno=fd) as client:
        client.settimeout(2)
        client.connect(path)
    return True


def _dgram_pair_send(path, sock_type=socket.SOCK_DGRAM):
    """A datagram socketpair can name another destination in sendto(2)."""
    first, second = socket.socketpair(socket.AF_UNIX, sock_type)
    with first, second:
        first.sendto(b"probe", path)
    return True


def _raw_pair_send(path):
    """AF_UNIX accepts SOCK_RAW as an alias for SOCK_DGRAM."""
    return _dgram_pair_send(path, socket.SOCK_RAW)


def _fifo_write(path):
    """Opening a FIFO for writing reaches its host reader without changing the filesystem."""
    fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, b"probe")
    finally:
        os.close(fd)
    return True


def _keyctl():
    import ctypes
    import platform

    libc = ctypes.CDLL(None, use_errno=True)
    number = _KEYCTL[platform.machine()]
    if libc.syscall(number, _KEYCTL_GET_KEYRING_ID, _KEY_SPEC_PROCESS_KEYRING, 1) < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return True


def _unshare_user():
    os.unshare(os.CLONE_NEWUSER)
    return True


def _inherited_descriptor():
    found = []
    for descriptor, mode, target in _INHERITED_DESCRIPTORS:
        if stat.S_ISREG(mode) or stat.S_ISSOCK(mode):
            found.append(f"fd{descriptor}:{stat.S_IFMT(mode):o}:{target}".replace(" ", "_"))
    if found:
        _DETAIL.append(",".join(found))
    return bool(found)


def _environment(name):
    return name in os.environ


def _heartbeat(path, seconds, ready):
    os.setsid()
    if os.fork():
        os._exit(0)
    for descriptor in (0, 1, 2):
        os.close(descriptor)
    with open(f"{path}.pid", "w", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    ends = time.monotonic() + float(seconds)
    while time.monotonic() < ends:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(".")
        if ready is not None:
            os.write(ready, b"r")
            os.close(ready)
            ready = None
        time.sleep(0.05)
    os._exit(0)


def _detached(probe_id, path, seconds):
    """End only after the detached grandchild has written its first heartbeat."""
    import select

    _emit("reached", probe_id)
    read_end, write_end = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_end)
        _heartbeat(path, seconds, write_end)
    os.close(write_end)
    os.waitpid(child, 0)
    select.select([read_end], [], [], 5.0)
    os.close(read_end)


PROBES = {
    "host-file-read": _read_file,
    "host-file-write": _create_file,
    "input-write": _create_file,
    "host-process-environ": _read_environ,
    "host-process-signal": _signal,
    "host-loopback-connect": _tcp_connect,
    "host-unix-socket-connect": _unix_connect,
    "input-unix-socket-connect": _unix_connect,
    "raw-domain-unix-connect": _raw_domain_connect,
    "input-unix-dgram-send": _dgram_pair_send,
    "input-unix-raw-pair-send": _raw_pair_send,
    "input-fifo-write": _fifo_write,
    "abstract-unix-socket-connect": lambda name: _unix_connect("\0" + name),
    "keyctl-syscall": _keyctl,
    "nested-user-namespace": _unshare_user,
    "inherited-descriptor": _inherited_descriptor,
    "environment-canary": _environment,
}


def main(probe_id, *arguments):
    if probe_id == "detached-descendant":
        _detached(probe_id, *arguments)
        return 0
    _emit("reached", probe_id)
    try:
        allowed = PROBES[probe_id](*arguments)
        detail = (_DETAIL[0] if _DETAIL else "ok") if allowed else "absent"
    except OSError as exc:
        allowed, detail = False, errno.errorcode.get(exc.errno, str(exc.errno))
    _emit("result", probe_id, "allowed" if allowed else "denied", detail)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
