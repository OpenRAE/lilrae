"""Static consistency of the released TechVault pack (#954, #1700).

These tests read the staged released SDL and its realization. No running Docker
environment is needed.
"""

from pathlib import Path

import pytest

import tests.test_consistency as consistency
from tests.test_consistency import compose_config


@pytest.fixture(scope="module")
def techvault_sdl(tmp_path_factory) -> Path:
    """Staged SDL path of the default TechVault env-pack scenario (#875)."""
    from tests.techvault.pack import techvault_scenario_path

    return techvault_scenario_path(tmp_path_factory.mktemp("techvault-consistency"))


@pytest.fixture(scope="module")
def rendered_techvault(released_techvault_realization):
    """The pinned TechVault pack, realized once per test session without Docker."""
    return released_techvault_realization


@pytest.fixture(scope="module")
def rendered_techvault_spec(rendered_techvault):
    """The deployment spec the realization hands the Compose backend."""
    return rendered_techvault.deployment_spec(sorted(rendered_techvault.profiles))


class TestMispSuricataRulesVolume:
    def test_the_pack_shares_the_rules_volumes_with_sync(self, techvault_sdl):
        """ADR-043: the sync node and Suricata share the rules volumes."""
        from raes import parse_sdl_file

        scenario = parse_sdl_file(techvault_sdl)
        consumers = {
            volume_name: {
                (consumer.node, consumer.mount_destination, consumer.access_mode.value)
                for consumer in scenario.persistent_volumes[volume_name].consumers
            }
            for volume_name in ("suricata_misp_rules", "suricata_command_socket")
        }
        assert consumers["suricata_misp_rules"] == {
            ("suricata", "/var/lib/suricata/rules/misp", "read_only"),
            ("misp-suricata-sync", "/var/lib/suricata/rules/misp", "read_write"),
        }
        assert consumers["suricata_command_socket"] == {
            ("suricata", "/var/run/suricata", "read_write"),
            ("misp-suricata-sync", "/var/run/suricata", "read_write"),
        }


class TestKaliContainerLifecycle:
    """Issue #293 / ADR-033 §2: the kali container must reap children and
    its readiness must reflect the usable surface, not just port 22.

    kali is realized generically from the SDL (issue #581), never
    Compose-started, so these two properties no longer live in
    docker-compose.yml — they are asserted against the SDL node instead.
    """

    @staticmethod
    def _kali_node(techvault_sdl):
        from raes import parse_sdl_file

        scenario = parse_sdl_file(techvault_sdl)
        return scenario.nodes["kali"]

    def test_kali_runs_under_systemd_reaper(self, techvault_sdl):
        """kali must declare service_manager_units so the generic
        materializer boots it on the init-capable systemd base image
        (`base_image_for_os`, src/aptl/backends/raes_materializer.py) —
        systemd is PID 1 there and reaps orphaned children natively.
        Without any service unit declared, kali would get the bare
        non-service base image instead, with no reaper (the zombie defect
        in issue #293, now a property of image selection, not a Compose
        `init: true` flag)."""
        kali = self._kali_node(techvault_sdl)
        assert kali.runtime is not None
        assert kali.runtime.service_manager_units, (
            "kali must declare at least one service_manager_units entry "
            "(ADR-033 §2 / issue #293): with none, the materializer selects "
            "the non-service base image, which has no PID-1 reaper."
        )

    def test_kali_scenario_owns_only_native_sshd(self, techvault_sdl):
        """Kali declares sshd; capture is admitted backend apparatus.

        The scenario must not claim the backend-owned OBS-003 capture broker as
        a guest service.  Apparatus construction, activation, and disclosure
        are verified separately by ``test_capture_apparatus.py``.
        """
        kali = self._kali_node(techvault_sdl)
        unit_names = {unit.unit_name for unit in kali.runtime.service_manager_units}
        assert "ssh.service" in unit_names, "kali must run and verify sshd"
        assert "kali-capture-bootstrap.service" not in unit_names

    def test_kali_has_no_scenario_declared_host_proxy(
        self, compose_config, rendered_techvault
    ):
        """Kali's host-routable endpoint is backend apparatus, not a scenario node.

        The old `kali-ssh-proxy` service published 127.0.0.1:2023 for host-run
        MCP clients. TechVault declares no such node, nothing started it, and it
        has been removed (issue #1006). Operator access is declared as
        `agents.red-team-operator.interactive_access` and is the backend's to
        provide and disclose; this test pins only that neither the in-tree
        Compose model nor the realized pack reintroduces a proxy of its own.
        The `kali` Compose service is a scale-to-zero stub, so kali's own
        attachments are read from the realization (#954).
        """
        services = compose_config["services"]
        assert "kali-ssh-proxy" not in services
        assert "webapp-proxy" not in services
        nodes = {node.name: node for node in rendered_techvault.nodes}
        assert not {"kali-ssh-proxy", "webapp-proxy"} & nodes.keys()
        internal = {
            network.name for network in rendered_techvault.networks if network.internal
        }
        kali = nodes["kali"]
        assert set(kali.networks) <= internal, (
            "kali must stay on internal range networks; host-routable operator "
            "access is published by backend apparatus, not by the node"
        )
        assert not kali.published_ports, "kali must publish no host port itself"


class TestRenderedNetworkEgressControls(consistency.TestNetworkEgressControls):
    """SAF-002 on the networks the planner renders for the pinned pack.

    ``aptl lab start`` creates this generated base Compose file by default (#954).
    """

    @pytest.fixture
    def networks(self, rendered_techvault_spec):
        from aptl.core.deployment._compose_node_topology import render_networks

        return render_networks(rendered_techvault_spec)
