"""Consumer and run boundaries shared by generic Docker and Compose (#965)."""

from dataclasses import replace
from types import SimpleNamespace
import hashlib
import json
import uuid

import pytest

from aptl.core.config import EnvironmentGrant
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.scenario_bundle import PackIdentity
from tests.test_compose_environment_bindings import (
    _PACK,
    _delivered,
    _realization,
    _secret,
    _service,
)
from tests.test_raes_runtime_environment import _bound_body, _spec


@pytest.fixture(params=["generic", "compose"])
def route(request):
    return request.param


def _graph(route, *nodes, **kwargs):
    graph = _realization(*nodes, **kwargs)
    return replace(graph, images=()) if route == "generic" else graph


def _adapter_grant(consumer="db", source="STARTUP_TOKEN"):
    return EnvironmentGrant(
        pack=_PACK.pack_id,
        consumer=consumer,
        variable="API_TOKEN",
        source={"kind": "project-env-file", "variable": source},
    )


def _delivery(route, backend, graph, root):
    if route == "compose":
        return _delivered(backend, graph, root)["db"]
    return _bound_body(
        backend, _spec(("API_TOKEN",), sourced=("API_TOKEN",), node="db")
    )


@pytest.mark.parametrize("mismatch", ["consumer", "pack", "no-pack", "missing-grant"])
def test_adapter_source_requires_an_explicit_consumer_and_exact_selection(
    tmp_path, monkeypatch, route, mismatch
):
    canary = f"adapter-{uuid.uuid4().hex}"
    monkeypatch.setenv("API_TOKEN", canary)
    (tmp_path / ".env").write_text(f"STARTUP_TOKEN={canary}\nAPI_TOKEN={canary}\n")
    graph = _graph(
        route,
        _service("db", _secret("API_TOKEN")),
        adapter_names=("STARTUP_TOKEN", "API_TOKEN"),
        adapter_grants=()
        if mismatch == "missing-grant"
        else (_adapter_grant("other" if mismatch == "consumer" else "db"),),
    )
    if mismatch == "pack":
        graph = replace(
            graph,
            pack_identity=PackIdentity(_PACK.pack_id, "2.0.0", "sha256:" + "1" * 64),
        )
    elif mismatch == "no-pack":
        graph = replace(graph, pack_identity=None)
    backend = DockerComposeBackend(tmp_path)
    commands = []
    monkeypatch.setattr(backend, "_run", lambda cmd, **_: commands.append(cmd))

    assert backend._environment_binding_preflight(graph) is not None
    result = backend.realize(graph, scenario_root=tmp_path)

    assert not result.success
    assert "API_TOKEN has no environment grant" in result.error
    assert canary not in result.error
    assert commands == []
    assert not (tmp_path / ".aptl/realization").exists()
    assert backend._environment_binding_context is None


def test_adapter_binding_captures_its_source_and_refreshes_between_runs(
    tmp_path, monkeypatch, route, caplog
):
    graph = _graph(
        route,
        _service("db", _secret("API_TOKEN")),
        adapter_names=("STARTUP_TOKEN",),
        adapter_grants=(_adapter_grant(),),
    )
    backend = DockerComposeBackend(tmp_path)
    values = [f"bound-{uuid.uuid4().hex}" for _ in range(2)]
    for value in values:
        (tmp_path / ".env").write_text(f"STARTUP_TOKEN={value}\n")
        with caplog.at_level("INFO", logger="aptl"):
            assert backend._environment_binding_preflight(graph) is None
            # A source changed after preflight cannot alter this start.
            (tmp_path / ".env").write_text("STARTUP_TOKEN=changed-after-check\n")
            delivered = _delivery(route, backend, graph, tmp_path)
        assert value in delivered
        assert "changed-after-check" not in delivered
    assert "startup-adapter:project-env-file:STARTUP_TOKEN" in caplog.text
    for value in values:
        assert value not in caplog.text
        assert hashlib.sha256(value.encode()).hexdigest() not in caplog.text

    # A failed later run clears both the adapter and delivery snapshots.
    (tmp_path / ".env").write_text("")
    result = backend._environment_binding_preflight(graph)
    assert result is not None and "has no value" in result.error
    assert backend._environment_binding_context is None
    assert backend._compose_environment is None


@pytest.mark.parametrize(
    "source",
    [
        "valid",
        "artifact",
        "output",
        "missing-output",
        "node",
        "consumer",
        "service",
        "duplicate",
        "missing",
    ],
)
def test_generated_reference_matches_its_exact_source_before_mutation(
    tmp_path, monkeypatch, route, source
):
    variable = {
        "name": "API_TOKEN",
        "value_classification": "redacted",
        "value_from": {"generated_artifact": "keys", "output": "api-key"},
    }
    consumer = SimpleNamespace(
        target_address="provision.node.other"
        if source == "consumer"
        else "provision.node.db",
        environment_variable="API_TOKEN",
        node_name="other" if source == "node" else "db",
        service_name="other" if source == "service" else "db",
        output_name="other" if source == "output" else "api-key",
    )
    artifact = SimpleNamespace(
        name="other" if source == "artifact" else "keys",
        outputs=()
        if source == "missing-output"
        else (SimpleNamespace(name="api-key"),),
        environment_consumers=(consumer, consumer)
        if source == "duplicate"
        else (consumer,),
    )
    graph = replace(
        _graph(route, _service("db", variable)),
        generated_artifacts=() if source == "missing" else (artifact,),
    )
    monkeypatch.setenv("API_TOKEN", f"ambient-{uuid.uuid4().hex}")
    backend = DockerComposeBackend(tmp_path)
    if source == "valid":
        assert backend._environment_binding_preflight(graph) is None
    else:
        commands = []
        monkeypatch.setattr(backend, "_run", lambda cmd, **_: commands.append(cmd))
        assert backend._environment_binding_preflight(graph) is not None
        result = backend.realize(graph, scenario_root=tmp_path)
        assert not result.success
        assert "API_TOKEN has no generated output for this node" in result.error
        assert commands == []
        assert not (tmp_path / ".aptl/realization").exists()


@pytest.mark.parametrize(
    "classification", ["secret_fixture", "plain", "unknown", "redacted"]
)
def test_generated_readback_never_commits_operational_values(classification):
    from raes.runtime_configuration import RuntimeConfiguration
    from aptl.backends._raes_runtime_environment_observation import observe_environment

    canary = f"generated-{uuid.uuid4().hex}"
    runtime = RuntimeConfiguration.model_validate(
        {
            "environment": [
                {
                    "name": "API_TOKEN",
                    "value_classification": classification,
                    "value_from": {"generated_artifact": "keys", "output": "api-key"},
                }
            ]
        }
    )
    disclosed = observe_environment(
        {"Config": {"Env": [f"API_TOKEN={canary}"]}}, runtime
    )
    evidence = json.dumps(disclosed)
    assert canary not in evidence
    assert hashlib.sha256(canary.encode()).hexdigest() not in evidence
    assert "value_commitment" not in evidence


@pytest.mark.parametrize("classification", ["secret_fixture", "plain", "unknown"])
def test_generated_values_that_cannot_disclose_a_digest_require_open_authority(
    tmp_path, monkeypatch, route, classification
):
    graph = _graph(
        route,
        _service(
            "db",
            {
                "name": "API_TOKEN",
                "value_classification": classification,
                "value_from": {"generated_artifact": "keys", "output": "api-key"},
            },
        ),
    )
    graph = replace(graph, realization_authority=())
    backend = DockerComposeBackend(tmp_path)
    commands = []
    monkeypatch.setattr(backend, "_run", lambda cmd, **_: commands.append(cmd))
    result = backend.realize(graph, scenario_root=tmp_path)
    assert not result.success
    assert "needs open runtime-environment authority" in result.error
    assert commands == []
    assert not (tmp_path / ".aptl/realization").exists()


@pytest.mark.parametrize(
    "invalid", ["pack", "source", "ambient", "duplicate", "shape", "unidentified"]
)
def test_startup_plan_refuses_unowned_or_ambiguous_sources(invalid):
    from aptl.backends.scenario_startup import (
        ScenarioEnvironmentFixture,
        ScenarioStartupPlan,
        ScenarioStartupProviderError,
        _validated_plan,
    )

    grant = _adapter_grant()
    if invalid == "pack":
        grant = grant.model_copy(update={"pack": "other-pack"})
    elif invalid in {"source", "ambient"}:
        grant = EnvironmentGrant(
            pack=_PACK.pack_id,
            consumer="db",
            variable="API_TOKEN",
            source={
                "kind": "process-environment"
                if invalid == "ambient"
                else "project-env-file",
                "variable": "UNDECLARED" if invalid == "source" else "STARTUP_TOKEN",
            },
        )
    grants = (grant, grant) if invalid == "duplicate" else (grant,)
    plan = ScenarioStartupPlan(
        "scripts/seed.sh",
        ("soc",),
        ("soc",),
        environment_fixtures=(ScenarioEnvironmentFixture("STARTUP_TOKEN", "fixture"),),
        environment_grants=list(grants) if invalid == "shape" else grants,
    )
    bundle = SimpleNamespace(pack_identity=None if invalid == "unidentified" else _PACK)
    with pytest.raises(ScenarioStartupProviderError, match="provider-result-invalid"):
        _validated_plan(plan, bundle)
