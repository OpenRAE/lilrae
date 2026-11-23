"""The released TechVault pack leaves environment and mount scopes closed (#1700)."""

from __future__ import annotations

from pathlib import Path

import pytest
from raes.parser import parse_sdl_file

from aptl.backends.raes_base_substrate import _environment_names
from tests.techvault.pack import techvault_scenario_path


@pytest.fixture(scope="module")
def scenario_path(tmp_path_factory) -> Path:
    """Staged SDL path of the default TechVault env-pack scenario (#875)."""
    return techvault_scenario_path(tmp_path_factory.mktemp("raes-env"))


def _webapp_runtime(scenario_path: Path):
    return parse_sdl_file(scenario_path).nodes["webapp"].runtime


def test_closed_pack_environment_is_not_invented(scenario_path):
    """An empty closed environment remains empty at the base-container seam."""

    names = _environment_names(_webapp_runtime(scenario_path))

    assert names == ()


def test_closed_node_mounts_are_not_invented(scenario_path):
    """Backend-neutral nodes gain no Docker mount details through APTL."""

    from aptl.backends.raes_base_substrate import _volume_mounts

    scenario = parse_sdl_file(scenario_path)
    lowered = {
        name: {(m.source, m.target) for m in _volume_mounts(node.runtime)}
        for name, node in scenario.nodes.items()
        if getattr(node, "runtime", None) and node.runtime.mounts
    }

    assert lowered == {}

    # Explicit portable persistent-volume resources remain authored state; they
    # are not node-local Docker mount selections and keep their exact consumers.
    persistent = {
        name: {
            (consumer.node, consumer.mount_destination) for consumer in volume.consumers
        }
        for name, volume in scenario.persistent_volumes.items()
    }
    assert persistent["suricata_misp_rules"] == {
        ("suricata", "/var/lib/suricata/rules/misp"),
        ("misp-suricata-sync", "/var/lib/suricata/rules/misp"),
    }
    assert persistent["suricata_command_socket"] == {
        ("suricata", "/var/run/suricata"),
        ("misp-suricata-sync", "/var/run/suricata"),
    }


def test_closed_pack_environment_has_no_backend_defaults(scenario_path):
    """Old Compose literals are not smuggled into the backend-neutral pack."""

    from aptl.backends.raes_base_substrate import _environment_defaults

    defaults = dict(_environment_defaults(_webapp_runtime(scenario_path)))

    assert defaults == {}


def test_closed_pack_credentials_are_not_reintroduced_as_environment(scenario_path):
    """A planted secret elsewhere in the scenario does not open this scope."""

    from aptl.backends.raes_base_substrate import _environment_defaults

    scenario = parse_sdl_file(scenario_path)

    db = dict(_environment_defaults(scenario.nodes["db"].runtime))
    webapp = dict(_environment_defaults(scenario.nodes["webapp"].runtime))

    assert db == {}
    assert webapp == {}


def test_a_real_operator_secret_is_still_authored_empty(scenario_path):
    """The distinction must cut both ways, or everything becomes a fixture."""

    from aptl.backends.raes_base_substrate import _environment_defaults

    scenario = parse_sdl_file(scenario_path)
    sync = dict(_environment_defaults(scenario.nodes["misp-suricata-sync"].runtime))

    # MISP's API key is a real deployment credential, not planted range content.
    assert "MISP_API_KEY" not in sync


def test_closed_pack_environment_has_no_values_to_reclassify(
    scenario_path,
):
    """APTL cannot reinterpret absent closed values as backend fixtures."""

    scenario = parse_sdl_file(scenario_path)

    assert scenario.nodes["db"].runtime.environment == []
    assert scenario.nodes["webapp"].runtime.environment == []
