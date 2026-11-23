"""The released TechVault pack publishes its management surfaces on loopback only.

``aptl lab start`` runs the publications the planner renders for the pinned
pack without reading the root ``docker-compose.yml`` (#954). This pins the
ADR-034 Host Exposure boundary on that rendered model (#1700).
"""

import pytest

from aptl.core.deployment._compose_port_realization import compose_port_entry
from tests.test_docker_compose_port_bindings import (
    assert_loopback_bound,
    unclassified_publications,
)

# The pack's nodes keep the pack's names, so the Wazuh services are hyphenated.
RENDERED_MANAGEMENT_SURFACES = [
    ("wazuh-manager", 1514),
    ("wazuh-manager", 1515),
    ("wazuh-manager", 514),
    ("wazuh-manager", 55000),
    ("wazuh-indexer", 9200),
    ("wazuh-dashboard", 443),
    ("misp", 8443),
    ("shuffle-frontend", 3443),
    ("shuffle-frontend", 3001),
]


@pytest.fixture(scope="module")
def rendered(released_techvault_realization) -> dict:
    """Every node publication the realization carries for the pinned TechVault pack.

    `aptl lab start` writes an image node's publications into the Compose port
    override and a base-container node's into its own ``docker run -p``. Both
    render these declarations, so each node is checked here whichever way it
    starts. Backend apparatus outside the realization, such as the
    operator-access relays, is checked in ``tests/test_operator_access.py``.
    The pack is realized once per test session, without Docker.
    """
    realization = released_techvault_realization
    spec = realization.deployment_spec(sorted(realization.profiles))
    return {
        "services": {
            node.name: {"ports": [compose_port_entry(p) for p in node.published_ports]}
            for node in spec.nodes
            if node.published_ports
        }
    }


@pytest.mark.parametrize("service,host_port", RENDERED_MANAGEMENT_SURFACES)
def test_rendered_management_surface_is_loopback_bound(rendered, service, host_port):
    assert_loopback_bound(rendered, service, host_port)


def test_every_rendered_published_port_is_classified(rendered):
    """A host publication nobody classified is one nobody checked (#1006)."""
    unclassified = unclassified_publications(rendered, set(RENDERED_MANAGEMENT_SURFACES))
    assert not unclassified, (
        f"host-published ports with no exposure classification: {unclassified}; "
        "add each to RENDERED_MANAGEMENT_SURFACES"
    )
