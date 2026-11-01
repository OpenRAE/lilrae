"""Shared test fixtures for APTL CLI tests."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

# The pytester fixture runs pytest in a test, for the tests of the repository's
# pytest plugins.
pytest_plugins = ["pytester"]


# ---------------------------------------------------------------------------
# Unit test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _allow_testclient_host(monkeypatch):
    """Permit Starlette ``TestClient``'s default ``Host: testserver``.

    The BFF Host gate (UI-008a, DNS-rebinding defence) rejects non-loopback
    hosts on ``/api/*``. The test client sends ``Host: testserver``, so allow it
    for the suite. Production defaults to loopback-only; tests that exercise the
    gate's rejection path set an explicitly disallowed Host instead.
    """
    monkeypatch.setenv("APTL_ALLOWED_HOSTS", "testserver")


@pytest.fixture(autouse=True)
def _fast_soc_ca_keys(monkeypatch):
    """Shrink SOC-CA RSA key sizes for the whole test run.

    ``ensure_soc_certs`` mints a fresh CA plus four service certs on every
    call and is exercised dozens of times across the suite (and again
    whenever lab-startup code paths run). At the production 4096-bit CA size
    that prime search dominates wall time and can stall on a loaded host,
    which previously read as a hang. The CA-chain logic the tests assert is
    key-size independent, so generate small keys here; production sizes
    remain the defaults in ``aptl.core._soc_ca_builders``.
    """
    from aptl.core import _soc_ca_builders

    monkeypatch.setattr(_soc_ca_builders, "_CA_KEY_SIZE", 1024)
    monkeypatch.setattr(_soc_ca_builders, "_SVC_KEY_SIZE", 1024)


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for config files."""
    return tmp_path


@pytest.fixture
def valid_config_dict() -> dict:
    """A minimal valid APTL configuration dictionary."""
    return {
        "lab": {
            "name": "test-lab",
            "network_subnet": "172.20.0.0/16",
        },
        "containers": {"profiles": ["wazuh", "victim", "kali"]},
    }


@pytest.fixture
def valid_config_file(tmp_config_dir: Path, valid_config_dict: dict) -> Path:
    """Write a valid JSON config file and return its path."""
    config_path = tmp_config_dir / "aptl.json"
    config_path.write_text(json.dumps(valid_config_dict))
    return config_path


@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess.run for commands that shell out."""
    return mocker.patch("subprocess.run")


@pytest.fixture
def mock_container() -> MagicMock:
    """A mock Docker container object."""
    container = MagicMock()
    container.name = "aptl-victim"
    container.status = "running"
    container.short_id = "abc123"
    container.attrs = {
        "State": {"Health": {"Status": "healthy"}},
        "NetworkSettings": {
            "Networks": {
                "aptl-network": {"IPAddress": "172.20.0.20"}
            }
        },
    }
    return container


@pytest.fixture
def mock_docker_client(mocker, mock_container):
    """Mock docker.from_env() returning a client with containers."""
    mock_client = MagicMock()
    mock_client.containers.list.return_value = [mock_container]
    mock_client.containers.get.return_value = mock_container
    mocker.patch("aptl.core.lab.docker_client", return_value=mock_client)
    return mock_client


# ---------------------------------------------------------------------------
# Scenario fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_scenario_dict() -> dict:
    """Minimal valid scenario as a dictionary."""
    return {
        "metadata": {
            "id": "test-scenario",
            "name": "Test Scenario",
            "description": "A test scenario for unit tests",
            "difficulty": "beginner",
            "estimated_minutes": 10,
        },
        "mode": "red",
        "containers": {"required": ["kali", "victim"]},
        "objectives": {
            "red": [
                {
                    "id": "test-obj",
                    "description": "A test objective",
                    "type": "manual",
                    "points": 100,
                }
            ],
            "blue": [],
        },
    }


@pytest.fixture
def sample_scenario_yaml(tmp_path: Path, sample_scenario_dict: dict) -> Path:
    """Write a valid scenario YAML file and return its path."""
    path = tmp_path / "test-scenario.yaml"
    path.write_text(yaml.dump(sample_scenario_dict, default_flow_style=False))
    return path


@pytest.fixture
def aptl_state_dir(tmp_path: Path) -> Path:
    """Provide a temporary .aptl/ state directory."""
    state_dir = tmp_path / ".aptl"
    state_dir.mkdir()
    return state_dir


# ---------------------------------------------------------------------------
# Unified scenario with attack steps fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_scenario_with_steps_dict() -> dict:
    """Valid unified scenario with attack steps + OCSF detections."""
    return {
        "metadata": {
            "id": "test-unified",
            "name": "Test Unified Scenario",
            "description": "A unified scenario with steps and OCSF detections",
            "difficulty": "intermediate",
            "estimated_minutes": 30,
            "tags": ["test"],
            "mitre_attack": {
                "tactics": ["Reconnaissance", "Initial Access"],
                "techniques": ["T1595.002", "T1190"],
            },
        },
        "mode": "purple",
        "containers": {"required": ["kali", "wazuh"]},
        "attack_chain": "Recon -> Exploit -> Exfil",
        "steps": [
            {
                "step_number": 1,
                "technique_id": "T1595.002",
                "technique_name": "Active Scanning",
                "tactic": "Reconnaissance",
                "description": "Scan the target network",
                "target": "victim",
                "commands": ["nmap -sV 172.20.0.20"],
                "prerequisites": [],
                "expected_detections": [
                    {
                        "product_name": "wazuh",
                        "analytic_uid": "1000001",
                        "severity_id": 3,
                        "description": "Port scan detected",
                        "max_detection_time_seconds": 30,
                    }
                ],
                "investigation_hints": ["Check Suricata alerts"],
                "remediation": ["Log the activity"],
            },
            {
                "step_number": 2,
                "technique_id": "T1190",
                "technique_name": "Exploit Public-Facing Application",
                "tactic": "Initial Access",
                "description": "Exploit SQL injection vulnerability",
                "target": "webapp",
                "commands": ["sqlmap -u http://target/page?id=1"],
                "prerequisites": ["T1595.002"],
                "expected_detections": [],
                "investigation_hints": [],
                "remediation": [],
            },
        ],
    }


@pytest.fixture(autouse=True)
def _live_lab_credentials(request, monkeypatch):
    """Keep lab credential access behind test execution and explicit opt-in."""
    marker = request.node.get_closest_marker("live_lab")
    if marker is None:
        return
    opt_in = marker.kwargs.get("opt_in", "APTL_SMOKE")
    if os.getenv(opt_in) != "1":
        pytest.skip(f"Live tests require explicit {opt_in}=1 authorization")
    if opt_in != "APTL_SMOKE":
        return  # The composed gate owns its own admitted credential sources.
    from tests import helpers

    for name, value in helpers.live_credentials().items():
        monkeypatch.setattr(helpers, name, value)
        if hasattr(request.module, name):
            monkeypatch.setattr(request.module, name, value)


@pytest.fixture(scope="session")
def released_techvault_bundle(tmp_path_factory):
    from aptl.core.scenario_bundle import env_pack_bundle
    from tests.techvault_pack import _pack_root

    bundle = env_pack_bundle(
        tmp_path_factory.mktemp("released-techvault"),
        identity="techvault", source_pack=_pack_root(),
    )
    yield bundle
    bundle.close()


@pytest.fixture(scope="session")
def released_techvault_scenario(released_techvault_bundle):
    """Read-only declarations; tests that alter fields must copy those fields."""
    from raes import parse_sdl_file

    return parse_sdl_file(released_techvault_bundle.sdl_path)


@pytest.fixture(scope="session")
def released_techvault_realization(released_techvault_bundle, released_techvault_scenario):
    """Share the read-only released realization, never a live manager/backend."""
    from tests.techvault_pack import realize_techvault_pack

    return realize_techvault_pack(
        released_techvault_bundle.root, bundle=released_techvault_bundle,
        scenario=released_techvault_scenario,
    )
