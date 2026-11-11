"""Behavioral tests for the manual Wazuh active-response test scripts (#1356).

``scripts/test-wazuh-ar-drop.sh`` and ``scripts/test-wazuh-ar-whitelist.sh``
are the SIEM-006 end-to-end checks. They need a running lab, so these tests
drive them against a stub ``docker`` on ``PATH`` and check that each verdict
comes from the current run: a blocked request counts as blocked, and a log
line or an iptables drop left by an earlier run satisfies nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DROP_SCRIPT = PROJECT_ROOT / "scripts" / "test-wazuh-ar-drop.sh"
WHITELIST_SCRIPT = PROJECT_ROOT / "scripts" / "test-wazuh-ar-whitelist.sh"
REAL_WRAPPER = PROJECT_ROOT / "containers" / "_wazuh-agent" / "aptl-firewall-drop.sh"
KALI_IP = "172.20.4.30"
STALE_STAMP = "2026-10-01T00:00:00+00:00 aptl-firewall-drop:"

# The drop script's view of the lab. Each call is appended to STUB_STATE/calls.
# The kali drop is the file STUB_STATE/drop. STUB_BLOCKED says what a request
# from kali does while that drop exists: "timeout" and "refused" make curl
# print 000 and exit 28 or 7, as the real curl does, and "http" means the drop
# does not enforce. STUB_AR_FIRES=1 installs the drop when the marker request
# reaches the webapp. STUB_WEBAPP_DOWN is "always" or "after-ar".
_DROP_DOCKER = """
import os
import pathlib
import sys

state = pathlib.Path(os.environ["STUB_STATE"])
drop = state / "drop"
fired = state / "ar-fired"
args = sys.argv[1:]
with (state / "calls").open("a", encoding="utf-8") as calls:
    calls.write(" ".join(args) + "\\n")
if args[:1] == ["ps"]:
    print("aptl-wazuh-manager\\naptl-webapp\\naptl-kali")
    sys.exit(0)
if args[:1] != ["exec"]:
    sys.exit(0)
args = args[1:]
while args[0].startswith("-"):
    args = args[2:] if args[0] == "-e" else args[1:]
container, argv = args[0], args[1:]


def curl(url):
    blocked = os.environ.get("STUB_BLOCKED", "timeout")
    if drop.exists() and blocked != "http":
        return "000", 28 if blocked == "timeout" else 7
    down = os.environ.get("STUB_WEBAPP_DOWN", "")
    if down == "always" or (down == "after-ar" and fired.exists()):
        return "000", 28
    if "aptl-ar-test-marker" in url and os.environ.get("STUB_AR_FIRES") == "1":
        drop.touch()
        fired.touch()
        return "404", 0
    return "200", 0


if container == "aptl-kali" and argv[:1] == ["curl"]:
    code, rc = curl(argv[-1])
    sys.stdout.write(code)
    sys.exit(rc)
if container == "aptl-webapp" and argv[:2] == ["iptables", "-C"]:
    sys.exit(0 if drop.exists() else 1)
if container == "aptl-webapp" and argv[:1] == ["sh"] and "iptables -D" in argv[-1]:
    drop.unlink(missing_ok=True)
    sys.exit(0)
if container == "aptl-webapp" and argv[:2] == ["iptables", "-L"]:
    print("Chain INPUT (policy ACCEPT)")
    sys.exit(0)
if container == "aptl-wazuh-manager":
    sys.exit(0)
sys.stderr.write(f"unexpected docker call: {sys.argv[1:]}\\n")
sys.exit(99)
"""

# The whitelist script only reads files and runs the wrapper inside the target,
# so its stub runs each `docker exec` command on the host instead.
_LOCAL_DOCKER = """
import os
import sys

args = sys.argv[1:]
if args[:1] == ["ps"]:
    print("aptl-webapp")
    sys.exit(0)
args = args[1:]
while args[0].startswith("-"):
    args = args[2:] if args[0] == "-e" else args[1:]
os.execvp(args[1], args[1:])
"""

# A wrapper that answers like aptl-firewall-drop but can leave out the skip or
# the delete line (STUB_WRAPPER_OMIT) or log a longer address than it was given
# (STUB_WRAPPER_IP_SUFFIX).
_FAKE_WRAPPER = """
import json
import os
import sys

payload = json.load(sys.stdin)
command = payload["command"]
srcip = payload["parameters"]["alert"]["data"]["srcip"]
omit = os.environ.get("STUB_WRAPPER_OMIT", "")
logged = srcip + os.environ.get("STUB_WRAPPER_IP_SUFFIX", "")
line, rc = None, 0
if command == "add" and srcip == os.environ["KALI_IP"]:
    line = None if omit == "skip" else f"SKIPPED for whitelisted {logged}"
elif command == "add":
    rc = 1
elif omit != "removed":
    line = f"removed 0 DROP rule(s) for {logged}"
if line:
    with open(os.environ["LOG"], "a", encoding="utf-8") as log:
        log.write(f"2026-10-12T00:00:00+00:00 aptl-firewall-drop: {line}\\n")
sys.exit(rc)
"""


def _write_executable(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _run(script: Path, tmp_path: Path, docker_body: str, extra_env: dict[str, str]):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "docker", docker_body)
    # The drop script sleeps for minutes waiting on the manager; skip it.
    (fake_bin / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "sleep").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
    env.update(extra_env)
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=60,
    )


@pytest.mark.parametrize(
    ("lab", "expected_rc", "expected_line"),
    [
        pytest.param(
            {"STUB_BLOCKED": "timeout"},
            0,
            "follow-up correctly blocked (curl: 'TIMEOUT')",
            id="blocked-request-times-out",
        ),
        pytest.param(
            {"STUB_BLOCKED": "refused"},
            0,
            "follow-up correctly blocked (curl: 'TIMEOUT')",
            id="blocked-request-is-refused",
        ),
        pytest.param(
            {"STUB_BLOCKED": "http"},
            1,
            "FAIL: follow-up was NOT blocked: kali -> webapp/ returned HTTP 200.",
            id="drop-does-not-enforce",
        ),
        pytest.param(
            {"STUB_WEBAPP_DOWN": "always"},
            1,
            "FAIL: baseline failed: kali -> webapp returned 'TIMEOUT'.",
            id="webapp-down-before-test",
        ),
        pytest.param(
            {"STUB_WEBAPP_DOWN": "after-ar"},
            1,
            "FAIL: recovery failed: kali -> webapp returned 'TIMEOUT' AFTER cleanup.",
            id="webapp-down-after-cleanup",
        ),
        pytest.param(
            {"STUB_LEFTOVER_DROP": "1"},
            0,
            "PASS - in-process Wazuh agent on aptl-webapp successfully blocked kali",
            id="earlier-run-drop-is-cleared",
        ),
        pytest.param(
            {"STUB_LEFTOVER_DROP": "1", "STUB_AR_FIRES": "0"},
            1,
            f"FAIL: AR did not install a drop for {KALI_IP} within 2s.",
            id="earlier-run-drop-is-not-this-runs-ar",
        ),
    ],
)
def test_drop_script_judges_this_runs_requests_and_drop(
    tmp_path, lab, expected_rc, expected_line
):
    state = tmp_path / "state"
    state.mkdir()
    if lab.get("STUB_LEFTOVER_DROP") == "1":
        (state / "drop").touch()
    env = {
        "STUB_STATE": str(state),
        "STUB_AR_FIRES": "1",
        "WAIT_AR_SEC": "2",
        "WAIT_MGR_SEC": "0",
        **lab,
    }

    result = _run(DROP_SCRIPT, tmp_path, _DROP_DOCKER, env)

    assert result.returncode == expected_rc, result.stdout + result.stderr
    assert expected_line in result.stdout, result.stdout
    assert "unexpected docker call" not in result.stderr, result.stderr
    # The EXIT trap always removes the kali drop again.
    assert not (state / "drop").exists()


def _whitelist_env(
    tmp_path: Path, wrapper: Path, kali_ip: str, *, stale_lines: bool = True
) -> dict[str, str]:
    log = tmp_path / "active-responses.log"
    whitelist = tmp_path / "active-response-whitelist"
    whitelist.write_text(f"{kali_ip}\n", encoding="utf-8")
    if stale_lines:
        # Lines an earlier passing run left behind; the wrapper only appends.
        log.write_text(
            f"{STALE_STAMP} SKIPPED for whitelisted {kali_ip}\n"
            f"{STALE_STAMP} removed 0 DROP rule(s) for {kali_ip}\n",
            encoding="utf-8",
        )
    return {
        "WRAPPER": str(wrapper),
        "WHITELIST": str(whitelist),
        "LOG": str(log),
        "KALI_IP": kali_ip,
        # Read by the real wrapper, which the script runs through `env`.
        "APTL_AR_WHITELIST": str(whitelist),
        "APTL_AR_LOG": str(log),
    }


@pytest.mark.parametrize(
    ("stale_lines", "skip_lines"),
    [
        pytest.param(True, 2, id="log-has-earlier-runs"),
        pytest.param(False, 1, id="log-does-not-exist-yet"),
    ],
)
def test_whitelist_script_passes_against_the_real_wrapper(
    tmp_path, stale_lines, skip_lines
):
    env = _whitelist_env(tmp_path, REAL_WRAPPER, KALI_IP, stale_lines=stale_lines)

    result = _run(WHITELIST_SCRIPT, tmp_path, _LOCAL_DOCKER, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "all checks PASS" in result.stdout
    log_lines = Path(env["LOG"]).read_text(encoding="utf-8").splitlines()
    skipped = f"SKIPPED for whitelisted {KALI_IP}"
    assert sum(skipped in line for line in log_lines) == skip_lines


@pytest.mark.parametrize(
    ("kali_ip", "wrapper_env", "expected_line"),
    [
        pytest.param(
            KALI_IP,
            {"STUB_WRAPPER_OMIT": "skip"},
            f"FAIL: no 'SKIPPED for whitelisted {KALI_IP}' line",
            id="skip-not-logged",
        ),
        pytest.param(
            KALI_IP,
            {"STUB_WRAPPER_OMIT": "removed"},
            f"FAIL: no 'removed N DROP rule(s) for {KALI_IP}' line",
            id="delete-not-logged",
        ),
        pytest.param(
            "10.0.0.1",
            {"STUB_WRAPPER_IP_SUFFIX": "0"},
            "FAIL: no 'SKIPPED for whitelisted 10.0.0.1' line",
            id="longer-address-logged",
        ),
    ],
)
def test_whitelist_script_ignores_log_lines_from_earlier_runs(
    tmp_path, kali_ip, wrapper_env, expected_line
):
    wrapper = tmp_path / "fake-wrapper"
    _write_executable(wrapper, _FAKE_WRAPPER)
    env = {**_whitelist_env(tmp_path, wrapper, kali_ip), **wrapper_env}

    result = _run(WHITELIST_SCRIPT, tmp_path, _LOCAL_DOCKER, env)

    assert result.returncode == 1, result.stdout + result.stderr
    assert expected_line in result.stdout, result.stdout
