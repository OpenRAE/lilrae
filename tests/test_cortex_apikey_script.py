"""Behavioral tests for the Cortex API key seed script against a simulated Cortex."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORTEX_APIKEY_SCRIPT = PROJECT_ROOT / "scripts" / "cortex-apikey.sh"
ADMINISTRATOR = "admin@example.test"
ADMINISTRATOR_SECRET = "declared-administrator-test-secret"
INITIALIZER_KEY = "initializer-test-key"
CONNECTOR_KEY = "connector-test-key"

# The seed reaches Cortex through `docker exec`, so `docker` is replaced by a
# small Cortex 3 simulation. Its one rule that matters here: Cortex answers
# anonymous user-index requests only while no user exists ("Use of initial user
# is forbidden because users exist in database").
FAKE_CORTEX = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import sys

root = pathlib.Path(os.environ["FAKE_CORTEX_ROOT"])
state_path = root / "state.json"
state = json.loads(state_path.read_text())


def save():
    state_path.write_text(json.dumps(state))


def host_path(container_path):
    return root / "container" / container_path.lstrip("/")


args = sys.argv[1:]
if args[:1] != ["exec"]:
    sys.exit(0)
args = args[1:]
if args[:1] == ["-i"]:
    args = args[1:]
command = args[1:]
if command[:1] == ["mktemp"]:
    path = command[1].replace("XXXXXXXX", "session1")
    host_path(path).parent.mkdir(parents=True, exist_ok=True)
    host_path(path).write_text("")
    print(path)
    sys.exit(0)
if command[:1] == ["cat"]:
    sys.stdout.write(host_path(command[1]).read_text())
    sys.exit(0)
if command[:1] == ["rm"]:
    sys.exit(0)

config = {"header": []}
for line in sys.stdin.read().splitlines():
    key, sep, value = line.partition(" = ")
    if not sep:
        config[line.strip()] = True
    elif key == "header":
        config["header"].append(json.loads(value))
    else:
        config[key] = json.loads(value)
method = config.get("request", "POST" if "data" in config else "GET")
path = config["url"].split("://", 1)[1].split("/", 1)[1]
path = "/" + path
bearer = next(
    (h.split("Bearer ", 1)[1] for h in config["header"] if h.startswith("Authorization: Bearer ")),
    None,
)
cookie = config.get("cookie")
jar = host_path(cookie) if cookie else None
session = jar is not None and jar.exists() and "LOGGED-IN" in jar.read_text()
anonymous_open = not state["users"]
caller = {u: v for u, v in state["users"].items() if bearer and v.get("key") == bearer}
identity = next(iter(caller), None)
if session:
    identity = state["session_user"]
mode = "session" if session else ("key" if bearer else "anonymous")
with (root / "calls.log").open("a") as log:
    log.write(f"{method} {path} {mode}\n")


def reply(status, body=None):
    if status >= 400:
        sys.exit(22)
    if body is not None:
        print(json.dumps(body))
    sys.exit(0)


if path == "/api/status":
    reply(200, {"versions": {"Cortex": "3.1.8"}})
if path == "/api/maintenance/migrate":
    state["migrated"] = True
    save()
    reply(204)
if path == "/api/login" and method == "POST":
    login = json.loads(config["data"])
    user = state["users"].get(login["user"])
    if not user or user.get("password") != login["password"]:
        reply(401)
    jar = host_path(config["cookie-jar"])
    jar.write_text("# Netscape HTTP Cookie File\nLOGGED-IN\n" + "\t".join(
        ["localhost", "FALSE", "/", "FALSE", "0", "CORTEX-XSRF-TOKEN", "xsrf-token"]) + "\n")
    state["session_user"] = login["user"]
    save()
    reply(200, {"id": login["user"]})
if bearer and identity is None:
    reply(401)  # an unknown API key is refused, even while the init window is open
if path == "/api/user/current":
    if identity is None:
        reply(401)
    user = state["users"].get(identity, {})
    reply(200, {"_id": identity, "roles": user.get("roles", [])})
if path == "/api/user" and method == "GET":
    reply(200 if (anonymous_open or session or identity) else 400, list(state["users"]))
if path == "/api/organization" and method == "POST":
    if not (anonymous_open or session):
        reply(401)
    state["organizations"].append(json.loads(config["data"])["name"])
    save()
    reply(201, {})
if path == "/api/user" and method == "POST":
    if not (anonymous_open or session or identity):
        reply(401)
    created = json.loads(config["data"])
    state["users"][created["login"]] = {"key": created.get("key"), "roles": created["roles"]}
    save()
    reply(201, {})
if path.startswith("/api/user/") and method == "GET":
    exists = path.endswith("thehive%40cortex.local") and "thehive@cortex.local" in state["users"]
    reply(200 if exists else 404, {})
if path == "/api/analyzerdefinition/scan":
    reply(204)
if path == "/api/analyzerdefinition":
    reply(200, [{"id": "TechVaultScenarioContext_1_0"}])
if path.startswith("/api/organization/analyzer/"):
    state["analyzer"] = True
    save()
    reply(201, {})
if path == "/api/analyzer":
    if identity is None:
        reply(401)
    enabled = [{"analyzerDefinitionId": "TechVaultScenarioContext_1_0"}]
    reply(200, enabled if state.get("analyzer") else [])
reply(404)
'''


def _run_seed(
    tmp_path: Path, *, existing_administrator: bool, secret: str | None
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run the real seed script against the simulated Cortex."""

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text(FAKE_CORTEX, encoding="utf-8")
    (fake_bin / "docker").chmod(0o755)
    # The seed polls with `sleep`; the simulation answers at once.
    (fake_bin / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "sleep").chmod(0o755)
    users = {}
    if existing_administrator:
        users[ADMINISTRATOR] = {"password": ADMINISTRATOR_SECRET, "roles": ["superadmin"]}
    (tmp_path / "state.json").write_text(
        json.dumps({"users": users, "organizations": [], "migrated": existing_administrator}),
        encoding="utf-8",
    )
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "initializer").write_text(INITIALIZER_KEY + "\n", encoding="utf-8")
    (keys / "connector").write_text(CONNECTOR_KEY + "\n", encoding="utf-8")
    env = {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_CORTEX_ROOT": str(tmp_path),
        "CORTEX_CONTAINER": "cortex-under-test",
        "CORTEX_INITIALIZER_KEY_FILE": str(keys / "initializer"),
        "CORTEX_CONNECTOR_KEY_FILE": str(keys / "connector"),
    }
    if secret is not None:
        env["CORTEX_SUPERADMIN_USER"] = ADMINISTRATOR
        env["CORTEX_SUPERADMIN_PASSWORD"] = secret
    result = subprocess.run(
        [str(CORTEX_APIKEY_SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    calls_log = tmp_path / "calls.log"
    calls = calls_log.read_text(encoding="utf-8").splitlines() if calls_log.exists() else []
    return result, calls


def test_seed_uses_the_declared_administrator_session_when_it_already_exists(tmp_path):
    """A backend that created the declared administrator closed Cortex's anonymous access."""

    result, calls = _run_seed(tmp_path, existing_administrator=True, secret=ADMINISTRATOR_SECRET)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == CONNECTOR_KEY
    assert "did not become ready" not in result.stderr
    assert "GET /api/user/current session" in calls
    assert "POST /api/organization session" in calls
    assert "POST /api/user session" in calls


def test_seed_keeps_the_anonymous_first_run_path_on_a_fresh_cortex(tmp_path):
    """Without a declared administrator, the first-run window is used anonymously."""

    result, calls = _run_seed(tmp_path, existing_administrator=False, secret=None)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == CONNECTOR_KEY
    assert "GET /api/user anonymous" in calls
    assert "POST /api/organization anonymous" in calls
    assert not any(call.endswith(" session") for call in calls)


def test_seed_refuses_when_the_declared_administrator_cannot_sign_in(tmp_path):
    """A declared administrator whose credential does not work fails with its own reason."""

    result, calls = _run_seed(tmp_path, existing_administrator=True, secret="wrong-test-secret")

    assert result.returncode != 0
    assert "The declared Cortex administrator could not sign in" in result.stderr
    assert "POST /api/organization session" not in calls
    assert result.stdout.strip() == ""
