"""Released TechVault console bindings have public TLS names (#1700)."""

from __future__ import annotations

from aptl.core import _participant_desktop_tls as tls


def test_released_console_bindings_have_a_public_certificate_identity(released_techvault_realization):
    result = released_techvault_realization
    realization = result.deployment_spec(sorted(result.profiles))
    expected = {
        "shuffle-frontend": "shuffle-frontend/server.pem",
        "wazuh-dashboard": "wazuh.dashboard.pem",
    }
    for node in realization.nodes:
        if node.name not in expected:
            continue
        paths = set()
        for artifact in realization.generated_artifacts:
            if artifact.generator == "certificate_bundle":
                selected = tls._selected_outputs(artifact, node.address)
                paths.update(tls._selected_certificate_paths(artifact, selected))
        assert expected[node.name] in paths
