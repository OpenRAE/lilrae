"""The in-sandbox launcher: each layer, its failure paths, and a real run."""

import ctypes
import errno
import json
import os
import subprocess
from pathlib import Path

import pytest

from aptl.containment import _launcher as launcher
from aptl.containment.launch_status import LAYERS, parse_launch_status
from aptl.containment.policy import launcher_policy
from aptl.core.containment import REQUEST_SCHEMA, ExecutionLimits, ExecutionRequest

LAUNCHER = Path(launcher.__file__)


def _pipe_status() -> tuple[launcher.Status, int]:
    read_end, write_end = os.pipe()
    return launcher.Status(write_end), read_end


def _read(fd: int) -> bytes:
    os.set_blocking(fd, False)
    try:
        return os.read(fd, 65536)
    except BlockingIOError:
        return b""


def test_status_lines_follow_the_protocol() -> None:
    status, read_end = _pipe_status()

    status.ok("landlock", "abi=4")
    status.fail("seccomp", "bad\nrule")
    status.write("exec")

    assert _read(read_end) == b"ok landlock abi=4\nfail seccomp bad rule\nexec\n"


def test_landlock_rights_grow_with_the_abi() -> None:
    assert launcher._fs_rights(1) == (1 << 13) - 1
    assert launcher._fs_rights(3) & (1 << 14)
    assert not launcher._fs_rights(4) & (1 << 15)
    assert launcher._fs_rights(5) & (1 << 15)
    handled = launcher._fs_rights(1)
    assert launcher._grant_mask("read", handled) == (1 << 2) | (1 << 3)
    assert launcher._grant_mask("write", handled) == handled
    assert launcher._grant_mask("read_exec", handled) & 1


def test_limits_apply_each_value_and_refuse_unknown_names(monkeypatch: pytest.MonkeyPatch) -> None:
    applied: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(launcher.resource, "setrlimit", lambda kind, value: applied.append((kind, value)))

    launcher.set_limits({"core_bytes": 0, "cpu_seconds": 3})

    assert applied == [(launcher.resource.RLIMIT_CORE, (0, 0)), (launcher.resource.RLIMIT_CPU, (3, 3))]
    with pytest.raises(launcher.LayerError, match="limits"):
        launcher.set_limits({"unknown": 1})


def test_close_descriptors_keeps_only_the_status_descriptor(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[int] = []
    monkeypatch.setattr(launcher.os, "listdir", lambda path: ["0", "1", "2", "3", "5", "9"])
    monkeypatch.setattr(launcher.os, "close", closed.append)

    assert launcher.close_descriptors(5) == 2
    assert closed == [3, 9]


def test_close_descriptors_refuses_without_a_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(path: str) -> list[str]:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(launcher.os, "listdir", denied)

    with pytest.raises(launcher.LayerError, match="descriptors"):
        launcher.close_descriptors(5)


class _FakeLibc:
    def __init__(self, abi: int, fail: int | None = None) -> None:
        self.abi = abi
        self.fail = fail
        self.calls: list[int] = []

    def syscall(self, number: int, *args: object) -> int:
        self.calls.append(number)
        if number == self.fail:
            ctypes.set_errno(errno.EINVAL)
            return -1
        if number == 444 and args[0] is None:
            return self.abi
        if number == 444:
            return os.open("/dev/null", os.O_RDONLY)
        return 0

    def prctl(self, *args: object) -> int:
        return 0


def test_landlock_adds_existing_grants_and_restricts(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("x")
    libc = _FakeLibc(abi=4)
    grants = [
        {"path": str(tmp_path), "access": "write"},
        {"path": str(tmp_path / "file"), "access": "read"},
        {"path": str(tmp_path / "absent"), "access": "read"},
    ]

    assert launcher.apply_landlock(libc, grants) == 4  # type: ignore[arg-type]
    assert libc.calls.count(445) == 2
    assert libc.calls[-1] == 446


@pytest.mark.parametrize("failing", [445, 446])
def test_landlock_failure_is_a_layer_error(tmp_path: Path, failing: int) -> None:
    libc = _FakeLibc(abi=1, fail=failing)
    grants = [{"path": str(tmp_path), "access": "read"}]
    with pytest.raises(launcher.LayerError, match="landlock"):
        launcher.apply_landlock(libc, grants)  # type: ignore[arg-type]


class _FakeSeccomp:
    def __init__(self, *, init: int = 1, add: int = 0, load: int = 0) -> None:
        self.init, self.add, self.load = init, add, load
        self.rules: list[tuple[int, int, int]] = []
        self.released = False

    def seccomp_init(self, action: int) -> int:
        return self.init

    def seccomp_syscall_resolve_name(self, name: bytes) -> int:
        return -1 if name == b"absent" else len(name)

    def seccomp_rule_add_array(self, context: int, action: int, number: int, count: int, array: object) -> int:
        self.rules.append((action, number, count))
        return self.add

    def seccomp_load(self, context: int) -> int:
        return self.load

    def seccomp_release(self, context: int) -> None:
        self.released = True


def test_seccomp_adds_rules_that_resolve_and_loads() -> None:
    library = _FakeSeccomp()
    rules = [
        {"syscall": "keyctl", "errno": 1, "args": []},
        {"syscall": "absent", "errno": 1, "args": []},
        {"syscall": "socket", "errno": 1, "args": [{"arg": 0, "op": "eq", "a": 17, "b": 0}]},
    ]

    assert launcher.apply_seccomp(library, rules) == 2  # type: ignore[arg-type]
    assert library.rules == [(0x00050001, 6, 0), (0x00050001, 6, 1)]
    assert library.released


@pytest.mark.parametrize("library", [_FakeSeccomp(init=0), _FakeSeccomp(add=-1), _FakeSeccomp(load=-1)])
def test_seccomp_failures_are_layer_errors(library: _FakeSeccomp) -> None:
    with pytest.raises(launcher.LayerError, match="seccomp"):
        launcher.apply_seccomp(library, [{"syscall": "keyctl", "errno": 1, "args": []}])  # type: ignore[arg-type]


def test_libseccomp_loads_on_this_host() -> None:
    assert launcher.load_libseccomp().seccomp_init.restype is ctypes.c_void_p


def _policy_file(tmp_path: Path, policy: object) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    return path


def test_main_refuses_a_bad_policy_and_a_missing_target(tmp_path: Path) -> None:
    status, read_end = _pipe_status()

    assert launcher.main(["l", str(status.fd), str(tmp_path / "absent"), "--", "/bin/true"]) == 126
    assert launcher.main(["l", str(status.fd), str(_policy_file(tmp_path, {})), "--"]) == 126

    assert _read(read_end) == b"fail policy FileNotFoundError\nfail arguments no target command\n"


def test_main_reports_a_layer_failure_and_an_exec_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    status, read_end = _pipe_status()
    policy = str(_policy_file(tmp_path, {"environment": {}}))

    def broken(status: launcher.Status, policy: dict) -> None:
        raise launcher.LayerError("landlock", "EINVAL")

    monkeypatch.setattr(launcher, "apply_layers", broken)
    assert launcher.main(["l", str(status.fd), policy, "--", "/bin/true"]) == 126

    def no_exec(path: str, argv: list[str], env: dict[str, str]) -> None:
        raise FileNotFoundError(errno.ENOENT, "absent")

    monkeypatch.setattr(launcher, "apply_layers", lambda status, policy: None)
    monkeypatch.setattr(launcher.os, "execve", no_exec)
    assert launcher.main(["l", str(status.fd), policy, "--", "/absent"]) == 127

    assert _read(read_end) == b"fail landlock EINVAL\nexec\nfail exec ENOENT\n"


@pytest.mark.integration
@pytest.mark.containment
def test_launcher_layers_hold_without_bubblewrap(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    # Outside Bubblewrap the /tmp grant covers the host /tmp, so read a file
    # that no grant covers: this test file in the checkout.
    secret = Path(__file__)
    request = ExecutionRequest(
        schema_version=REQUEST_SCHEMA, profile="linux-full", label="launcher", argv=("/usr/bin/true",),
        env={"FIXTURE_MODE": "proof"}, stdin=b"", input_dir=None,
        limits=ExecutionLimits(deadline_seconds=5, max_output_bytes=64), network="none",
    )
    policy = _policy_file(tmp_path, launcher_policy(request, output))
    target = (
        "import ctypes, os, json\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "out = {'keyctl': libc.syscall(250, 0, -2, 1), 'fds': sorted(os.listdir('/proc/self/fd')),"
        " 'env': os.environ.get('FIXTURE_MODE')}\n"
        f"try: open({str(secret)!r}).read(); out['secret'] = 'read'\n"
        "except OSError as e: out['secret'] = e.errno\n"
        "try: os.unshare(os.CLONE_NEWUSER); out['unshare'] = 'ok'\n"
        "except OSError as e: out['unshare'] = e.errno\n"
        f"open({str(output / 'written')!r}, 'w').write('ok')\n"
        "print(json.dumps(out))\n"
    )
    read_end, write_end = os.pipe()
    stray = os.open(secret, os.O_RDONLY)
    completed = subprocess.run(
        ["/usr/bin/python3", "-I", "-S", str(LAUNCHER), str(write_end), str(policy), "--",
         "/usr/bin/python3", "-I", "-c", target],
        capture_output=True, timeout=30, check=False, pass_fds=(write_end, stray),
    )
    os.close(write_end)
    os.close(stray)
    status = parse_launch_status(_read(read_end))

    assert completed.returncode == 0, completed.stderr
    assert status.executed
    assert set(status.applied) == set(LAYERS)
    observed = json.loads(completed.stdout)
    assert observed["keyctl"] == -1
    assert observed["secret"] == errno.EACCES
    assert observed["unshare"] == errno.EPERM
    assert observed["env"] == "proof"
    assert str(stray) not in observed["fds"]
    assert str(write_end) not in observed["fds"]
    assert (output / "written").read_text() == "ok"
