"""The launcher policy: environment, Landlock grants, seccomp rules, limits."""

from pathlib import Path

import pytest

from aptl.containment.policy import (
    LAUNCHER_POLICY_SCHEMA,
    denied_environment_names,
    launcher_policy,
    seccomp_rules,
)
from aptl.core.containment import REQUEST_SCHEMA, ExecutionLimits, ExecutionRequest


def _request(env: dict[str, str] | None = None, input_dir: Path | None = None, **limits: int) -> ExecutionRequest:
    return ExecutionRequest(
        schema_version=REQUEST_SCHEMA,
        profile="linux-full",
        label="policy",
        argv=("/usr/bin/true",),
        env=env or {},
        stdin=b"",
        input_dir=input_dir,
        limits=ExecutionLimits(deadline_seconds=5, max_output_bytes=64, **limits),
        network="none",
    )


@pytest.mark.parametrize(
    "name",
    ["LD_PRELOAD", "LD_ANYTHING", "DYLD_INSERT_LIBRARIES", "PYTHONPATH", "PYTHONWHATEVER",
     "HTTPS_PROXY", "no_proxy", "BASH_ENV", "NODE_OPTIONS", "GIT_EXEC_PATH", "SSLKEYLOGFILE",
     "TMPDIR", "HOME", "PATH"],
)
def test_loader_config_proxy_and_fixed_names_are_denied(name: str) -> None:
    assert denied_environment_names({name: "x"}) == (name,)


def test_ordinary_names_are_allowed() -> None:
    assert denied_environment_names({"FIXTURE_MODE": "proof", "LANG_OVERRIDE": "x"}) == ()


def test_seccomp_rules_deny_the_escape_surface() -> None:
    rules = seccomp_rules()
    plain = {rule["syscall"] for rule in rules if not rule["args"]}
    assert {"keyctl", "bpf", "ptrace", "unshare", "setns", "mount", "io_uring_setup",
            "userfaultfd", "perf_event_open", "memfd_create"} <= plain
    clone3 = next(rule for rule in rules if rule["syscall"] == "clone3")
    assert clone3["errno"] == 38
    clone_flags = {rule["args"][0]["a"] for rule in rules if rule["syscall"] == "clone"}
    assert 0x10000000 in clone_flags
    assert 0x20000000 in clone_flags
    # The kernel reads the domain as a 32-bit int, so the rule masks the upper bits.
    socket_families = {
        rule["args"][0]["b"] for rule in rules
        if rule["syscall"] == "socket" and rule["args"][0]["arg"] == 0
        and rule["args"][0] == {"arg": 0, "op": "masked_eq", "a": 0xFFFFFFFF, "b": rule["args"][0]["b"]}
    }
    assert {1, 15, 17, 38, 40} <= socket_families  # AF_UNIX: no host Unix socket is reachable
    assert not any(rule["syscall"] == "socket" and rule["args"][0]["op"] == "eq" for rule in rules)
    assert "socketpair" not in plain
    # SOCK_RAW is an AF_UNIX alias for SOCK_DGRAM, so both datagram spellings are denied.
    for sock_type in (2, 3):
        assert {"syscall": "socketpair", "errno": 1, "args": [{"arg": 1, "op": "masked_eq", "a": 0xF, "b": sock_type}]} in rules
    assert any(
        rule["syscall"] == "execveat" and rule["args"][0] == {"arg": 4, "op": "masked_eq", "a": 0x1000, "b": 0x1000}
        for rule in rules
    )


def test_policy_grants_input_read_output_write_and_carries_env(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    policy = launcher_policy(
        _request(env={"FIXTURE_MODE": "proof"}, input_dir=input_dir, cpu_seconds=7, max_file_mb=2, address_space_mb=64),
        output_dir,
    )

    assert policy["schema_version"] == LAUNCHER_POLICY_SCHEMA
    grants = {grant["path"]: grant["access"] for grant in policy["landlock"]}
    assert grants["/run/lilrae/input"] == "read_exec"
    assert str(input_dir) not in grants
    assert grants[str(output_dir)] == "write"
    assert grants["/tmp"] == "write"
    assert grants["/usr"] == "read_exec"
    assert policy["environment"] == {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/tmp/home", "FIXTURE_MODE": "proof",
    }
    assert policy["limits"] == {
        "core_bytes": 0, "open_files": 4096, "cpu_seconds": 7,
        "file_bytes": 2 * 1024 * 1024, "address_space_bytes": 64 * 1024 * 1024,
    }
    assert policy["seccomp"] == seccomp_rules()


def test_policy_without_input_grants_no_input(tmp_path: Path) -> None:
    policy = launcher_policy(_request(), tmp_path / "output")

    assert all(grant["path"] != "/run/lilrae/input" for grant in policy["landlock"])
    assert policy["limits"] == {"core_bytes": 0, "open_files": 4096}
