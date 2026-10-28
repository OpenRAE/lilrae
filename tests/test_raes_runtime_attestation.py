"""Content-addressed TechVault runtime-configuration attestations."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends.raes_runtime_attestation import (
    TECHVAULT_STUDY_RUNTIME_ATTESTATION_SET_DIGEST,
    observe_techvault_attested_concerns,
)
from aptl.core.scenario_bundle import PackIdentity
from aptl.core.deployment._wazuh_attestation import declared_wazuh_fact_ids
import pytest

_MISP_BACKEND_IMAGE = (
    "ghcr.io/misp/misp-docker/misp-core@"
    "sha256:0eaa4e423d5cd965b7b76aa5665e81d5c05a35bc46a4ffec2ca52e0cfe627e86"
)


class _Backend:
    def __init__(
        self,
        digest: str | None,
        declared_wazuh_attestation: dict[str, object] | None = None,
    ) -> None:
        self.digest = digest
        self.declared_wazuh_attestation = declared_wazuh_attestation or {}

    def container_image_digest(self, _container_name: str) -> str | None:
        return self.digest


def _matched(*fact_ids: str) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "fact_id": fact_id,
            "expected": "declared",
            "observed": "declared",
            "status": "matched",
            "failure_category": "",
        }
        for fact_id in fact_ids
    )


@pytest.fixture(scope="module")
def declared_pack(released_techvault_bundle, released_techvault_scenario):
    return released_techvault_bundle, released_techvault_scenario


def _misp_node(declared_pack):
    bundle, scenario = declared_pack
    return bundle, SimpleNamespace(
        name="misp", container_name="aptl-misp",
        runtime=deepcopy(scenario.nodes["misp"].runtime),
        image=SimpleNamespace(image_ref=_MISP_BACKEND_IMAGE),
    )


def _wazuh_node(declared_pack, name: str, service_name: str):
    bundle, scenario = declared_pack
    return bundle, SimpleNamespace(
        name=name, backend_services=(service_name,), container_name=f"aptl-{name}",
        runtime=deepcopy(scenario.nodes[name].runtime), image=None,
    )


def test_known_pack_projection_and_realized_image_are_attested(declared_pack):
    bundle, node = _misp_node(declared_pack)

    concerns = observe_techvault_attested_concerns(
        _Backend(node.image.image_ref.rsplit("@", 1)[1]),
        node,
        bundle.pack_identity,
        content_verified=True,
    )

    assert CONCERN_PAYLOAD_PATH["runtime-applications"] in concerns
    assert CONCERN_PAYLOAD_PATH["runtime-platform-applications"] in concerns


def test_study_copy_uses_same_projection_only_at_its_exact_digest(declared_pack):
    bundle, node = _misp_node(declared_pack)
    backend = _Backend(node.image.image_ref.rsplit("@", 1)[1])
    study = PackIdentity(
        "techvault-participant-study",
        "0.1.2",
        TECHVAULT_STUDY_RUNTIME_ATTESTATION_SET_DIGEST,
    )

    attested = observe_techvault_attested_concerns(
        backend, node, study, content_verified=True
    )
    changed = observe_techvault_attested_concerns(
        backend,
        node,
        PackIdentity(study.pack_id, study.pack_version, "sha256:" + "0" * 64),
        content_verified=True,
    )

    assert CONCERN_PAYLOAD_PATH["runtime-applications"] in attested
    assert changed == {}


def test_changed_semantic_projection_is_not_attested(declared_pack):
    bundle, node = _misp_node(declared_pack)
    node.runtime.applications[0].routes[0].path = "/not-the-released-route"

    concerns = observe_techvault_attested_concerns(
        _Backend(node.image.image_ref.rsplit("@", 1)[1]),
        node,
        bundle.pack_identity,
        content_verified=True,
    )

    assert CONCERN_PAYLOAD_PATH["runtime-applications"] not in concerns


def test_wrong_realized_image_is_not_attested(declared_pack):
    bundle, node = _misp_node(declared_pack)

    concerns = observe_techvault_attested_concerns(
        _Backend("sha256:" + "0" * 64),
        node,
        bundle.pack_identity,
        content_verified=True,
    )

    assert concerns == {}


def test_wazuh_runtime_facts_require_native_declared_fact_attestation(declared_pack):
    bundle, node = _wazuh_node(declared_pack, "wazuh-indexer", "wazuh.indexer")
    path = CONCERN_PAYLOAD_PATH["runtime-datastore-services"]

    absent = observe_techvault_attested_concerns(
        _Backend(None), node, bundle.pack_identity, content_verified=True
    )
    observed = observe_techvault_attested_concerns(
        _Backend(
            None,
            {"wazuh.indexer": _matched(*declared_wazuh_fact_ids(node))},
        ),
        node,
        bundle.pack_identity,
        content_verified=True,
    )

    assert path not in absent
    assert path in observed


def test_wazuh_runtime_facts_require_the_exact_declared_observation_set(declared_pack):
    bundle, node = _wazuh_node(declared_pack, "wazuh-indexer", "wazuh.indexer")
    required = sorted(declared_wazuh_fact_ids(node))
    assert len(required) > 1

    concerns = observe_techvault_attested_concerns(
        _Backend(None, {"wazuh.indexer": _matched(*required[:-1])}),
        node,
        bundle.pack_identity,
        content_verified=True,
    )

    assert CONCERN_PAYLOAD_PATH["runtime-datastore-services"] not in concerns


def test_non_wazuh_datastore_does_not_require_wazuh_attestation(declared_pack):
    bundle, node = _wazuh_node(declared_pack, "misp-redis", "misp.redis")

    concerns = observe_techvault_attested_concerns(
        _Backend(None), node, bundle.pack_identity, content_verified=True
    )

    assert CONCERN_PAYLOAD_PATH["runtime-datastore-services"] in concerns


def test_every_pinned_projection_matches_the_released_pack(released_techvault_realization):
    """A pack release that changes an attested claim fails here, not live (#1273).

    Each pinned digest is the canonical projection of the released TechVault
    SDL claim. A stale pin leaves that concern uncorroborated, and lab start
    then fails its realization readback after every service is up.
    """

    from raes_processor.semantics.realization import project_realization_concern

    from aptl.backends import raes_runtime_attestation as attestation

    nodes = {node.name: node for node in released_techvault_realization.nodes}
    stale = [
        key
        for key, pinned in attestation._TECHVAULT_PROJECTION_DIGESTS.items()
        if attestation.canonical_json_digest(
            project_realization_concern(
                key[1],
                getattr(nodes[key[0]].runtime, attestation._RUNTIME_FIELD_BY_KIND[key[1]]),
                observed=False,
            )
        )
        != pinned
    ]

    assert stale == []
