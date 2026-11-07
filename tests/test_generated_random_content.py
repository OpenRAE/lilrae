"""Per-run generated values retain identity and reach their admitted content."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import Mock
import os
import re

import pytest
from raes import parse_sdl
from raes_contracts.planning import PlanScope
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.planner import plan

from aptl.backends.generated_content import (
    bind_generated_content,
    generated_content_delivered,
)
from aptl.core.deployment.backend import DeploymentBackend
from aptl.core.deployment._compose_content_mounts import image_node_content_override
from aptl.core.deployment.realization import (
    DeploymentRealizationSpec,
    DeploymentImageRealization,
    DeploymentNodeRealization,
)
from aptl.backends.raes_literal_content_realization import (
    resolve_literal_content_placement,
)
from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.backends.raes_realization_model import PlacementRealization
from aptl.backends.raes_stateful_realization import realize_stateful_resources
from aptl.core.deployment._compose_artifact_paths import artifact_source_path
from aptl.core.deployment.random_values import read_random_value, realize_random_value
from aptl.utils.pathsafe import PathContainmentError

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="POSIX no-follow artifact storage"
)


@pytest.fixture
def admitted():
    scenario = parse_sdl("""name: generated-content
nodes:
  worker:
    type: compute
    os: linux
generated_artifacts:
  flag:
    generator: random_value
    lifecycle: reuse_valid
    regeneration_scope: per_run
    random_value:
      alphabet: hex_lower
      length: 32
      format: {prefix: 'FLAG{', suffix: '}'}
    provenance: fixture
    outputs:
      - {name: value, path: flag.txt, sensitivity: secret}
content:
  flag-file:
    type: file
    target: worker
    path: /root/flag.txt
    sensitive: true
    text_from: {generated_artifact: flag, output: value}
""")
    execution = plan(
        compile_scenario_runtime_model(scenario),
        create_aptl_manifest(),
        scope=PlanScope(target_name="aptl", run_id="run-one"),
    )
    assert execution.is_valid, execution.diagnostics
    resources = list(execution.provisioning.resources.values())
    diagnostics = []
    artifacts, _ = realize_stateful_resources(resources, [], diagnostics)
    assert not diagnostics
    assert len(artifacts) == 1
    resource = next(
        item for item in resources if item.resource_type == "content-placement"
    )
    content, diagnostics = resolve_literal_content_placement(
        resource, resource.payload, "provision.node.worker"
    )
    assert not diagnostics
    placements = bind_generated_content(
        [
            PlacementRealization(
                address=resource.address,
                resource_type="content-placement",
                name="flag-file",
                target_address="provision.node.worker",
                target_node="worker",
                content=content,
            )
        ],
        artifacts,
        diagnostics,
    )
    assert not diagnostics
    return artifacts[0], placements[0].content


def test_retries_share_one_private_value_and_new_runs_get_a_fresh_value(
    tmp_path, admitted
):
    artifact, content = admitted
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: realize_random_value(tmp_path, artifact), range(4)))
    first = read_random_value(tmp_path, artifact)
    assert re.fullmatch(rb"FLAG\{[0-9a-f]{32}\}", first)
    assert (tmp_path / content.source_relpath).read_bytes() == first
    assert (tmp_path / content.source_relpath).stat().st_mode & 0o777 == 0o600
    realize_random_value(tmp_path, artifact)
    assert read_random_value(tmp_path, artifact) == first
    second = replace(artifact, scope_binding="run:run-two")
    realize_random_value(tmp_path, second)
    assert artifact_source_path(tmp_path, second) != artifact_source_path(
        tmp_path, artifact
    )
    assert read_random_value(tmp_path, second) != first
    assert first.decode() not in str(artifact.details()) + str(content.details())


def test_changed_recipe_in_the_same_run_is_refused_without_rotating(tmp_path, admitted):
    artifact, _ = admitted
    realize_random_value(tmp_path, artifact)
    first = read_random_value(tmp_path, artifact)
    changed = replace(
        artifact, random_value=artifact.random_value.model_copy(update={"length": 40})
    )
    with pytest.raises(ValueError, match="recipe changed"):
        realize_random_value(tmp_path, changed)
    assert read_random_value(tmp_path, artifact) == first


def test_corrupt_or_symlinked_generated_output_is_refused(tmp_path, admitted):
    artifact, content = admitted
    realize_random_value(tmp_path, artifact)
    output = tmp_path / content.source_relpath
    output.write_bytes(b"not-a-valid-generated-value")
    with pytest.raises(ValueError, match="does not match"):
        realize_random_value(tmp_path, artifact)
    output.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged")
    output.symlink_to(outside)
    with pytest.raises(PathContainmentError):
        realize_random_value(tmp_path, artifact)
    assert outside.read_bytes() == b"unchanged"


def test_generated_content_mount_and_native_readback_use_the_same_output(
    tmp_path, admitted
):
    artifact, content = admitted
    realize_random_value(tmp_path, artifact)
    node = DeploymentNodeRealization(
        address="provision.node.worker",
        name="worker",
        service_name="worker",
        container_name="worker",
        networks=(),
    )
    image = Mock(spec=DeploymentImageRealization, address=node.address)
    spec = DeploymentRealizationSpec(
        profiles=(), nodes=(node,), networks=(), images=(image,), content=(content,)
    )
    override = image_node_content_override(spec, tmp_path, tmp_path)
    mount = override["services"]["worker"]["volumes"][0]
    assert mount["source"] == str(tmp_path / content.source_relpath)
    assert mount["target"] == "/root/flag.txt"
    backend = Mock(spec=DeploymentBackend)
    backend.container_file_read.return_value = read_random_value(tmp_path, artifact)
    assert generated_content_delivered(backend, "worker", content, tmp_path)
    backend.container_file_read.return_value = b"different"
    assert not generated_content_delivered(backend, "worker", content, tmp_path)
    backend.container_file_read.return_value = None
    assert not generated_content_delivered(backend, "worker", content, tmp_path)
