"""Issue #912: consume MISP/Redis's released contract without post-start repair."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import re

import pytest
import yaml

from aptl.backends._raes_backend_implementation_catalog import (
    BACKEND_IMPLEMENTATION_PROFILES,
)
from aptl.core.deployment._compose_stateful_artifact_helpers import (
    read_generated_output,
)
from aptl.core.deployment._compose_stateful_constants import SOC_CERT_PROFILE
from aptl.core.deployment._misp_cache_credential import (
    MISP_CACHE_CONFIG_OUTPUT,
    MISP_CACHE_CREDENTIAL_PROFILE,
    MISP_CACHE_PASSWORD_OUTPUT,
    realize_misp_cache_credential,
)
from aptl.core.deployment._misp_server_tls import (
    MISP_SERVER_TLS_PROFILE,
    realize_misp_server_tls,
)
from aptl.core.deployment.realization import (
    DeploymentGeneratedArtifactOutput,
    DeploymentGeneratedArtifactRealization,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _enum(value: object) -> object:
    return getattr(value, "value", value)


# --------------------------------------------------------------------------
# The released pack is what unblocks this issue; assert what it now authors.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# What APTL selects under that contract.
# --------------------------------------------------------------------------


def _misp_profile():
    return next(
        profile
        for profile in BACKEND_IMPLEMENTATION_PROFILES
        if profile.source_name == "ghcr.io/misp/misp-docker/misp-core"
    )


def test_compose_runs_the_same_misp_image_the_catalog_selects():
    """The Compose service and the catalog cannot pin different MISP images."""

    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text())

    assert compose["services"]["misp"]["image"] == _misp_profile().image_ref


def test_unrelated_https_settings_do_not_expand_certificate_identity():
    """A webhook or documentation URL is not the node's service identity."""

    from aptl.core.deployment._authored_service_hosts import authored_service_hosts

    setting = SimpleNamespace(
        setting_id="incident-webhook-url",
        value="https://collector.example.invalid/hook",
    )
    runtime = SimpleNamespace(
        platform_applications=(SimpleNamespace(settings=(setting,)),)
    )
    realization = SimpleNamespace(
        nodes=(SimpleNamespace(name="misp", runtime=runtime),)
    )

    assert authored_service_hosts(realization) == {}


# --------------------------------------------------------------------------
# The producers.
# --------------------------------------------------------------------------


def _cache_artifact() -> DeploymentGeneratedArtifactRealization:
    return DeploymentGeneratedArtifactRealization(
        address="backend.generated-artifact.misp-cache-credential",
        name="misp-cache-credential",
        generator="rendered_config",
        lifecycle="reuse_valid",
        provenance=MISP_CACHE_CREDENTIAL_PROFILE,
        outputs=(
            DeploymentGeneratedArtifactOutput(
                name=MISP_CACHE_PASSWORD_OUTPUT,
                path="cache-password",
                sensitivity="secret",
                disposition="producer_private",
            ),
            DeploymentGeneratedArtifactOutput(
                name=MISP_CACHE_CONFIG_OUTPUT,
                path="redis.conf",
                sensitivity="secret",
            ),
        ),
        consumers=(),
    )


def _cache_paths(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / ".aptl/realization/misp-cache-credential"
    return root / "cache-password", root / "redis.conf"


def _cache_acl_token(config_file: Path) -> str | None:
    """Inspect the ACL shape without exposing a generated credential on failure."""

    match = re.fullmatch(
        r"user default reset on >([A-Za-z0-9_-]{43,128}) "
        r"~\* \+@read \+@write \+@connection \+@transaction -@dangerous\n"
        r"appendonly no\nmaxmemory-policy noeviction\n",
        config_file.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def test_the_cache_credential_is_generated_owner_only_and_reused(tmp_path):
    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is None
    password_file, config_file = _cache_paths(tmp_path)

    password = password_file.read_text(encoding="utf-8").strip()
    assert password
    credential_matches = _cache_acl_token(config_file) == password
    assert credential_matches
    assert password_file.stat().st_mode & 0o777 == 0o600
    assert config_file.stat().st_mode & 0o777 == 0o600
    # Redis parses its config by whitespace, so a credential with a space in it
    # would silently change the directive rather than the value.
    assert not any(character.isspace() for character in password)

    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is None
    assert password_file.read_text(encoding="utf-8").strip() == password


def test_a_drifted_cache_config_is_regenerated_rather_than_reused(tmp_path):
    """Two ends authenticating with different values is worse than neither."""

    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is None
    password_file, config_file = _cache_paths(tmp_path)
    original = password_file.read_text(encoding="utf-8").strip()
    config_file.write_text("requirepass something-else\n", encoding="utf-8")

    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is None

    regenerated = password_file.read_text(encoding="utf-8").strip()
    assert regenerated != original
    credential_matches = _cache_acl_token(config_file) == regenerated
    assert credential_matches


@pytest.mark.parametrize("rewrite", ["  {key}\n", "{key}\r\n"], ids=["padded", "crlf"])
def test_a_padded_cache_password_is_regenerated_rather_than_reused(tmp_path, rewrite):
    """MISP would receive the padding while redis.conf holds the bare token (#966)."""

    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is None
    password_file, config_file = _cache_paths(tmp_path)
    original = password_file.read_bytes().removesuffix(b"\n").decode()
    password_file.write_bytes(rewrite.format(key=original).encode())

    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is None

    delivered = read_generated_output(tmp_path, password_file)
    credential_matches = _cache_acl_token(config_file) == delivered
    assert credential_matches
    assert delivered != original


def test_a_symlinked_cache_output_is_never_reused(tmp_path):
    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is None
    password_file, _config_file = _cache_paths(tmp_path)
    outside = tmp_path / "outside-password"
    outside.write_text(password_file.read_text(encoding="utf-8"), encoding="utf-8")
    password_file.unlink()
    password_file.symlink_to(outside)

    assert realize_misp_cache_credential(_cache_artifact(), tmp_path) is not None


def test_a_cache_artifact_off_its_contract_is_refused(tmp_path):
    artifact = DeploymentGeneratedArtifactRealization(
        **{**_cache_artifact().__dict__, "lifecycle": "replace"}
    )
    assert realize_misp_cache_credential(artifact, tmp_path) is not None


def _tls_artifact() -> DeploymentGeneratedArtifactRealization:
    return DeploymentGeneratedArtifactRealization(
        address="backend.generated-artifact.misp-server-tls",
        name="misp-server-tls",
        generator="rendered_config",
        lifecycle="reuse_valid",
        provenance=MISP_SERVER_TLS_PROFILE,
        outputs=(
            DeploymentGeneratedArtifactOutput(
                name="server-certificate", path="cert.pem", sensitivity="public"
            ),
            DeploymentGeneratedArtifactOutput(
                name="server-private-key", path="key.pem", sensitivity="secret"
            ),
        ),
        consumers=(),
    )


def _stage_bundle(tmp_path: Path, certificate: str, key: str) -> None:
    bundle = tmp_path / "config/soc_certs/misp"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "server.pem").write_text(certificate, encoding="utf-8")
    (bundle / "server.key").write_text(key, encoding="utf-8")


def test_the_leaf_is_staged_under_the_names_the_image_reads(tmp_path):
    _stage_bundle(tmp_path, "CERTIFICATE\n", "PRIVATE KEY\n")

    assert realize_misp_server_tls(_tls_artifact(), tmp_path) is None

    root = tmp_path / ".aptl/realization/misp-server-tls"
    assert (root / "cert.pem").read_text(encoding="utf-8") == "CERTIFICATE\n"
    assert (root / "key.pem").read_text(encoding="utf-8") == "PRIVATE KEY\n"
    # nginx in the web companion runs as uid 101 (#1407): the key is readable
    # across the bind mount, and the owner-only root keeps other users out.
    assert (root / "key.pem").stat().st_mode & 0o777 == 0o644
    assert root.stat().st_mode & 0o777 == 0o700


def test_an_owner_only_copy_from_an_earlier_start_becomes_readable(tmp_path):
    """Unchanged bytes do not excuse a stale mode (#1407).

    Copies staged before the web companion existed are 0600, which uid 101
    cannot read. Restaging the same leaf must still widen the copy.
    """

    _stage_bundle(tmp_path, "CERTIFICATE\n", "PRIVATE KEY\n")
    assert realize_misp_server_tls(_tls_artifact(), tmp_path) is None
    key = tmp_path / ".aptl/realization/misp-server-tls/key.pem"
    key.chmod(0o600)

    assert realize_misp_server_tls(_tls_artifact(), tmp_path) is None

    assert key.stat().st_mode & 0o777 == 0o644


def test_a_rotated_leaf_replaces_the_staged_copy(tmp_path):
    """A stale copy would keep serving a certificate the bundle has retired."""

    _stage_bundle(tmp_path, "FIRST\n", "FIRST KEY\n")
    assert realize_misp_server_tls(_tls_artifact(), tmp_path) is None
    _stage_bundle(tmp_path, "SECOND\n", "SECOND KEY\n")

    assert realize_misp_server_tls(_tls_artifact(), tmp_path) is None

    root = tmp_path / ".aptl/realization/misp-server-tls"
    assert (root / "cert.pem").read_text(encoding="utf-8") == "SECOND\n"


def test_a_missing_bundle_fails_closed_rather_than_staging_nothing(tmp_path):
    assert realize_misp_server_tls(_tls_artifact(), tmp_path) is not None


def test_a_symlinked_bundle_leaf_is_not_staged(tmp_path):
    _stage_bundle(tmp_path, "CERTIFICATE\n", "PRIVATE KEY\n")
    key = tmp_path / "config/soc_certs/misp/server.key"
    outside = tmp_path / "outside-key"
    outside.write_text("PRIVATE KEY\n", encoding="utf-8")
    key.unlink()
    key.symlink_to(outside)

    assert realize_misp_server_tls(_tls_artifact(), tmp_path) is not None


# --------------------------------------------------------------------------
# The mutation is gone.
# --------------------------------------------------------------------------


def test_no_post_realization_misp_or_cache_repair_script_survives():
    """The obsolete container-recreating path is absent from the installed assets."""

    assert not (PROJECT_ROOT / "scripts" / "envpack-soar-fixups.sh").exists()
    seed = (PROJECT_ROOT / "scripts" / "seed-prime.sh").read_text(encoding="utf-8")
    assert "envpack-soar-fixups.sh" not in seed


# --------------------------------------------------------------------------
# Producers must run in dependency order, not address order.
# --------------------------------------------------------------------------


def test_the_leaf_is_staged_after_the_bundle_that_produces_it(tmp_path, monkeypatch):
    """The whole prerequisite pass, not the producer in isolation.

    The realization spec sorts artifacts by address, and
    `backend.generated-artifact.misp-server-tls` sorts before
    `provision.generated-artifact.range-soc-certificates`. Iterating that
    order stages the leaf before the bundle exists, so a fresh realization root
    fails at startup. Only running the real pass catches that.
    """

    from aptl.core.deployment.docker_compose import DockerComposeBackend

    backend = DockerComposeBackend(tmp_path, project_name="aptl-test")
    order: list[str] = []

    def _record(_self, artifact, scenario_root, realization):
        order.append(artifact.name)
        if artifact.name == "misp-server-tls":
            bundle = scenario_root / "config/soc_certs/misp"
            assert bundle.is_dir(), "leaf staged before its producer ran"
        elif artifact.name == "range-soc-certificates":
            target = scenario_root / "config/soc_certs/misp"
            target.mkdir(parents=True, exist_ok=True)
            (target / "server.pem").write_text("CERT\n", encoding="utf-8")
            (target / "server.key").write_text("KEY\n", encoding="utf-8")
        return None

    monkeypatch.setattr(
        DockerComposeBackend, "_realize_one_generated_artifact", _record
    )
    realization = _ordering_spec()

    assert backend._realize_stateful_prerequisites(realization, tmp_path) is None
    assert order.index("range-soc-certificates") < order.index("misp-server-tls")


def _ordering_spec():
    from aptl.core.deployment.realization import DeploymentRealizationSpec

    def artifact(address, name, deps=()):
        return DeploymentGeneratedArtifactRealization(
            address=address,
            name=name,
            generator="certificate_bundle"
            if "certificates" in name
            else "rendered_config",
            lifecycle="reuse_valid",
            provenance=SOC_CERT_PROFILE,
            outputs=(),
            consumers=(),
            ordering_dependencies=deps,
        )

    return DeploymentRealizationSpec(
        profiles=(),
        nodes=(),
        networks=(),
        generated_artifacts=(
            artifact(
                "backend.generated-artifact.misp-server-tls",
                "misp-server-tls",
                ("provision.generated-artifact.range-soc-certificates",),
            ),
            artifact(
                "provision.generated-artifact.range-soc-certificates",
                "range-soc-certificates",
            ),
        ),
    )


@pytest.mark.parametrize("producer_count", [0, 1, 2])
def test_tls_delivery_dependency_uses_one_admitted_producer(producer_count):
    from dataclasses import replace
    from aptl.backends.raes_realization import _merge_backend_generated_artifacts
    from aptl.core.deployment._compose_stateful_constants import SOC_CERT_PROFILE
    from aptl.core.deployment.realization import DeploymentStatefulConsumer
    target = DeploymentStatefulConsumer(
        target_address='provision.node.misp', node_name='misp', service_name='misp',
        mount_destination='/opt/certificates', access_mode='read_only',
        selected_outputs=('misp-certificate', 'misp-private-key'),
    )
    source = DeploymentGeneratedArtifactRealization(
        address='provision.generated-artifact.independent-certificates',
        name='independent-certificates', generator='certificate_bundle',
        lifecycle='reuse_valid', provenance=SOC_CERT_PROFILE,
        outputs=(), consumers=(target,),
    )
    delivery = replace(_tls_artifact(), consumers=(target,))
    diagnostics = []
    producers = [replace(source, name=f"certificates-{index}", address=f"provision.generated-artifact.certificates-{index}") for index in range(producer_count)]
    merged = _merge_backend_generated_artifacts(producers, [SimpleNamespace(backend_generated_artifacts=(delivery,))], diagnostics)
    if producer_count == 1:
        assert diagnostics == []
        assert merged[-1].ordering_dependencies == (producers[0].address,)
    else:
        assert merged == producers
        assert [item.code for item in diagnostics] == ["aptl.provisioner.backend-artifact-source-ambiguous"]
