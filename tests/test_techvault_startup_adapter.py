"""Content-identified startup enrichment for the released TechVault pack."""

from importlib import metadata
from importlib.resources import files
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import yaml

from aptl.backends.scenario_startup import (
    ENTRY_POINT_GROUP,
    ScenarioStartupProviderError,
    ScenarioStartupPlan,
    ScenarioStartupSelection,
    StartupHookContext,
    _safe_relative_script,
    observe_scenario_runtime_concerns,
    run_scenario_runtime,
    resolve_scenario_startup,
    select_scenario_startup,
)
from aptl.backends.scenario_startup_policy import (
    ScenarioComposeStartupPolicy,
    StartupHealthDependency,
    StartupHealthProbe,
    _validated_policy,
    _resolved_services as resolve_startup_policy,
    write_scenario_startup_override,
)
from aptl.backends.scenario_service_policy import (
    ScenarioComposeServicePolicy,
    ServiceFileMount,
    _resolved_services as resolve_service_policy,
    certificate_mount_aliases,
    write_scenario_service_override,
)
import pytest


def test_service_alias_rejects_linked_source(tmp_path):
    from aptl.backends.scenario_service_policy import _project_file
    from aptl.backends.scenario_startup import ScenarioStartupProviderError

    (tmp_path / "real").write_text("configuration")
    (tmp_path / "alias").symlink_to(tmp_path / "real")
    with pytest.raises(ScenarioStartupProviderError):
        _project_file(tmp_path, "alias")


from aptl.core.deployment.realization import (
    DeploymentImageRealization,
    DeploymentNodeRealization,
    DeploymentRealizationSpec,
)
from aptl.core.scenario_bundle import PackIdentity, ScenarioBundle, ScenarioSourceKind
from aptl_techvault.runtime_parameters import TECHVAULT_PACK_SET_DIGEST


def _bundle(*, digest: str = TECHVAULT_PACK_SET_DIGEST) -> ScenarioBundle:
    pack_root = Path(str(files("raes_env_packs") / "resources/packs/techvault"))
    return ScenarioBundle(
        identity="techvault",
        root=pack_root,
        sdl_path=pack_root / "sdl/techvault.sdl.yaml",
        source_kind=ScenarioSourceKind.ENV_PACK,
        pack_identity=PackIdentity("techvault", "6.5.1", digest),
    )


def _startup_spec(
    *, digest: str = TECHVAULT_PACK_SET_DIGEST
) -> DeploymentRealizationSpec:
    dependencies = {
        "worker": ("provision.node.search",),
        "app": (
            "provision.node.store",
            "provision.node.search",
            "provision.node.worker",
        ),
    }
    names = ("store", "search", "worker", "app")
    nodes = tuple(
        DeploymentNodeRealization(
            address=f"provision.node.{name}",
            name=name,
            service_name=name,
            container_name=f"aptl-{name}",
            networks=("security-net",),
            ordering_dependencies=dependencies.get(name, ()),
        )
        for name in names
    )
    images = tuple(
        DeploymentImageRealization(
            address=node.address,
            service_name=node.service_name or "",
            source_name=node.name,
            source_version="test",
            image_ref=f"example/{node.name}:test",
            mode="pull",
            policy_rule="test",
        )
        for node in nodes
    )
    return DeploymentRealizationSpec(
        profiles=("soc",),
        nodes=nodes,
        networks=(),
        images=images,
        pack_identity=PackIdentity("techvault", "6.5.1", digest),
    )


def test_qualified_techvault_policy_adds_no_health_override(tmp_path) -> None:
    assert write_scenario_startup_override(_startup_spec(), tmp_path) is None


def test_qualified_policy_waits_for_declared_healthy_dependencies(
    tmp_path, monkeypatch
) -> None:
    from aptl_techvault.startup import provider

    monkeypatch.setattr(
        provider,
        "compose_startup_policy",
        lambda: ScenarioComposeStartupPolicy(
            probes=(
                StartupHealthProbe("store", ("CMD", "store-ready")),
                StartupHealthProbe("search", ("CMD", "search-ready")),
                StartupHealthProbe("worker", ("CMD", "worker-ready")),
            ),
            dependencies=(
                StartupHealthDependency("worker", "search"),
                StartupHealthDependency("app", "store"),
                StartupHealthDependency("app", "search"),
                StartupHealthDependency("app", "worker"),
            ),
        ),
    )

    path = write_scenario_startup_override(_startup_spec(), tmp_path)

    assert path is not None
    services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]
    assert services["store"]["healthcheck"]["test"] == ["CMD", "store-ready"]
    assert services["worker"]["depends_on"]["search"] == {
        "condition": "service_healthy"
    }
    assert services["app"]["depends_on"] == {
        name: {"condition": "service_healthy"}
        for name in ("store", "search", "worker")
    }
    assert (
        write_scenario_startup_override(
            _startup_spec(digest="sha256:" + "0" * 64), tmp_path
        )
        is None
    )


def test_qualified_techvault_service_policy_binds_generated_tls_files(tmp_path) -> None:
    spec = _startup_spec()
    shuffle_nodes = tuple(
        DeploymentNodeRealization(
            address=f"provision.node.{name}",
            name=name,
            service_name=name,
            container_name=f"aptl-{name}",
            networks=("security-net",),
        )
        for name in ("shuffle-frontend", "shuffle-orborus")
    )
    shuffle_images = tuple(
        DeploymentImageRealization(
            address=node.address,
            service_name=node.service_name or "",
            source_name=node.name,
            source_version="test",
            image_ref=f"example/{node.name}:test",
            mode="pull",
            policy_rule="test",
        )
        for node in shuffle_nodes
    )
    spec = DeploymentRealizationSpec(
        profiles=spec.profiles,
        nodes=(*spec.nodes, *shuffle_nodes),
        networks=spec.networks,
        images=(*spec.images, *shuffle_images),
        pack_identity=spec.pack_identity,
    )
    for name in (
        "config/soc_certs/shuffle-frontend/server.pem",
        "config/soc_certs/shuffle-frontend/server.key",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("test", encoding="utf-8")

    resolver = lambda name: f"workspace-{name}"
    path = write_scenario_service_override(
        spec, tmp_path, container_name_for_semantic=resolver
    )
    assert path is not None
    services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]
    assert {item["target"] for item in services["shuffle-frontend"]["volumes"]} == {
        "/etc/nginx/fullchain.cert.pem",
        "/etc/nginx/privkey.pem",
    }
    assert services["shuffle-orborus"]["environment"] == {
        "ORBORUS_CONTAINER_NAME": "workspace-aptl-shuffle-orborus"
    }
    assert all(
        item["read_only"] is True
        for service in services.values()
        for item in service.get("volumes", ())
    )
    assert (
        write_scenario_service_override(
            _startup_spec(digest="sha256:" + "0" * 64), tmp_path
        )
        is None
    )


def test_service_policy_rejects_missing_or_escaping_files(
    tmp_path, monkeypatch
) -> None:
    from aptl_techvault.startup import provider

    monkeypatch.setattr(
        provider,
        "compose_service_policy",
        lambda: ScenarioComposeServicePolicy(
            mounts=(ServiceFileMount("app", "../outside", "/etc/app/x"),)
        ),
    )
    spec = _startup_spec()
    with pytest.raises(ScenarioStartupProviderError, match="result-invalid"):
        resolve_service_policy(spec, tmp_path)


def test_certificate_aliases_require_the_same_declared_source_and_consumer(
    tmp_path,
) -> None:
    names = (
        "config/soc_certs/shuffle-frontend/server.pem",
        "config/soc_certs/shuffle-frontend/server.key",
    )
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")
    expected = {
        "shuffle-frontend": {
            (
                str(tmp_path / "config/soc_certs/shuffle-frontend/server.pem"),
                "/opt/techvault/soc-certs/shuffle-frontend/server.pem",
            )
        },
    }

    aliases = certificate_mount_aliases(_startup_spec(), tmp_path, expected)

    assert aliases == {
        "shuffle-frontend": {
            (
                str(tmp_path / "config/soc_certs/shuffle-frontend/server.pem"),
                "/etc/nginx/fullchain.cert.pem",
            )
        },
    }


def test_startup_policy_cannot_add_undeclared_dependency_or_service() -> None:
    spec = _startup_spec()
    undeclared_edge = ScenarioComposeStartupPolicy(
        probes=(StartupHealthProbe("store", ("CMD", "true")),),
        dependencies=(StartupHealthDependency("worker", "store"),),
    )
    with pytest.raises(ScenarioStartupProviderError, match="result-invalid"):
        _validated_policy(undeclared_edge, spec)
    foreign_service = ScenarioComposeStartupPolicy(
        probes=(StartupHealthProbe("foreign", ("CMD", "true")),),
    )
    with pytest.raises(ScenarioStartupProviderError, match="result-invalid"):
        _validated_policy(foreign_service, spec)


@pytest.mark.parametrize(
    "probe",
    [
        StartupHealthProbe("app", ("CMD-SHELL", "true")),
        StartupHealthProbe("app", ("CMD",)),
        StartupHealthProbe("app", ("CMD", "true"), timeout_seconds=0),
        StartupHealthProbe("app", ("CMD", "true"), retries=True),
    ],
)
def test_startup_policy_rejects_malformed_health_probes(probe) -> None:
    policy = ScenarioComposeStartupPolicy(probes=(probe,))
    spec = _startup_spec()
    with pytest.raises(ScenarioStartupProviderError, match="result-invalid"):
        _validated_policy(policy, spec)


def test_startup_policy_rejects_duplicate_health_probe() -> None:
    probe = StartupHealthProbe("app", ("CMD", "true"))
    policy = ScenarioComposeStartupPolicy(probes=(probe, probe))
    spec = _startup_spec()
    with pytest.raises(ScenarioStartupProviderError, match="result-invalid"):
        _validated_policy(policy, spec)


def test_startup_values_are_the_pack_declared_account_credentials() -> None:
    """Each value comes from the admitted SDL, not from the adapter (#1273)."""

    from aptl.backends.raes_declared_credentials import scenario_accounts

    bundle = _bundle()
    plan = resolve_scenario_startup(bundle)
    accounts = scenario_accounts(bundle.sdl_path)
    values = {item.name: item.value for item in plan.environment_fixtures}

    def declared(account: str) -> tuple[str, str]:
        binding = accounts[account].credential_bindings[0]
        return accounts[account].username, binding.material.value

    expected = declared("wazuh-indexer-admin")
    assert values["INDEXER_USERNAME"] == expected[0]
    assert values["INDEXER_PASSWORD"] == expected[1]
    expected = declared("wazuh-manager-api")
    assert values["API_USERNAME"] == expected[0]
    assert values["API_PASSWORD"] == expected[1]
    expected = declared("shuffle-administrator")
    assert values["SHUFFLE_DEFAULT_USERNAME"] == expected[0]
    assert values["SHUFFLE_DEFAULT_PASSWORD"] == expected[1]
    source = Path(__file__).resolve().parents[1] / "src" / "aptl_techvault"
    adapter = (source / "account_environment.py").read_text(encoding="utf-8")
    assert values["INDEXER_PASSWORD"] not in adapter


def test_exact_release_resolves_seed_and_runtime_bindings() -> None:
    plan = resolve_scenario_startup(_bundle())

    assert plan is not None
    assert plan.seed_script == "scripts/seed-prime.sh"
    assert set(plan.required_profiles) == {
        "wazuh",
        "enterprise",
        "victim",
        "kali",
        "fileshare",
        "soc",
    }
    assert plan.activation_profiles == ("soc",)
    assert [(item.target, item.source) for item in plan.environment_aliases] == [
        ("ADMIN_KEY", "MISP_API_KEY")
    ]
    assert {item.name for item in plan.environment_fixtures} == {
        "INDEXER_USERNAME",
        "INDEXER_PASSWORD",
        "DASHBOARD_USERNAME",
        "DASHBOARD_PASSWORD",
        "API_USERNAME",
        "API_PASSWORD",
        "SHUFFLE_DEFAULT_USERNAME",
        "SHUFFLE_DEFAULT_PASSWORD",
    }
    assert {
        (item.variable, item.semantic_name) for item in plan.container_environment
    } >= {
        ("MISP_CONTAINER", "aptl-misp"),
        ("WAZUH_MANAGER_CONTAINER", "aptl-wazuh-manager"),
    }
    assert {item.server_id: item.environment_keys for item in plan.mcp_server_keys} == {
        "aptl-indexer": (
            "INDEXER_USERNAME",
            "INDEXER_PASSWORD",
            "API_USERNAME",
            "API_PASSWORD",
        ),
        "aptl-network": ("INDEXER_USERNAME", "INDEXER_PASSWORD"),
        "aptl-soar": ("SHUFFLE_API_KEY",),
        "aptl-threatintel": ("MISP_API_KEY",),
        "aptl-wazuh": (
            "INDEXER_USERNAME",
            "INDEXER_PASSWORD",
            "API_USERNAME",
            "API_PASSWORD",
        ),
    }


def test_changed_pack_digest_gets_no_startup_behavior() -> None:
    assert resolve_scenario_startup(_bundle(digest="sha256:" + "0" * 64)) is None


def test_admitted_provider_is_reused_by_all_runtime_hooks(
    monkeypatch, tmp_path
) -> None:
    from aptl.backends import scenario_startup

    calls: list[str] = []
    identity = _bundle().pack_identity
    assert identity is not None
    provider = SimpleNamespace(
        extension_api_version="1",
        supported_pack_id=identity.pack_id,
        supported_pack_versions=(identity.pack_version,),
        supported_pack_set_digests=(identity.set_digest,),
        resolve=lambda bundle: (
            calls.append("resolve")
            or ScenarioStartupPlan("scripts/seed.sh", ("soc",), ("soc",))
        ),
        compose_service_policy=lambda: (
            calls.append("service") or ScenarioComposeServicePolicy()
        ),
        compose_startup_policy=lambda: (
            calls.append("startup") or ScenarioComposeStartupPolicy()
        ),
        realize_runtime=lambda backend, nodes: calls.append("runtime") or [],
        observe_runtime=lambda backend, node: calls.append("observe") or {},
    )
    loads: list[str] = []
    entry = SimpleNamespace(
        name=identity.pack_id,
        load=lambda: loads.append("load") or provider,
    )
    monkeypatch.setattr(scenario_startup, "_entry_points", lambda: [entry])

    selection = select_scenario_startup(_bundle())
    assert selection.provider is provider
    assert loads == ["load"]
    monkeypatch.setattr(
        scenario_startup,
        "_entry_points",
        lambda: pytest.fail("startup provider was rediscovered"),
    )
    spec = replace(_startup_spec(), startup_selection=selection)

    assert resolve_service_policy(spec, tmp_path) == {}
    assert certificate_mount_aliases(spec, tmp_path, {}) == {}
    assert resolve_startup_policy(spec) == {}
    assert run_scenario_runtime(identity, object(), (), selection=selection) == []
    assert (
        observe_scenario_runtime_concerns(
            identity, object(), object(), selection=selection
        )
        == {}
    )
    assert calls == ["resolve", "service", "service", "startup", "runtime", "observe"]
    assert loads == ["load"]


def test_runtime_hook_only_runs_for_the_qualified_pack(monkeypatch) -> None:
    from aptl_techvault.startup import provider

    calls = []
    monkeypatch.setattr(
        provider,
        "realize_runtime",
        lambda backend, nodes: calls.append((backend, nodes)) or [],
    )
    backend = object()
    nodes = (object(),)

    assert run_scenario_runtime(_bundle().pack_identity, backend, nodes) == []
    assert calls == [(backend, nodes)]
    assert (
        run_scenario_runtime(
            _bundle(digest="sha256:" + "0" * 64).pack_identity,
            backend,
            nodes,
        )
        == []
    )
    assert calls == [(backend, nodes)]


def test_runtime_observation_only_runs_for_the_qualified_pack(monkeypatch) -> None:
    from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

    from aptl_techvault.startup import provider

    path = CONCERN_PAYLOAD_PATH["runtime-container-autoremove"]
    calls = []
    monkeypatch.setattr(
        provider,
        "observe_runtime",
        lambda backend, node: calls.append((backend, node)) or {path: False},
    )
    backend = object()
    node = object()

    assert observe_scenario_runtime_concerns(
        _bundle().pack_identity, backend, node
    ) == {path: False}
    assert (
        observe_scenario_runtime_concerns(
            _bundle(digest="sha256:" + "0" * 64).pack_identity, backend, node
        )
        == {}
    )
    assert calls == [(backend, node)]


@pytest.mark.parametrize(
    "path", ["/tmp/seed.sh", "a/../seed.sh", "a/./seed.sh", "a//seed.sh"]
)
def test_adapter_script_path_rejects_noncanonical_components(path: str) -> None:
    with pytest.raises(ScenarioStartupProviderError):
        _safe_relative_script(path)


def test_core_preparation_binds_operator_alias_without_scenario_import(
    tmp_path,
) -> None:
    from aptl.core.lab import _LabStartContext, _prepare_scenario_startup

    values = {
        "INDEXER_USERNAME": "indexer",
        "INDEXER_PASSWORD": "indexer-password",
        "API_USERNAME": "api",
        "API_PASSWORD": "api-password",
        "MISP_API_KEY": "opaque-misp-key",
    }
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    ctx = _LabStartContext(
        project_dir=tmp_path,
        skip_seed=False,
        raw_env=dict(values),
    )

    assert _prepare_scenario_startup(ctx, _bundle()) is None
    assert ctx.scenario_startup is not None
    assert ctx.raw_env["ADMIN_KEY"] == values["MISP_API_KEY"]


def test_core_preparation_rejects_a_missing_declared_operator_alias(tmp_path) -> None:
    from aptl.core.lab import _LabStartContext, _prepare_scenario_startup

    ctx = _LabStartContext(project_dir=tmp_path, skip_seed=False, raw_env={})

    failure = _prepare_scenario_startup(ctx, _bundle())

    assert failure is not None
    assert not failure.success
    assert "MISP_API_KEY" in failure.error
    assert ctx.scenario_startup is None
    assert (tmp_path / ".env").exists()


def test_seed_environment_uses_receipt_resolved_container_names(tmp_path) -> None:
    from unittest.mock import MagicMock

    from aptl.core.lab import _LabStartContext, _scenario_seed_environment

    plan = resolve_scenario_startup(_bundle())
    assert plan is not None
    backend = MagicMock()
    backend.docker_transport_environment.return_value = {}
    backend.container_inspect.side_effect = lambda semantic: {
        "Name": f"/workspace-{semantic.removeprefix('aptl-')}"
    }
    ctx = _LabStartContext(
        project_dir=tmp_path,
        skip_seed=False,
        backend=backend,
        raw_env={"MISP_API_KEY": "opaque"},
    )

    environment = _scenario_seed_environment(ctx, plan)

    assert environment["MISP_CONTAINER"] == "workspace-misp"
    assert environment["WAZUH_MANAGER_CONTAINER"] == "workspace-wazuh-manager"
    assert backend.container_inspect.call_count == len(plan.container_environment)


def test_startup_adapter_is_registered_outside_framework() -> None:
    entries = {
        entry.name: entry.value
        for entry in metadata.entry_points(group=ENTRY_POINT_GROUP)
    }

    assert entries["techvault"].startswith("aptl_techvault.")
    framework = Path(__file__).resolve().parents[1] / "src" / "aptl"
    offenders = {
        str(path.relative_to(framework))
        for path in framework.rglob("*.py")
        if "from aptl_techvault" in path.read_text(encoding="utf-8")
        or "import aptl_techvault" in path.read_text(encoding="utf-8")
    }
    assert offenders == set()


def test_runtime_selections_are_reported_value_free_or_flagged() -> None:
    from raes_contracts.realization_structure import validate_realization_value

    from aptl.backends.scenario_startup import (
        ScenarioRuntimeSelection,
        scenario_runtime_selection_details,
    )
    from aptl_techvault.startup import TechVaultStartupProvider

    def selection(provider):
        return ScenarioStartupSelection(identity=None, provider=provider, plan=None)

    reported = scenario_runtime_selection_details(selection(TechVaultStartupProvider()))

    assert reported == [
        {
            "node": "db",
            "subject": "database-client-authentication",
            "choice": TechVaultStartupProvider.runtime_selections[0].choice,
            "reference": "OpenRAE/env-packs#411",
        }
    ]
    assert validate_realization_value(
        {"scenario_runtime_selections": reported}
    ).conformant
    assert scenario_runtime_selection_details(None) == []
    assert scenario_runtime_selection_details(selection(SimpleNamespace())) == []
    malformed = SimpleNamespace(
        runtime_selections=[ScenarioRuntimeSelection("db", "x", "y")]
    )
    assert scenario_runtime_selection_details(selection(malformed)) == [
        {"error": "scenario runtime selections are malformed"}
    ]
