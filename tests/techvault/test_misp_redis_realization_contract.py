"""Issue #912: the released TechVault MISP and cache contract (#1700)."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from raes.parser import parse_sdl_file

from aptl.core.deployment._misp_cache_credential import (
    MISP_CACHE_CONFIG_OUTPUT,
    MISP_CACHE_PASSWORD_OUTPUT,
    MISP_CACHE_RUNTIME_CONFIG_DIR,
    MISP_CACHE_RUNTIME_CONFIG_PATH,
)
from aptl.core.deployment._misp_server_tls import (
    MISP_SERVER_TLS_MOUNT_DESTINATION,
)
from aptl.core.soc_ca import derive_soc_service_certs
from aptl_techvault.redis_acl_observation import _REDIS_ACL_READBACK_SCRIPT
from tests.techvault.pack import realize_techvault_pack, techvault_scenario_path
from tests.test_misp_redis_realization_contract import _enum, _misp_profile


def test_released_pack_authors_the_misp_and_cache_contract(tmp_path: Path) -> None:
    """The released pack retains OpenRAE/env-packs#280's MISP contract."""

    assert version("raes-env-packs") in SpecifierSet(">=7.0.0,<8")
    scenario = parse_sdl_file(techvault_scenario_path(tmp_path))

    application = scenario.nodes["misp"].runtime.platform_applications[0]
    bindings = {
        binding.binding_id: (binding.target_node_ref, binding.target_service_ref)
        for binding in application.upstream_bindings
    }
    assert bindings["misp-relational-store"] == ("misp-db", "mysql")
    assert bindings["misp-cache-store"] == ("misp-redis", "redis")

    settings = {setting.setting_id: setting.value for setting in application.settings}
    assert settings["misp-canonical-url"] == "https://misp.techvault.local"

    cache = scenario.nodes["misp-redis"].runtime
    datastore = cache.datastore_services[0]
    assert datastore.authorization_ref == "misp-redis-authorization"
    authorization = cache.app_authorizations[0]
    assert authorization.auth_enabled is True
    # The pack requires authentication without choosing the bytes: the
    # credential is explicitly value-free, which is what makes generating it a
    # legitimate backend choice rather than an invented one.
    principal = authorization.principals[0]
    assert _enum(principal.credential_classification) == "redacted"

    listener = scenario.nodes["misp"].runtime.service_listeners[0]
    assert listener.readiness.probe == "misp-authenticated-api-operation"
    assert "authenticated" in listener.readiness.criteria.lower()


@pytest.fixture(scope="module")
def realization(released_techvault_realization):
    return released_techvault_realization


def test_the_cache_is_authenticated_without_putting_the_secret_in_argv(realization):
    """The credential reaches the server through a file, never the command."""

    cache = next(node for node in realization.nodes if node.name == "misp-redis")
    command = list(cache.runtime.container.command)

    assert MISP_CACHE_RUNTIME_CONFIG_PATH.startswith("/run/")
    assert command == ["redis-server", MISP_CACHE_RUNTIME_CONFIG_PATH]
    assert list(cache.runtime.container.entrypoint) == [
        "/bin/sh",
        "-ec",
        f"install -d -m 0755 -o root -g root {MISP_CACHE_RUNTIME_CONFIG_DIR} && "
        "install -m 0400 -o redis -g redis /etc/redis/redis.conf "
        f'{MISP_CACHE_RUNTIME_CONFIG_PATH} && exec docker-entrypoint.sh "$@"',
        "--",
    ]
    assert _REDIS_ACL_READBACK_SCRIPT.count(MISP_CACHE_RUNTIME_CONFIG_PATH) == 2
    assert "/tmp/" not in " ".join(cache.runtime.container.entrypoint)
    # `--requirepass <value>` would work, and would also publish the credential
    # in the container's command line and in `docker inspect`.
    assert "--requirepass" not in command

    artifact = next(
        item
        for item in realization.generated_artifacts
        if item.name == "misp-cache-credential"
    )
    consumer = artifact.consumers[0]
    assert consumer.node_name == "misp-redis"
    assert consumer.access_mode == "read_only"
    assert consumer.selected_outputs == (MISP_CACHE_CONFIG_OUTPUT,)

    password = next(
        output
        for output in artifact.outputs
        if output.name == MISP_CACHE_PASSWORD_OUTPUT
    )
    # Producer-private means no consumer can bind it: MISP receives the value
    # through environment delivery instead.
    assert password.disposition == "producer_private"
    delivery = artifact.environment_consumers[0]
    assert delivery.node_name == "misp"
    assert delivery.environment_variable == "REDIS_PASSWORD"


def test_misp_receives_the_authored_identity_not_a_backend_default(realization):
    """BASE_URL comes from the authored setting, not from `localhost`."""

    misp = next(node for node in realization.nodes if node.name == "misp")
    environment = {item.name: item for item in misp.runtime.environment}

    assert environment["BASE_URL"].value == "https://misp.techvault.local"
    assert environment["REDIS_HOST"].value == "misp-redis"
    # The generated cache credential is bound by reference and carries no value
    # in the plan.
    assert environment["REDIS_PASSWORD"].value == ""
    assert _enum(environment["REDIS_PASSWORD"].value_classification) == "redacted"
    # The operator supplies the admin key; it is never a fixture.
    assert _enum(environment["ADMIN_KEY"].value_classification) == "operator_secret"
    assert environment["ADMIN_KEY"].value == ""


def test_the_leaf_is_delivered_where_the_selected_image_reads_it(realization):
    """A mounted certificate the image never reads is not an activated one."""

    artifact = next(
        item
        for item in realization.generated_artifacts
        if item.name == "misp-server-tls"
    )
    consumer = artifact.consumers[0]

    assert consumer.node_name == "misp"
    assert consumer.mount_destination == MISP_SERVER_TLS_MOUNT_DESTINATION
    assert consumer.access_mode == "read_only"
    assert sorted(output.path for output in artifact.outputs) == ["cert.pem", "key.pem"]
    # The pack produces the material; this delivery must not run before it.
    # The reference is canonicalized to the realized address at merge, because
    # stateful validation, cycle detection and execution all compare exact
    # addresses -- the SDL shorthand the profile writes would pass execution
    # ordering and then be rejected by preflight.
    assert artifact.ordering_dependencies == (
        "provision.generated-artifact.techvault-soc-certificates",
    )
    # The pack's own neutral delivery is untouched and still authoritative.
    bundle = next(
        item
        for item in realization.generated_artifacts
        if item.name == "techvault-soc-certificates"
    )
    misp_consumer = next(item for item in bundle.consumers if item.node_name == "misp")
    assert misp_consumer.mount_destination == "/opt/techvault/soc-certs"


def test_the_certificate_covers_the_authored_host(realization):
    """A lab CA is useless if the leaf omits the name consumers are told to use."""

    from aptl.core.deployment._authored_service_hosts import authored_service_hosts

    hosts = authored_service_hosts(realization)
    assert "misp.techvault.local" in hosts["misp"]

    certs = derive_soc_service_certs(("lab-ca.pem", "misp/server.pem"), hosts)
    misp = next(cert for cert in certs if cert.name == "misp")
    assert "misp.techvault.local" in misp.sans
    assert "misp" in misp.sans


def test_the_released_misp_version_selects_its_pinned_image(realization):
    """The pack's MISP version selects the one reviewed MISP pin (#1407).

    MISP 2.5.44 images carry PHP that is vulnerable to CVE-2026-109618 and
    CVE-2026-109619, so the pack moved to 2.5.50. The selector matches the
    declared version exactly; a stale profile leaves MISP unselectable.
    """

    misp = next(node for node in realization.nodes if node.name == "misp")
    profile = _misp_profile()

    assert profile.selector is not None
    assert profile.selector.version == profile.source_version == "2.5.50"
    assert profile.profile_id == "misp-2.5.50"
    assert misp.image.image_ref == profile.image_ref


@pytest.mark.integration
def test_stateful_preflight_accepts_the_delivery_dependency(tmp_path):
    """Execution ordering is not the only thing that reads the dependency.

    `stateful_realization_errors` validates every ordering reference against
    exact realized addresses *before* any artifact runs, so a reference that
    only the execution-time resolver understands stops the Compose pipeline at
    preflight and never reaches the ordering this test's sibling covers.
    """

    from aptl.core.deployment._compose_stateful_graph import stateful_realization_errors

    realization = realize_techvault_pack(tmp_path)
    delivery = next(
        item
        for item in realization.generated_artifacts
        if item.name == "misp-server-tls"
    )
    addresses = {item.address for item in realization.generated_artifacts}

    assert set(delivery.ordering_dependencies) <= addresses
    spec = realization.deployment_spec(sorted(realization.profiles))
    assert stateful_realization_errors(spec, local_artifacts=True) == []
