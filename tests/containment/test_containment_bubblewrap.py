"""Bubblewrap arguments, status parsing, and the launcher status protocol."""

from pathlib import Path

from aptl.containment.bubblewrap import (
    INPUT_IN_SANDBOX,
    LAUNCHER_IN_SANDBOX,
    POLICY_IN_SANDBOX,
    REQUIRED_NAMESPACES,
    SandboxLayout,
    parse_status,
    parse_version,
    probe_arguments,
    run_arguments,
)
from aptl.containment.launch_status import LAYERS, parse_launch_status


def _layout(tmp_path: Path, input_dir: Path | None) -> SandboxLayout:
    return SandboxLayout(tmp_path / "launcher.py", tmp_path / "policy.json", tmp_path / "output", input_dir)


def _pairs(argv: tuple[str, ...], flag: str) -> list[tuple[str, str]]:
    return [(argv[i + 1], argv[i + 2]) for i, word in enumerate(argv) if word == flag]


def test_run_arguments_isolate_and_bind_only_the_grants(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    argv = run_arguments(
        Path("/usr/bin/bwrap"), _layout(tmp_path, input_dir), status_fd=7, json_fd=9,
        argv=("/usr/bin/python3", "-c", "1"),
    )

    separator = argv.index("--")
    options = argv[:separator]
    for flag in ("--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent",
                 "--new-session", "--clearenv", "--proc", "--dev"):
        assert flag in options
    assert options[options.index("--cap-drop") + 1] == "ALL"
    assert options.index("--tmpfs") < options.index("--bind")
    # The input sits outside every writable grant; its host path links to it.
    assert (str(input_dir), INPUT_IN_SANDBOX) in _pairs(options, "--ro-bind")
    assert (INPUT_IN_SANDBOX, str(input_dir)) in _pairs(options, "--symlink")
    assert _pairs(options, "--bind") == [(str(tmp_path / "output"), str(tmp_path / "output"))]
    assert (str(tmp_path / "launcher.py"), LAUNCHER_IN_SANDBOX) in _pairs(options, "--ro-bind")
    assert (str(tmp_path / "policy.json"), POLICY_IN_SANDBOX) in _pairs(options, "--ro-bind")
    assert options[options.index("--json-status-fd") + 1] == "9"
    assert options[options.index("--chdir") + 1] == str(tmp_path / "output")
    assert "--setenv" not in options
    assert argv[separator + 1:] == (
        "/usr/bin/python3", "-I", "-S", LAUNCHER_IN_SANDBOX, "7", POLICY_IN_SANDBOX,
        "--", "/usr/bin/python3", "-c", "1",
    )


def test_run_arguments_without_input_bind_no_input(tmp_path: Path) -> None:
    argv = run_arguments(Path("/usr/bin/bwrap"), _layout(tmp_path, None), status_fd=3, json_fd=4, argv=("/bin/true",))

    bound = {source for source, _ in _pairs(argv, "--ro-bind")}
    assert str(tmp_path / "input") not in bound


def test_probe_arguments_use_the_same_isolation() -> None:
    argv = probe_arguments(Path("/usr/bin/bwrap"))

    assert argv[0] == "/usr/bin/bwrap"
    assert "--disable-userns" in argv
    assert argv[-2:] == ("--", "/usr/bin/true")


def test_parse_status_reads_namespaces_and_exit() -> None:
    data = (
        b'{ "child-pid": 42, "pid-namespace": 1, "mnt-namespace": 2, "net-namespace": 3,'
        b' "ipc-namespace": 4, "uts-namespace": 5, "cgroup-namespace": 6 }\n'
        b"not json\n[1]\n"
        b'{ "exit-code": 3 }\n'
    )

    status = parse_status(data)

    assert status.child_started is True
    assert REQUIRED_NAMESPACES <= status.namespaces
    assert status.exit_code == 3


def test_parse_status_without_a_child_has_no_evidence() -> None:
    status = parse_status(b"")

    assert (status.child_started, status.namespaces, status.exit_code) == (False, frozenset(), None)


def test_parse_version() -> None:
    assert parse_version(b"bubblewrap 0.9.0\n") == (0, 9, 0)
    assert parse_version(b"something else") is None
    assert parse_version(b"bubblewrap x.y") is None


def _status(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode()


def test_launch_status_requires_every_layer_before_exec() -> None:
    complete = parse_launch_status(_status(*(f"ok {layer} detail" for layer in LAYERS), "exec"))
    partial = parse_launch_status(_status("ok descriptors", "exec"))

    assert complete.executed is True and set(complete.applied) == set(LAYERS)
    assert partial.executed is False


def test_launch_status_failure_wins_over_exec() -> None:
    status = parse_launch_status(_status(*(f"ok {layer}" for layer in LAYERS), "exec", "fail exec ENOENT", "fail other x"))

    assert status.executed is False
    assert status.failure == ("exec", "ENOENT")


def test_launch_status_ignores_unknown_lines() -> None:
    status = parse_launch_status(b"ok unknown x\nexec extra\nnoise\n")

    assert status.applied == {}
    assert status.executed is False
    assert status.failure is None


def test_the_system_view_binds_public_tls_material_only(tmp_path: Path) -> None:
    argv = run_arguments(Path("/usr/bin/bwrap"), _layout(tmp_path, None), status_fd=3, json_fd=4, argv=("/bin/true",))

    bound = {source for source, _ in _pairs(argv, "--ro-bind")}
    assert "/etc/ssl" not in bound
    assert not any(path.startswith("/etc/ssl/private") for path in bound)
    if Path("/etc/ssl/certs").exists():
        assert "/etc/ssl/certs" in bound
