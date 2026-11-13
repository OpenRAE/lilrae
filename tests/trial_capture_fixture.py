"""Admitted capture request shared by backend collection tests."""

import json

from dataclasses import replace
from types import SimpleNamespace
from aptl.backends.raes_evidence_acquisition import NativeEvidenceRequest
from aptl.core.correlation.clock import FixedClockProvider
from aptl.core.experiment.capture_plan import admit_capture_demands
from aptl.core.experiment.capture_registry import CollectorRegistry
from aptl.core.runstore import LocalRunStore


def capture_request(tmp_path):
    from tests.test_pack_adapter_install_seam import _registration, PACK, BACKEND
    from aptl.backends.scenario_capture import (
        ScenarioCaptureContext,
        ScenarioCaptureContribution,
        ResolvedScenarioCapture,
    )
    from raes_backend_protocols.capabilities import ObservationCaptureOffer
    from raes_processor.capture_admission import CaptureDemand

    offer = ObservationCaptureOffer(
        offer_id="rpt.raw-observations",
        offer_version="1.0.0",
        output_contract="experiment-evidence-record-v1",
        field_selectors=("",),
        artifact_roles=frozenset({"observation"}),
        media_types=frozenset({"application/json"}),
        capture_kind="observation",
        source_classes=frozenset({"apparatus"}),
        source_refs=frozenset({"nodes.soc"}),
        scopes=frozenset({"run"}),
        scope_refs=frozenset({"nodes.soc"}),
        channel_kinds=frozenset({"backend-log"}),
        channel_refs=frozenset(),
        window_kinds=frozenset({"run"}),
        integrity_modes=frozenset({"checksum"}),
        sensitivity="internal",
        availability="available",
        fidelity="complete",
        disclosure="redacted",
        retention_policy_refs=frozenset({"run_lifetime"}),
        export_policy="not-required",
        redaction_policy=None,
    )
    registration = replace(
        _registration(),
        channel_kind="backend-log",
        capture_offer=offer,
        integrity_modes=frozenset({"checksum"}),
        redaction_policies=frozenset(),
        retention_policies=frozenset({"run_lifetime"}),
    )
    registry = CollectorRegistry((registration,))
    demand = CaptureDemand(
        demand_id="security-tool-logs",
        address="evidence_requirements.security-tool-logs",
        output_contract=offer.output_contract,
        field_selectors=("",),
        artifact_roles=("observation",),
        media_types=("application/json",),
        capture_kind="observation",
        source_classes=("apparatus",),
        source_refs=("nodes.soc",),
        scopes=("run",),
        scope_refs=("nodes.soc",),
        channel_kinds=("backend-log",),
        channel_refs=(),
        window_kinds=("run",),
        integrity_modes=("checksum",),
        sensitivity="internal",
        disclosure="redacted",
        retention_policy_refs=("run_lifetime",),
        redaction_policy=None,
    )
    plan = admit_capture_demands(
        (demand,), source_identity="sha256:" + "a" * 64, registry=registry
    )
    selection = ResolvedScenarioCapture(
        registry,
        ScenarioCaptureContribution(
            (registration,),
            native_registration_ids=frozenset({registration.registration_id}),
        ),
        ScenarioCaptureContext(PACK, BACKEND),
        "rpt-test-capture",
        "1",
    )
    store = LocalRunStore(tmp_path / "runs")
    request = NativeEvidenceRequest(
        plan=plan,
        backend=SimpleNamespace(),
        realization=SimpleNamespace(nodes=(), generated_artifacts=()),
        project_dir=tmp_path,
        environment={},
        run_store=store,
        run_id="run-1",
        capture_selection=selection,
        clock=FixedClockProvider(measurement_time="2026-11-04T00:00:00Z"),
    )
    return request, registration


def run_managed_capture(tmp_path, archive, role):
    """Exercise the configured producer, transport reducer and retention callback."""
    from pathlib import Path
    from threading import Event
    from tests.test_lilrae_participant_configuration import configuration
    from tests.test_provider_capture import _frames
    from tests.opencode_fixture import synthetic_options
    from aptl.backends.lilrae_participant_configuration import (
        configured_opencode_executor,
    )
    from aptl.workbench.process import ProcessResult

    class Runner:
        def run(self, argv, **options):
            work = Path(options["cwd"])
            config = json.loads((work / "opencode.json").read_text())
            capture = config["plugin"][0][1]
            Path(capture["path"]).write_bytes(
                _frames(
                    usage={
                        "prompt_tokens": 12,
                        "completion_tokens": 3,
                        "completion_tokens_details": {"reasoning_tokens": 2},
                        "prompt_tokens_details": {
                            "cached_tokens": 5,
                            "cache_write_tokens": 4,
                        },
                    }
                ).replace(b"outer-red", capture["invocationId"].encode())
            )
            from aptl.backends.participant_tools.session import LilraeToolSession
            from tests.test_lilrae_participant_tools import binding, port, result

            native_port = port()
            native_port.participant_address = archive.grant.participant_address
            native_port.invocation_action_instance_id = f"outer-{role}"
            native_port.episode_id = f"episode-{role}"
            session = LilraeToolSession(
                native_port,
                (binding(),),
                Event(),
                evidence_sink=executor.tool_evidence_sink,
            )
            session.invoke(
                "aptl-red",
                "kali_run_command",
                {"command": "id"},
                "call",
                lambda args: result(
                    json.dumps(
                        {
                            "success": True,
                            "output": f"{role} tool result",
                            "credential": "private-credential",
                        }
                    )
                ),
            )
            events = [
                {"type": "text", "part": {"text": f"{role} observation"}},
                {"type": "reasoning", "part": {"text": f"{role} returned reasoning"}},
                {"type": "step_finish", "part": {"reason": "stop"}},
            ]
            return ProcessResult(
                0, b"\n".join(json.dumps(row).encode() for row in events), b""
            )

    manifest, configuration_result = configuration(role=role)
    executor = configured_opencode_executor(
        options=synthetic_options(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            runner=Runner(),
            environment={"OPENROUTER_API_KEY": "private-credential"},
            capture=archive,
        ),
        configuration=configuration_result,
        manifest=manifest,
        prompt="red task",
        prompt_ref="content.red-prompt@v1",
        supported_models=frozenset({"openrouter/model"}),
    )
    assert executor(f"outer-{role}", Event()) == f"{role} observation"
