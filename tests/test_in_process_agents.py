"""Check the released pack's in-node Wazuh configuration after realization.

The former LIVE_LAB suite assumed four fixed container names, retired sidecars,
NET_ADMIN and Compose LOG_PATHS. Those are no longer the shipped contract.
These checks exercise the realized workload and production configuration
renderer without Docker. Native configuration/process readback remains covered
by test_raes_runtime_observation.py, and the live active-response suite targets
the declared agent roster in test_wazuh_active_response.py.
"""

from __future__ import annotations

from xml.etree import ElementTree

import pytest

from aptl.core.deployment._wazuh_agent_configuration import wazuh_config
from tests.techvault_pack import realize_techvault_pack


ENDPOINT_NODES = (
    "ad", "db", "dns", "fileshare", "suricata", "victim", "webapp", "workstation"
)


@pytest.fixture(scope="module")
def realized_nodes(tmp_path_factory):
    realization = realize_techvault_pack(tmp_path_factory.mktemp("in-node-agents"))
    assert not realization.diagnostics
    return {node.name: node for node in realization.nodes}


def _endpoint_agent(node):
    agents = [
        agent
        for agent in node.runtime.forwarding_agents
        if agent.implementation.value == "wazuh_agent"
    ]
    assert len(agents) == 1, node.name
    return agents[0]


@pytest.mark.parametrize("name", ENDPOINT_NODES)
def test_endpoint_agent_uses_the_workload_substrate(realized_nodes, name):
    node = realized_nodes[name]
    _endpoint_agent(node)
    image_ref = node.image.image_ref if node.image else node.backend_base_image_ref
    assert "wazuh-agent" in image_ref
    assert node.backend_services == (name,)


@pytest.mark.parametrize("name", ENDPOINT_NODES)
def test_rendered_agent_configuration_preserves_declared_log_sources(
    realized_nodes, name
):
    agent = _endpoint_agent(realized_nodes[name])
    assert agent.sources, name
    payload = wazuh_config(agent)
    assert payload is not None, name
    config = ElementTree.fromstring(payload)
    assert [item.text for item in config.findall("localfile/location")] == [
        source.location for source in agent.sources
    ]
    assert config.findtext("client/enrollment/agent_name") == agent.name
    assert config.findtext("client/enrollment/manager_address") == "wazuh-manager"
    assert config.findtext("client/server/address") == "wazuh-manager"


def test_realized_pack_has_no_retired_wazuh_sidecars(realized_nodes):
    assert not any(name.startswith("wazuh-sidecar-") for name in realized_nodes)
    kali = realized_nodes["kali"]
    assert not any(
        agent.implementation.value == "wazuh_agent"
        for agent in kali.runtime.forwarding_agents
    )
