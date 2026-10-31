"""Runtime-authority materialization regression tests (#956)."""

from __future__ import annotations

from pathlib import Path

import pytest
from raes.runtime_configuration import RuntimeConfiguration

from aptl.core.deployment._compose_node_generation import _operational_config
from aptl.core.deployment.docker_compose import DockerComposeBackend
from aptl.core.deployment.realization import (
    DeploymentImageRealization,
    DeploymentNodeRealization,
    DeploymentRealizationSpec,
)
from aptl.core.deployment.runtime_materialization import (
    SHARED_DOCKER_PROFILE,
    RuntimeMaterializationProfile,
    effective_runtime_contract_issues,
    qualify_runtime_materialization,
)
from aptl.core.scenario_bundle import PackIdentity
from aptl.runtime_authority import DeploymentDockerAuthorityAdmission


_DIGEST_A = "sha256:" + "a" * 64
_QUALIFIED_PROFILE = RuntimeMaterializationProfile(name="test-compose")


def _node(runtime: RuntimeConfiguration, *, image_backed: bool = True):
    node = DeploymentNodeRealization(
        address="provision.node.workload",
        name="workload",
        service_name="workload",
        container_name="aptl-workload",
        networks=("shared",),
        runtime=runtime,
    )
    images = (
        DeploymentImageRealization(
            address=node.address,
            service_name="workload",
            source_name="workload",
            source_version="workload@" + _DIGEST_A,
            image_ref="example/workload@" + _DIGEST_A,
            mode="pull",
            policy_rule="digest-pinned",
        ),
    ) if image_backed else ()
    return node, images


def _spec(
    runtime: RuntimeConfiguration,
    *,
    image_backed: bool = True,
    authority: bool = False,
) -> DeploymentRealizationSpec:
    node, images = _node(runtime, image_backed=image_backed)
    admissions = ()
    if authority:
        admissions = (
            DeploymentDockerAuthorityAdmission(
                node_address=node.address,
                service_name="workload",
                engine="docker",
                privilege_class="host_root_equivalent",
                endpoint_kind="unix_socket",
                endpoint_source="/var/run/docker.sock",
                endpoint_target="/var/run/docker.sock",
                endpoint_read_write=True,
                spawn_requirements=(),
                authority_id="authority",
                image_template_ids=("worker", "app"),
            ),
        )
    return DeploymentRealizationSpec(
        profiles=(),
        nodes=(node,),
        networks=(),
        images=images,
        docker_authority_admissions=admissions,
        pack_identity=PackIdentity("fixture", "1.0.0", _DIGEST_A),
    )


def test_compose_lowering_preserves_supported_runtime_security_fields() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {
            "linux_capabilities": {
                "add": ["CAP_NET_ADMIN"],
                "drop": ["CAP_CHOWN"],
            },
            "container": {
                "privileged": True,
                "read_only_rootfs": True,
                "shm_size": "64 MiB",
                "namespaces": {
                    "pid": "host",
                    "ipc": "private",
                    "userns": "host",
                    "uts": "host",
                    "cgroup": "private",
                },
                "devices": [
                    {
                        "host_path": "/dev/net/tun",
                        "container_path": "/dev/net/tun",
                        "permissions": "rwm",
                    }
                ],
                "device_cgroup_rules": ["c 10:200 rwm"],
                "seccomp_profile": "unconfined",
                "security_opt": ["no-new-privileges=false"],
                "cgroup_parent": "scenario.slice",
                "runtime_name": "runc",
                "group_add": ["1000"],
                "extra_hosts": [{"hostname": "db", "address": "10.0.0.5"}],
                "dns": ["10.0.0.2"],
                "dns_options": ["use-vc"],
                "dns_search": ["scenario.test"],
                "log_driver": "json-file",
                "log_options": {"max-size": "10m"},
            },
        }
    )

    config = _operational_config(runtime)

    assert config["cap_add"] == ["NET_ADMIN"]
    assert config["cap_drop"] == ["CHOWN"]
    assert config["privileged"] is True
    assert config["read_only"] is True
    assert config["pid"] == "host"
    assert config["ipc"] == "private"
    assert config["userns_mode"] == "host"
    assert config["uts"] == "host"
    assert config["cgroup"] == "private"
    assert config["devices"] == ["/dev/net/tun:/dev/net/tun:rwm"]
    assert config["device_cgroup_rules"] == ["c 10:200 rwm"]
    assert config["security_opt"] == [
        "no-new-privileges=false",
        "seccomp=unconfined",
    ]
    assert config["cgroup_parent"] == "scenario.slice"
    assert config["runtime"] == "runc"
    assert config["group_add"] == ["1000"]
    assert config["extra_hosts"] == ["db:10.0.0.5"]
    assert config["dns_opt"] == ["use-vc"]
    assert config["dns_search"] == ["scenario.test"]
    assert config["logging"] == {
        "driver": "json-file",
        "options": {"max-size": "10m"},
    }


def test_shared_daemon_accepts_faithfully_lowerable_privilege() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {"container": {"privileged": True}}
    )

    issues = qualify_runtime_materialization(
        _spec(runtime),
        profile=SHARED_DOCKER_PROFILE,
    )

    assert issues == ()


def test_shared_daemon_accepts_faithfully_lowerable_host_bind() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {
            "mounts": [
                {
                    "source_kind": "bind",
                    "source": "/etc",
                    "target": "/host-etc",
                    "read_only": True,
                }
            ]
        }
    )

    issues = qualify_runtime_materialization(
        _spec(runtime),
        profile=SHARED_DOCKER_PROFILE,
    )

    assert issues == ()


def test_effective_model_rejects_undeclared_host_bind_without_runtime_fields() -> None:
    runtime = RuntimeConfiguration.model_validate({})
    payload = {
        "services": {
            "workload": {
                "image": "example/workload",
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/",
                        "target": "/host",
                        "read_only": False,
                    }
                ],
            }
        }
    }

    issues = effective_runtime_contract_issues(
        payload,
        _spec(runtime),
        profile=SHARED_DOCKER_PROFILE,
    )

    assert len(issues) == 1
    assert issues[0].field == "runtime.mounts"
    assert "undeclared runtime authority" in issues[0].limitation


def test_compose_lowering_preserves_authored_mount_contract() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {
            "mounts": [
                {
                    "source_kind": "bind",
                    "source": "/scenario/input",
                    "target": "/input",
                    "read_only": True,
                    "propagation": "rprivate",
                },
                {
                    "source_kind": "volume",
                    "source": "scenario-data",
                    "target": "/data",
                },
                {"source_kind": "tmpfs", "target": "/scratch"},
            ]
        }
    )

    assert _operational_config(runtime)["volumes"] == [
        {
            "type": "bind",
            "source": "/scenario/input",
            "target": "/input",
            "read_only": True,
            "bind": {"propagation": "rprivate"},
        },
        {
            "type": "volume",
            "source": "scenario-data",
            "target": "/data",
            "read_only": False,
        },
        {"type": "tmpfs", "target": "/scratch", "read_only": False},
    ]


def test_generic_substrate_rejects_non_volume_mount_before_materialization() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {"mounts": [{"source_kind": "tmpfs", "target": "/scratch"}]}
    )

    issues = qualify_runtime_materialization(
        _spec(runtime, image_backed=False),
        profile=_QUALIFIED_PROFILE,
    )

    assert len(issues) == 1
    assert issues[0].field == "runtime.mounts[0]"
    assert "generic substrate" in issues[0].limitation


def test_generic_substrate_rejects_unimplemented_field_before_materialization() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {"container": {"privileged": True}}
    )

    issues = qualify_runtime_materialization(
        _spec(runtime, image_backed=False),
        profile=_QUALIFIED_PROFILE,
    )

    assert len(issues) == 1
    assert issues[0].field == "runtime.container.privileged"
    assert "generic substrate" in issues[0].limitation


def test_shared_profile_accepts_faithful_image_backed_authority() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {
            "container": {
                "privileged": True,
                "security_opt": ["seccomp=unconfined"],
                "namespaces": {"pid": "host"},
            },
            "linux_capabilities": {
                "add": ["CAP_SYS_ADMIN"],
                "drop": ["CAP_CHOWN"],
            },
        }
    )
    assert qualify_runtime_materialization(
        _spec(runtime), profile=SHARED_DOCKER_PROFILE
    ) == ()


def test_admission_does_not_rewrite_or_filter_authored_runtime() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {
            "container": {
                "privileged": True,
                "security_opt": ["seccomp=unconfined"],
                "read_only_rootfs": True,
            },
            "linux_capabilities": {
                "add": ["CAP_SYS_ADMIN"],
                "drop": ["CAP_CHOWN"],
            },
        }
    )
    spec = _spec(runtime, authority=True)
    before = runtime.model_dump(mode="json", by_alias=True)

    issues = qualify_runtime_materialization(
        spec,
        profile=SHARED_DOCKER_PROFILE,
    )

    assert issues == ()
    assert spec.nodes[0].runtime.model_dump(mode="json", by_alias=True) == before
    config = _operational_config(spec.nodes[0].runtime)
    assert config["privileged"] is True
    assert config["security_opt"] == ["seccomp=unconfined"]
    assert config["read_only"] is True
    assert config["cap_add"] == ["SYS_ADMIN"]
    assert config["cap_drop"] == ["CHOWN"]


def test_declared_raw_socket_authority_is_accepted_on_normal_lab_backend() -> None:
    runtime = RuntimeConfiguration.model_validate({})

    issues = qualify_runtime_materialization(
        _spec(runtime, authority=True),
        profile=SHARED_DOCKER_PROFILE,
    )

    assert issues == ()


def test_unsupported_compose_field_is_never_silently_dropped() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {"container": {"masked_paths": ["/proc/kcore"]}}
    )

    issues = qualify_runtime_materialization(
        _spec(runtime),
        profile=_QUALIFIED_PROFILE,
    )

    assert len(issues) == 1
    assert issues[0].field == "runtime.container.masked_paths"
    assert "Compose" in issues[0].limitation


@pytest.mark.parametrize("field", ["required", "effective", "process_overrides"])
def test_unimplemented_capability_dimensions_are_never_silently_dropped(
    field: str,
) -> None:
    value: object = ["CAP_NET_ADMIN"]
    if field == "process_overrides":
        value = [
            {
                "subject": {"name": "worker"},
                "add": ["CAP_NET_ADMIN"],
            }
        ]
    runtime = RuntimeConfiguration.model_validate(
        {"linux_capabilities": {field: value}}
    )

    issues = qualify_runtime_materialization(
        _spec(runtime),
        profile=_QUALIFIED_PROFILE,
    )

    assert len(issues) == 1
    assert issues[0].field == f"runtime.linux_capabilities.{field}"
    assert "faithful lowering" in issues[0].limitation


def test_runtime_qualification_precedes_ownership_and_mixed_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RuntimeConfiguration.model_validate(
        {"container": {"masked_paths": ["/proc/kcore"]}}
    )
    backend = DockerComposeBackend(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        backend,
        "_ensure_resource_ownership",
        lambda *args, **kwargs: calls.append("ownership"),
    )
    monkeypatch.setattr(
        backend,
        "_materialize_base_container_nodes",
        lambda *args, **kwargs: calls.append("materialize"),
    )

    result = backend.realize(_spec(runtime), scenario_root=tmp_path)

    assert result.success is False
    assert calls == []
    assert "node=provision.node.workload" in result.error
    assert "field=runtime.container.masked_paths" in result.error
    assert "backend=shared-docker" in result.error


def test_a_root_model_does_not_override_runtime_qualification(tmp_path, monkeypatch):
    """Only the generated scenario model is qualified before mutation."""

    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  workload:\n    image: example/workload\n",
        encoding="utf-8",
    )
    runtime = RuntimeConfiguration.model_validate(
        {"container": {"read_only_rootfs": True}}
    )
    backend = DockerComposeBackend(tmp_path)
    monkeypatch.setattr(
        backend, "_run", lambda *_args, **_kwargs: pytest.fail("read unused root model")
    )
    result = backend.qualify_runtime_materialization(_spec(runtime), scenario_root=tmp_path)
    assert result.success


def test_a_root_model_cannot_add_undeclared_host_authority(tmp_path, monkeypatch):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  workload:\n    image: example/workload\n"
        "    volumes: [/:/host]\n",
        encoding="utf-8",
    )
    backend = DockerComposeBackend(tmp_path)
    monkeypatch.setattr(
        backend, "_run", lambda *_args, **_kwargs: pytest.fail("read unused root model")
    )
    result = backend.qualify_runtime_materialization(
        _spec(RuntimeConfiguration.model_validate({})), scenario_root=tmp_path
    )
    assert result.success


def _companion_spec() -> DeploymentRealizationSpec:
    from dataclasses import replace

    from aptl.core.deployment.realization import DeploymentCompanionRealization

    spec = _spec(RuntimeConfiguration.model_validate({}))
    companion = DeploymentCompanionRealization(
        role="web",
        image=DeploymentImageRealization(
            address="provision.node.workload",
            service_name="workload-web",
            source_name="web",
            source_version="1",
            image_ref="example/web@" + _DIGEST_A,
            mode="pull",
            policy_rule="backend-open-profile",
        ),
        tmpfs=("/tmp:mode=1777",),
    )
    (node,) = spec.nodes
    return replace(spec, nodes=(replace(node, backend_companions=(companion,)),))


def test_effective_model_accepts_the_rendered_companion_contract() -> None:
    from aptl.core.deployment._compose_node_generation import (
        render_realization_compose,
    )

    spec = _companion_spec()

    issues = effective_runtime_contract_issues(
        render_realization_compose(spec), spec, profile=SHARED_DOCKER_PROFILE
    )

    assert issues == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("privileged", True),
        ("cap_add", ["NET_ADMIN"]),
        ("network_mode", "host"),
        ("read_only", False),
        ("user", "0"),
        ("volumes", [{"type": "bind", "source": "/", "target": "/host"}]),
    ],
)
def test_effective_model_refuses_added_companion_authority(field, value) -> None:
    """A backend companion has no authored runtime, so nothing may widen it (#1407)."""

    from aptl.core.deployment._compose_node_generation import (
        render_realization_compose,
    )

    spec = _companion_spec()
    payload = render_realization_compose(spec)
    payload["services"]["workload-web"][field] = value

    issues = effective_runtime_contract_issues(
        payload, spec, profile=SHARED_DOCKER_PROFILE
    )

    assert len(issues) == 1
    assert "backend companion authority" in issues[0].limitation


def test_effective_model_refuses_a_missing_companion() -> None:
    from aptl.core.deployment._compose_node_generation import (
        render_realization_compose,
    )

    spec = _companion_spec()
    payload = render_realization_compose(spec)
    del payload["services"]["workload-web"]

    issues = effective_runtime_contract_issues(
        payload, spec, profile=SHARED_DOCKER_PROFILE
    )

    assert len(issues) == 1
    assert "companion is absent" in issues[0].limitation
