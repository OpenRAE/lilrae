"""A native OpenCode request profile may route to Vertex AI with the attached identity."""

import pytest

from aptl.core._credential_sources import AttachedServiceAccountSource
from aptl.core.config import ProcessEnvironmentCredentialSource
from aptl.core.opencode import OpenRouterRoute, VertexRoute
from aptl.core.participant_requests.profiles import RequestCatalog, RequestProfile
from aptl.workbench.trial_participants import participant_route
from tests.participant_request_fixture import profile_data

VERTEX = {
    "model": "google-vertex/zai-org/glm-5.2-maas",
    "gateway": "google-vertex",
    "gateway_endpoint": "https://aiplatform.googleapis.com",
    "serving_provider": "google-vertex",
}
KEY = ProcessEnvironmentCredentialSource(kind="process-environment", variable="KEY")


def catalog(**changes):
    return RequestCatalog(
        provider="opencode",
        implementation_version="1.0.0",
        build_version="1.19.5",
        executable_sha256="a" * 64,
        profiles=(RequestProfile.model_validate({**profile_data(), **VERTEX, **changes}),),
    )


def test_vertex_profile_routes_only_through_the_attached_identity():
    profile = catalog().profiles[0]
    attached = AttachedServiceAccountSource(kind="attached-service-account", project="prod-mgau4w")
    assert participant_route(profile, attached) == VertexRoute("prod-mgau4w")
    with pytest.raises(ValueError, match="attached service account"):
        participant_route(profile, KEY)
    openrouter = RequestProfile.model_validate(profile_data())
    assert isinstance(participant_route(openrouter, KEY), OpenRouterRoute)


@pytest.mark.parametrize(
    "changes",
    [
        {"gateway_endpoint": "https://example.com"},
        {"serving_provider": "z-ai"},
        {"model": "openrouter/z-ai/glm-5.3"},
    ],
)
def test_vertex_profile_refuses_another_route(changes):
    with pytest.raises(ValueError):
        catalog(**changes)
