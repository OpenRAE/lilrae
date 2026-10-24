"""Credential discovery for participant-invoked SOC seed scripts."""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
HELPER = PROJECT_ROOT / "scripts" / "aptl-env.sh"


def _load_key(env_file: Path, key: str, *, existing: str = "") -> str:
    env = {
        **os.environ,
        "APTL_ENV_HELPER": str(HELPER),
        "APTL_TEST_ENV_FILE": str(env_file),
        "APTL_TEST_KEY": key,
    }
    if existing:
        env[key] = existing
    else:
        env.pop(key, None)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$APTL_ENV_HELPER"; '
            'aptl_load_env_key "$APTL_TEST_ENV_FILE" "$APTL_TEST_KEY"; '
            'printf "%s" "${!APTL_TEST_KEY}"',
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_loads_generated_key_from_project_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MISP_API_KEY=fresh-lab-key\n")

    assert _load_key(env_file, "MISP_API_KEY") == "fresh-lab-key"


def test_explicit_process_environment_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MISP_API_KEY=file-key\n")

    assert _load_key(env_file, "MISP_API_KEY", existing="operator-key") == (
        "operator-key"
    )


def test_env_value_is_not_evaluated(tmp_path):
    marker = tmp_path / "must-not-exist"
    literal = f"$(touch {marker})"
    env_file = tmp_path / ".env"
    env_file.write_text(f"MISP_API_KEY={literal}\n")

    assert _load_key(env_file, "MISP_API_KEY") == literal
    assert not marker.exists()


def test_manual_seed_entrypoints_load_their_required_credentials():
    expected = {
        "seed-prime.sh": ("MISP_API_KEY", "SHUFFLE_API_KEY"),
        "seed-misp.sh": ("MISP_API_KEY",),
        "seed-shuffle.sh": (
            "MISP_API_KEY",
            "SHUFFLE_API_KEY",
            "THEHIVE_API_KEY",
        ),
    }
    for name, keys in expected.items():
        text = (PROJECT_ROOT / "scripts" / name).read_text()
        assert 'source "$SCRIPT_DIR/aptl-env.sh"' in text
        for key in keys:
            assert key in text


def test_seeded_soar_case_preserves_exact_alert_id_and_mcp_uses_flat_argument():
    seed = (PROJECT_ROOT / "scripts" / "seed-shuffle.sh").read_text()
    assert r"Wazuh alert id \$exec.id; rule \$exec.rule.id" in seed

    config = json.loads(
        (PROJECT_ROOT / "mcp" / "mcp-soar" / "docker-lab-config.json").read_text()
    )
    description = config["queries"]["execute_workflow"]["description"]
    assert "body itself becomes the execution argument" in description
    assert '"execution_argument"' not in description


def test_thehive_seed_uses_declared_https_endpoint_and_mounted_ca():
    script = (PROJECT_ROOT / "scripts" / "thehive-apikey.sh").read_text()
    assert 'THEHIVE_URL="${THEHIVE_URL:-https://localhost:9000}"' in script
    assert (
        'THEHIVE_CA_CERT="${THEHIVE_CA_CERT:-/opt/techvault/soc-certs/lab-ca.pem}"'
        in script
    )
    assert 'curl --cacert "$THEHIVE_CA_CERT"' in script


@pytest.mark.parametrize("script_name", ["thehive-apikey.sh", "cortex-apikey.sh"])
def test_seed_credentials_never_enter_docker_exec_argv(tmp_path, script_name):
    fake = tmp_path / "bin"
    fake.mkdir()
    log = tmp_path / "argv.jsonl"
    docker = fake / "docker"
    docker.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ["ARGV_LOG"], "a") as out:
    out.write(json.dumps(sys.argv[1:]) + "\\n")
if "mktemp" in sys.argv:
    print("/tmp/test-cookie")
    raise SystemExit(0)
if "/api/status" in " ".join(sys.argv) + sys.stdin.read():
    print("{}")
    raise SystemExit(0)
raise SystemExit(1)
""")
    docker.chmod(0o755)
    secret = "regression-secret-do-not-publish"
    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / script_name)],
        env={
            **os.environ,
            "PATH": f"{fake}:{os.environ['PATH']}",
            "ARGV_LOG": str(log),
            "THEHIVE_ADMIN_USER": "admin@example.test",
            "THEHIVE_ADMIN_PASS": secret,
            "CORTEX_ADMIN_KEY": secret,
            "CORTEX_API_KEY": secret + "-connector",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert log.exists()
    assert secret not in log.read_text()
    assert secret not in result.stdout + result.stderr


def _thehive_seed_docker(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    docker = fake / "docker"
    docker.write_text(r"""#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["REQUEST_LOG"], "a") as out:
    out.write(json.dumps({"argv": argv}) + "\n")
if "mktemp" in argv:
    print("/tmp/thehive-session"); raise SystemExit(0)
if "rm" in argv:
    raise SystemExit(0)
config = sys.stdin.read()
with open(os.environ["REQUEST_LOG"], "a") as out:
    out.write(json.dumps({"config": config}) + "\n")
fields = {}
for line in config.splitlines():
    if " = " in line:
        name, value = line.split(" = ", 1)
        fields[name] = json.loads(value)
url = fields["url"]
if url.endswith("/api/v1/login"):
    if json.loads(fields["data"]) == {"user": os.environ["EXPECTED_USER"], "password": os.environ["EXPECTED_PASSWORD"]}:
        print("{}"); raise SystemExit(0)
    raise SystemExit(22)
if fields.get("cookie") != "/tmp/thehive-session":
    raise SystemExit(22)
if url.endswith("/api/v1/query"):
    print('[{"_id":"existing"}]'); raise SystemExit(0)
if url.endswith("/key"):
    print("existing-service-key"); raise SystemExit(0)
raise SystemExit(22)
""")
    docker.chmod(0o755)
    return fake


@pytest.mark.parametrize("source", ["environment", "dotenv"])
def test_thehive_seed_uses_declared_admin_and_preserves_the_service_key(
    tmp_path, source
):
    fake = _thehive_seed_docker(tmp_path)
    log = tmp_path / "requests.jsonl"
    password = 'declared-password-with-"quotes"-and-\\slashes'
    username = "declared-admin@example.test"
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"THEHIVE_ADMIN_USER", "THEHIVE_ADMIN_PASS", "ENV_FILE"}
    }
    env.update(
        PATH=f"{fake}:{os.environ['PATH']}",
        REQUEST_LOG=str(log),
        EXPECTED_USER=username,
        EXPECTED_PASSWORD=password,
        ENV_FILE=str(tmp_path / ".env"),
    )
    if source == "environment":
        env.update(THEHIVE_ADMIN_USER=username, THEHIVE_ADMIN_PASS=password)
    else:
        (tmp_path / ".env").write_text(
            f"THEHIVE_ADMIN_USER={username}\nTHEHIVE_ADMIN_PASS={password}\n"
        )
    for _ in range(2):
        result = subprocess.run(
            ["bash", str(PROJECT_ROOT / "scripts" / "thehive-apikey.sh")],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "existing-service-key"
        assert password not in result.stdout + result.stderr
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert all(password not in json.dumps(record.get("argv", [])) for record in records)
    configs = [record["config"] for record in records if "config" in record]
    assert not any("/key/renew" in config for config in configs)
    assert not any("admin@thehive.local" in config for config in configs)


@pytest.mark.parametrize("missing", ["THEHIVE_ADMIN_USER", "THEHIVE_ADMIN_PASS"])
def test_thehive_seed_refuses_missing_admin_credentials_before_docker(
    tmp_path, missing
):
    fake = _thehive_seed_docker(tmp_path)
    log = tmp_path / "requests.jsonl"
    env = {
        **os.environ,
        "PATH": f"{fake}:{os.environ['PATH']}",
        "REQUEST_LOG": str(log),
        "THEHIVE_ADMIN_USER": "declared@example.test",
        "THEHIVE_ADMIN_PASS": "declared-fixture",
        "ENV_FILE": str(tmp_path / ".env"),
    }
    env.pop(missing)

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "thehive-apikey.sh")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "declared administrator credentials" in result.stderr
    assert not log.exists()


def test_cortex_seed_creates_its_identities_in_the_declared_administrator_session(
    tmp_path,
):
    """After the backend holds Cortex's first-run window (#1273).

    The organization and initializer are created in the declared
    administrator's session, with Cortex's CSRF token, and the administrator's
    password never reaches an argv.
    """

    fake = tmp_path / "bin"
    fake.mkdir()
    log = tmp_path / "requests.jsonl"
    (fake / "docker").write_text("""#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
log = os.environ["REQUEST_LOG"]
if "mktemp" in argv:
    print("/tmp/cortex-session")
    raise SystemExit(0)
if argv[-2:] == ["cat", "/tmp/cortex-session"]:
    print("localhost\\tFALSE\\t/\\tFALSE\\t0\\tCORTEX-XSRF-TOKEN\\txsrf-123")
    raise SystemExit(0)
if argv[-2:] == ["rm", "-f"] or "rm" in argv:
    raise SystemExit(0)
config = sys.stdin.read()
with open(log, "a") as out:
    out.write(json.dumps({"argv": argv, "config": config}) + "\\n")
url = next(json.loads(l.split(" = ", 1)[1]) for l in config.splitlines() if l.startswith("url = "))
admin_key = "Authorization: Bearer " + os.environ["CORTEX_ADMIN_KEY"]
created = os.path.exists(os.environ["CREATED"])
if url.endswith("/api/status") or url.endswith("/api/maintenance/migrate"):
    print("{}"); raise SystemExit(0)
if url.endswith("/api/login") or url.endswith("/api/user/current") and "cookie = " in config:
    print("{}"); raise SystemExit(0)
if url.endswith("/api/user") and "X-CORTEX-XSRF-TOKEN: xsrf-123" in config:
    open(os.environ["CREATED"], "w").close(); print("{}"); raise SystemExit(0)
if url.endswith("/api/organization") and "X-CORTEX-XSRF-TOKEN: xsrf-123" in config:
    print("{}"); raise SystemExit(0)
if url.endswith("/api/user") and "header" not in config.split("url")[0] and "Bearer" not in config:
    print("{}"); raise SystemExit(0)
if created and admin_key in config and url.endswith("/api/user/current"):
    print("{}"); raise SystemExit(0)
raise SystemExit(1)
""")
    (fake / "docker").chmod(0o755)
    password = "declared-cortex-administrator-password"
    subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "cortex-apikey.sh")],
        env={
            **os.environ,
            "PATH": f"{fake}:{os.environ['PATH']}",
            "REQUEST_LOG": str(log),
            "CREATED": str(tmp_path / "created"),
            "CORTEX_SUPERADMIN_USER": "admin@example.test",
            "CORTEX_SUPERADMIN_PASSWORD": password,
            "CORTEX_ADMIN_KEY": "initializer-key",
            "CORTEX_API_KEY": "connector-key",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert all(password not in json.dumps(record["argv"]) for record in records)
    login = [r for r in records if '/api/login"' in r["config"]]
    assert login
    assert password in login[0]["config"]
    creates = [
        r
        for r in records
        if '/api/user"' in r["config"] and "techvault-admin@cortex.local" in r["config"]
    ]
    assert creates
    assert all("X-CORTEX-XSRF-TOKEN: xsrf-123" in r["config"] for r in creates)
    assert all('cookie = "/tmp/cortex-session"' in r["config"] for r in creates)
