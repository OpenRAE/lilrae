"""Scoped capability admission and native authority under a shared policy."""

from dataclasses import replace
from threading import Barrier, Event
from unittest.mock import Mock

import pytest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import participant_tool_support_diagnostics

from aptl.backends.raes_manifest import create_aptl_manifest
from aptl.workbench.process import AgentExecutionError
from tests.lilrae_tool_fixture import tool_bindings, tool_scenario
from tests.test_lilrae_concurrent_participants import manager_for
from tests.test_lilrae_participant_tools import result
from tests.test_lilrae_tool_runtime import Controller


def scoped_scenario(selector="participant_refs"):
    authored = tool_scenario()
    behavior = authored.behavior_specifications["duel"]
    original = behavior.tool_affordances.pop("native")
    for role in ("red", "blue"):
        behavior.tool_affordances[role] = original.model_copy(
            update={selector: [role], "action_contract_refs": ["native-" + role]},
            deep=True,
        )
        authored.action_contracts["native-" + role] = authored.action_contracts[
            "native"
        ].model_copy(deep=True)
        behavior.action_contract_refs.append("native-" + role)
        authored.agents[role].actions.append("native-" + role)
    boundary = authored.observation_boundaries["red"]
    old = "behavior_specifications.duel.tool_affordances.native"
    refs = [
        f"behavior_specifications.duel.tool_affordances.{r}" for r in ("red", "blue")
    ]
    boundary.observable_refs = [r for r in boundary.observable_refs if r != old] + refs
    rule = boundary.view_rules[0]
    boundary.view_rules = [
        rule.model_copy(update={"information_ref": ref}) for ref in refs
    ]
    return authored


def installed_tools(controllers, authored):
    model = compile_runtime_model(authored)
    installed = []
    for role, item in zip(controllers, tool_bindings(controllers), strict=True):
        action = "participant.action-contract.native-" + role
        tool = item.tool_bindings[0]
        installed.append(
            replace(
                item,
                tool_bindings=(
                    replace(
                        tool,
                        tool_affordance_address=tool.tool_affordance_address.rsplit(
                            ".", 1
                        )[0]
                        + "."
                        + role,
                        action_contract_digest=canonical_json_digest(
                            model.action_contracts[action].spec
                        ),
                        execution_binding=replace(
                            tool.execution_binding,
                            binding_id="tool-" + role,
                            action_contract_address=action,
                        ),
                    ),
                ),
            )
        )
    return tuple(installed)


@pytest.mark.parametrize("selector", ["participant_refs", "participant_role_refs"])
@pytest.mark.parametrize("first", ["red", "blue"])
def test_scoped_tools_preserve_authority_and_history(selector, first):
    rendezvous, finished = Barrier(2, timeout=30), Event()
    effects, completed, forbidden = [], [], Mock()

    class Controller:
        def __init__(self, role):
            self.role = role

        def __call__(self, action, cancellation):
            pytest.fail("scoped executor requires a tool session")

        def invoke_with_tools(self, action, cancellation, tools):
            own = ("aptl-red", "kali_run_command", {"command": "id"})
            peer = (
                "aptl-wazuh",
                "wazuh_api_request",
                {"endpoint": "/agents", "method": "GET"},
            )
            if self.role == "blue":
                own, peer = peer, own
            with pytest.raises(AgentExecutionError):
                tools.invoke(*peer, "peer", forbidden)
            rendezvous.wait()
            if self.role != first:
                assert finished.wait(30)
            tools.invoke(
                *own, "own", lambda args: effects.append((self.role, args)) or result()
            )
            completed.append(self.role)
            if self.role == first:
                finished.set()
            return self.role + " scoped observation"

    controllers = {role: Controller(role) for role in ("red", "blue")}
    authored = scoped_scenario(selector)
    installed = installed_tools(controllers, authored)
    manifest = create_aptl_manifest(autonomous_bindings=installed)
    backend_manifest_v2_model(manifest)
    assert not participant_tool_support_diagnostics(
        compile_runtime_model(authored), manifest
    )
    manager, _ = manager_for(installed)
    with manager:
        plan = manager.plan(authored)
        assert not plan.diagnostics, plan.diagnostics
        applied = manager.apply(plan)
        assert applied.success, applied.diagnostics
        for role in controllers:
            history = manager.snapshot.participant_behavior_history[
                "participant.behavior." + role
            ]
            assert role + " scoped observation" in str(list(history))
            assert any(row.get("invocation_tool_context") for row in history)
    assert completed == [first, "blue" if first == "red" else "red"]
    assert sorted(role for role, _ in effects) == ["blue", "red"]
    forbidden.assert_not_called()


def test_tool_free_installation_does_not_claim_scoped_support():
    from tests.test_lilrae_concurrent_participants import bindings

    for installed in ((), bindings({"red": lambda *args: "unused"})):
        capability = create_aptl_manifest(
            autonomous_bindings=installed
        ).participant_runtime
        assert "scoped_tool_affordances" not in capability.supported_behavior_features
        assert not any(
            row.feature == "scoped_tool_affordances"
            for row in capability.feature_support
        )


@pytest.mark.parametrize(
    "claim",
    ["strength", "feature", "unsupported", "contracts", "capacity", "semantics"],
)
def test_false_claims_fail_public_gate_before_effects(claim):
    authored = scoped_scenario()
    native = Mock(spec=Controller("red"))
    installed = installed_tools({"red": native, "blue": native}, authored)
    manifest = create_aptl_manifest(autonomous_bindings=installed)
    from raes_backend_protocols.manifest import (
        backend_manifest_payload,
    )
    from raes_contracts.contracts import BackendManifestV2Model

    payload = backend_manifest_payload(manifest)
    capability = payload["capabilities"]["participant_runtime"]
    scoped = "scoped_tool_affordances"
    entry = next(
        row for row in capability["feature_support"] if row["feature"] == scoped
    )
    if claim == "strength":
        capability["feature_support"].remove(entry)
    elif claim == "feature":
        capability["supported_behavior_features"].remove(scoped)
    elif claim == "unsupported":
        capability["supported_behavior_features"].remove(scoped)
        capability["feature_support"].remove(entry)
    elif claim == "capacity":
        capability["tool_profiles"]["max_bindings_per_profile"] = 1
    elif claim == "semantics":
        capability["tool_profiles"]["semantic_versions"] = []
    else:
        payload["supported_contract_versions"] = []
    if claim in {"unsupported", "capacity"}:
        BackendManifestV2Model.model_validate(payload)
        runtime = manifest.participant_runtime
        if claim == "unsupported":
            runtime = replace(
                runtime,
                supported_behavior_features=runtime.supported_behavior_features
                - {scoped},
                feature_support=tuple(
                    row for row in runtime.feature_support if row.feature != scoped
                ),
            )
        else:
            runtime = replace(
                runtime,
                tool_profiles=runtime.tool_profiles.model_copy(
                    update={"max_bindings_per_profile": 1}
                ),
            )
        changed = replace(
            manifest,
            capabilities=replace(manifest.capabilities, participant_runtime=runtime),
        )
        diagnostics = participant_tool_support_diagnostics(
            compile_runtime_model(authored), changed
        )
        assert any(
            row.code == "participant.tool-support-insufficient" for row in diagnostics
        )
    else:
        with pytest.raises(ValueError):
            BackendManifestV2Model.model_validate(payload)
    native.assert_not_called()


@pytest.mark.parametrize("mismatch", ["peer", "digest", "target"])
def test_scoped_installed_mismatch_refuses_before_native_work(mismatch):
    authored, native = scoped_scenario(), Mock(spec=Controller("red"))
    installed = installed_tools({"red": native, "blue": native}, authored)
    item = installed[0]
    tool = item.tool_bindings[0]
    if mismatch == "peer":
        tool = installed[1].tool_bindings[0]
    elif mismatch == "digest":
        tool = replace(tool, action_contract_digest="sha256:" + "0" * 64)
    else:
        tool = replace(
            tool,
            execution_binding=replace(
                tool.execution_binding,
                target_addresses=("provision.node.other.service.http",),
            ),
        )
    installed = (replace(item, tool_bindings=(tool,)), installed[1])
    manager, _ = manager_for(installed)
    with manager:
        plan = manager.plan(authored)
        assert any(
            row.code == "lilrae.tool-binding-refused" for row in plan.diagnostics
        )
        assert not manager.apply(plan).success
    native.assert_not_called()


def qualify_scoped_wheel(tmp_path, *, source_root=None):
    import hashlib
    import json
    import subprocess
    import sys
    from pathlib import Path
    from tests.opencode_fixture import install_wheel

    installed = install_wheel(tmp_path, source_root=source_root)
    repo = Path(__file__).resolve().parents[1]
    script = """
import sys
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
import aptl
assert Path(aptl.__file__).resolve().is_relative_to(Path(sys.argv[1]))
from tests.test_lilrae_scoped_tools import scoped_scenario, installed_tools, test_scoped_tools_preserve_authority_and_history
from tests.test_lilrae_tool_runtime import Controller
from aptl.backends.raes import create_aptl_runtime_target, RuntimeTargetOptions
from aptl.core.scenario_bundle import project_tree_bundle
from aptl.core.config import AptlConfig
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import participant_tool_support_diagnostics
from raes_backend_protocols.manifest import backend_manifest_v2_model
from unittest.mock import Mock
root = Path.cwd()
authored = scoped_scenario()
bindings = installed_tools({r: Controller(r) for r in ("red", "blue")}, authored)
backend = Mock()
target = create_aptl_runtime_target(project_dir=root, config=AptlConfig(lab={"name": "scoped-test"}), backend=backend, bundle=project_tree_bundle(root, root / "scoped.sdl.yaml"), options=RuntimeTargetOptions(autonomous_bindings=bindings))
backend_manifest_v2_model(target.manifest)
assert not participant_tool_support_diagnostics(compile_runtime_model(authored), target.manifest)
assert not target.participant_runtime.autonomous_execution.planning_diagnostics(compile_runtime_model(authored))
backend.assert_not_called()
import json
import hashlib
from importlib.metadata import version
from raes_contracts.canonical import canonical_contract_digest, canonical_json_digest
print(json.dumps({
    "capability_sha256": hashlib.sha256((Path(aptl.__file__).parent / "backends" / "_lilrae_participant_capabilities.py").read_bytes()).hexdigest(),
    "python": sys.version.split()[0],
    "lilrae": version("lilrae"),
    "raes": version("raes"),
    "raes-env-packs": version("raes-env-packs"),
    "backend_manifest_digest": canonical_contract_digest(backend_manifest_v2_model(target.manifest)),
    "scenario_digest": canonical_json_digest(authored.model_dump(mode="json")),
    "implementation_manifest_digest": bindings[0].implementation_selection.manifest_digest,
    "policy": "participant-autonomous-execution/v1",
    "tool_semantics": "participant-tool-profile/v1",
    "native_effects": "deterministic local MCP handlers; no provider call",
}, sort_keys=True))
for selector in ("participant_refs", "participant_role_refs"):
    for first in ("red", "blue"):
        test_scoped_tools_preserve_authority_and_history(selector, first)
"""
    child = subprocess.run(
        [sys.executable, "-I", "-c", script, str(installed), str(repo)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert child.returncode == 0, child.stdout + child.stderr

    wheel = next((tmp_path / "wheels").glob("*.whl"))
    report = {
        "wheel": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "compatibility": json.loads(child.stdout),
    }
    (tmp_path / "candidate.json").write_text(json.dumps(report, indent=2) + "\n")
    print((tmp_path / "candidate.json").read_text())

    return report


def test_installed_wheel_scoped_contract(tmp_path):
    qualify_scoped_wheel(tmp_path)
