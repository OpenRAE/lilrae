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
        profiles=(
            RequestProfile.model_validate({**profile_data(), **VERTEX, **changes}),
        ),
    )


def test_vertex_profile_routes_only_through_the_attached_identity():
    profile = catalog().profiles[0]
    attached = AttachedServiceAccountSource(
        kind="attached-service-account", project="prod-mgau4w"
    )
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


def test_sealed_vertex_profile_renders_its_native_route_and_turn_limit():
    from aptl.workbench.opencode_configuration import render_opencode_config

    profile = catalog(assistant_turn_limit={"state": "set", "value": 200}).profiles[0]
    config = render_opencode_config(
        profile.model,
        VertexRoute("test-project"),
        {"*": "deny"},
        {},
        request_profile=profile,
        max_steps=profile.assistant_turn_limit.value,
    )
    assert config["enabled_providers"] == ["google-vertex"]
    provider = config["provider"]["google-vertex"]
    assert provider["options"] == {"project": "test-project", "location": "global"}
    assert set(provider["models"]) == {profile.model.removeprefix("google-vertex/")}
    assert config["agent"]["build"] == {"steps": 200}


@pytest.mark.parametrize("change", ["route", "model", "reasoning"])
def test_vertex_renderer_refuses_mismatched_or_unsupported_controls(change):
    from aptl.workbench.opencode_configuration import render_opencode_config

    profile = catalog().profiles[0]
    route = VertexRoute("test-project")
    model = profile.model
    if change == "route":
        route = OpenRouterRoute("https://openrouter.ai/api/v1", "test-provider")
    elif change == "model":
        model = "google-vertex/test/another-model"
    else:
        profile = catalog(
            reasoning_mode="disabled",
            reasoning_effort={"state": "omit", "value": None},
            reasoning_budget={"state": "omit", "value": None},
        ).profiles[0]
    with pytest.raises(ValueError):
        render_opencode_config(model, route, {"*": "deny"}, {}, request_profile=profile)
