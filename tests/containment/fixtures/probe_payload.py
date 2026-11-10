"""Escape-probe payload for the containment proof.

Run with the system Python 3: ``python3 -I probe_payload.py <probe-id> [args]``.
Each probe prints ``LILRAE-PROBE reached <probe-id>`` before its operation and
``LILRAE-PROBE result <probe-id> <denied|allowed> <detail>`` after it. The
``detached-descendant`` probe prints only the reached marker; the harness
observes its heartbeat instead.
"""

import ctypes
import errno
import os
import platform
import socket
import stat
import sys
import time

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


def _keyctl():
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
    for name in os.listdir("/proc/self/fd"):
        descriptor = int(name)
        if descriptor <= 2:
            continue
        try:
            mode = os.fstat(descriptor).st_mode
            target = os.readlink(f"/proc/self/fd/{descriptor}")
        except OSError:
            continue
        if stat.S_ISREG(mode) or stat.S_ISSOCK(mode):
            found.append(f"fd{descriptor}:{stat.S_IFMT(mode):o}:{target}".replace(" ", "_"))
    if found:
        _DETAIL.append(",".join(found))
    return bool(found)


def _environment(name):
    return name in os.environ


def _heartbeat(path, seconds):
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
        time.sleep(0.05)
    os._exit(0)


def _detached(probe_id, path, seconds):
    _emit("reached", probe_id)
    child = os.fork()
    if child == 0:
        _heartbeat(path, seconds)
    os.waitpid(child, 0)


PROBES = {
    "host-file-read": _read_file,
    "host-file-write": _create_file,
    "input-write": _create_file,
    "host-process-environ": _read_environ,
    "host-process-signal": _signal,
    "host-loopback-connect": _tcp_connect,
    "host-unix-socket-connect": _unix_connect,
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
