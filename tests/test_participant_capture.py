"""A fresh, exact participant source retains calls without replay accounting."""

from dataclasses import replace
import json

import pytest

from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.evidence.protocol import RunScope
from aptl.core.experiment.capture_registry import CaptureVisibility
from aptl.core.runstore import LocalRunStore
from tests.test_evidence_coordinator import _binding


def _grant():
    from aptl.core.evidence.participant_capture import ParticipantCaptureGrant

    return ParticipantCaptureGrant(
        binding=_binding(redaction_required=True, redaction_policy="redact_secrets"),
        scope=RunScope("run-1", "trial-1", "attempt-1"),
        participant_address="agents.red",
        capture_spec_version="1.0.0",
        configuration_digest="sha256:" + "a" * 64,
    )


def _payload():
    return {
        "invocation_id": "outer-red",
        "complete": True,
        "required_usage_complete": True,
        "calls": [
            {
                "invocation_id": "outer-red",
                "request_id": "request-1",
                "state": "completed",
                "provider_claims": {
                    "generation_id": "gen-1",
                    "served_provider": "provider",
                },
                "input_tokens": 12,
                "output_tokens": 3,
                "cost": None,
            }
        ],
        "records": [{"text": "accepted", "api_key": "private-canary"}],
    }


def test_source_is_run_scoped_and_repeated_publication_does_not_double_count(tmp_path):
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    archive = ParticipantCaptureArchive(LocalRunStore(tmp_path), _grant())
    archive.record(_payload())
    archive.record(_payload())
    result = archive.fetch("start", "end")
    assert result.status is CollectorStatus.OK
    assert len(result.records) == 1
    assert result.records[0]["totals"]["input_tokens"] == 12
    assert result.records[0]["totals"]["output_tokens"] == 3
    assert result.records[0]["totals"]["cost"] is None
    assert result.records[0]["capture_spec_version"] == "1.0.0"
    assert result.records[0]["participant_address"] == "agents.red"
    assert "private-canary" not in json.dumps(result.records)
    other = ParticipantCaptureArchive(
        LocalRunStore(tmp_path),
        replace(_grant(), scope=RunScope("run-2", "trial-2", "attempt-2")),
    )
    assert other.fetch("start", "end").status is CollectorStatus.SOURCE_UNAVAILABLE
    changed = _payload()
    changed["calls"][0]["input_tokens"] = 99
    with pytest.raises(ValueError):
        archive.record(changed)


def test_completed_missing_usage_is_partial_but_unknown_billing_is_usable(tmp_path):
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    payload = _payload()
    payload["required_usage_complete"] = False
    payload["calls"][0]["input_tokens"] = None
    archive = ParticipantCaptureArchive(LocalRunStore(tmp_path), _grant())
    archive.record(payload)
    result = archive.fetch("start", "end")
    assert result.status is CollectorStatus.MID_RUN_LOSS
    assert result.records
    assert result.records[0]["totals"]["input_tokens"] is None


def test_content_capture_refuses_participant_visibility():
    grant = _grant()
    binding = replace(
        grant.binding, visibility_class=CaptureVisibility.PARTICIPANT_VISIBLE
    )
    with pytest.raises(ValueError):
        replace(grant, binding=binding)


def test_capture_enabled_executor_retains_before_private_directory_cleanup(tmp_path):
    from pathlib import Path
    from threading import Event
    from tests.test_lilrae_participant_configuration import configuration
    from tests.test_provider_capture import _frames
    from tests.opencode_fixture import synthetic_options
    from aptl.backends.lilrae_participant_configuration import (
        configured_opencode_executor,
    )
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
    from aptl.workbench.process import ProcessResult

    manifest, result = configuration()
    grant = replace(
        _grant(),
        participant_address=result.participant_address,
        configuration_digest=result.configuration_digest,
    )
    archive = ParticipantCaptureArchive(LocalRunStore(tmp_path / "runs"), grant)

    class Runner:
        work = None

        def run(self, argv, **options):
            self.work = Path(options["cwd"])
            config = json.loads((self.work / "opencode.json").read_text())
            assert "OPENCODE_PURE" not in options["env"]
            assert options["env"]["OPENCODE_DISABLE_PROJECT_CONFIG"] == "true"
            assert options["env"]["OPENCODE_DISABLE_DEFAULT_PLUGINS"] == "true"
            assert len(config["plugin"]) == 1
            plugin, capture = config["plugin"][0]
            assert plugin.startswith("file:")
            Path(capture["path"]).write_bytes(
                _frames(usage={"prompt_tokens": 12, "completion_tokens": 3})
            )
            return ProcessResult(
                0,
                b'{"type":"text","part":{"text":"done"}}\n{"type":"step_finish","part":{"reason":"stop"}}\n',
                b"",
            )

    runner = Runner()
    active = configured_opencode_executor(
        options=synthetic_options(
            executable=Path("/bin/true"),
            work_root=tmp_path,
            runner=runner,
            environment={"OPENROUTER_API_KEY": "private-credential"},
            capture=archive,
        ),
        configuration=result,
        manifest=manifest,
        prompt="red task",
        prompt_ref="content.red-prompt@v1",
        supported_models=frozenset({"openrouter/model"}),
    )
    assert active("outer-red", Event()) == "done"
    assert not runner.work.exists()
    retained = archive.fetch("start", "end")
    assert retained.status is CollectorStatus.OK
    invocation = retained.records[0]["invocations"][0]
    assert invocation["calls"][0]["requested_provider"] == "test-provider"
    assert invocation["cli_events"][0]["part"]["text"] == "done"
    assert "private-credential" not in json.dumps(retained.records)


def test_action_counts_use_distinct_runtime_dispatch_identities():
    from aptl.core.evidence.participant_capture import aggregate_tool_calls

    rows = [
        {"phase": "dispatched", "action_instance_id": "first", "monotonic_ns": 10},
        {"phase": "dispatched", "action_instance_id": "first", "monotonic_ns": 10},
        {"phase": "failed", "action_instance_id": "first", "monotonic_ns": 11},
        {"phase": "refused", "action_instance_id": None, "monotonic_ns": 12},
        {"phase": "dispatched", "action_instance_id": "late", "monotonic_ns": 20},
    ]
    counts = aggregate_tool_calls(rows)
    assert counts["dispatched"] == 2
    assert counts["failed"] == 1
    assert counts["refused"] == 1
    assert counts["in_flight"] == 1


def test_tool_records_survive_a_missing_provider_invocation(tmp_path):
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    archive = ParticipantCaptureArchive(LocalRunStore(tmp_path), _grant())
    for sequence, phase in enumerate(("admitted", "dispatched", "unsettled")):
        archive.record_tool_event(
            {
                "participant_address": "agents.red",
                "episode_id": "episode-1",
                "invocation_id": "outer-red",
                "sequence": sequence,
                "phase": phase,
                "action_instance_id": "native-action-1",
                "observed_at": "2026-11-03T12:00:00Z",
                "monotonic_ns": sequence + 10,
            }
        )
    result = archive.fetch("start", "end")
    assert result.status is CollectorStatus.MID_RUN_LOSS
    assert len(result.records[0]["tool_events"]) == 3
    assert result.records[0]["action_counts"]["dispatched"] == 1


def test_malformed_invocation_preserves_another_accepted_invocation(tmp_path):
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    archive = ParticipantCaptureArchive(LocalRunStore(tmp_path), _grant())
    archive.record(_payload())
    archive.record({"invocation_id": "broken", "calls": [None], "complete": True})
    result = archive.fetch("start", "end")
    assert result.status is CollectorStatus.MID_RUN_LOSS
    assert [row["invocation_id"] for row in result.records[0]["invocations"]] == [
        "outer-red"
    ]
    assert result.records[0]["totals"]["known_input_tokens_subtotal"] == 12
    assert result.records[0]["totals"]["input_tokens"] is None
    assert all(
        result.records[0]["totals"][flag] is False
        for flag in (
            "membership_complete",
            "required_usage_complete",
            "input_tokens_complete",
            "output_tokens_complete",
            "billing_complete",
        )
    )


def test_attempts_with_the_same_invocation_id_have_separate_source_storage(tmp_path):
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    store = LocalRunStore(tmp_path)
    first = ParticipantCaptureArchive(store, _grant())
    first.record(_payload())
    later = ParticipantCaptureArchive(
        store, replace(_grant(), scope=replace(_grant().scope, attempt_id="attempt-2"))
    )
    changed = _payload()
    changed["calls"][0]["input_tokens"] = 20
    later.record(changed)
    assert first.fetch("s", "e").records[0]["totals"]["input_tokens"] == 12
    assert later.fetch("s", "e").records[0]["totals"]["input_tokens"] == 20


def test_retries_and_duplicate_generations_keep_honest_totals():
    from aptl.core.evidence.participant_capture import aggregate_model_calls
    from copy import deepcopy

    first = _payload()
    duplicate = deepcopy(first)
    duplicate["invocation_id"] = "repeat-delivery"
    retry = deepcopy(first)
    retry["invocation_id"] = "retry"
    retry["calls"][0]["provider_claims"]["generation_id"] = "gen-2"
    totals = aggregate_model_calls([first, duplicate, retry])
    assert totals["call_count"] == 2
    assert totals["input_tokens"] == 24
    assert totals["output_tokens"] == 6
    assert totals["membership_complete"]
    duplicate["calls"][0]["input_tokens"] = 99
    conflicting = aggregate_model_calls([first, duplicate])
    assert not conflicting["membership_complete"]
    assert conflicting["input_tokens"] is None


@pytest.mark.parametrize("termination", [None, "timeout", "cancelled"])
def test_archive_quota_retains_redacted_prefix_and_reports_truncation(
    tmp_path, termination
):
    from aptl.core.evidence.participant_capture import ParticipantCaptureArchive

    archive = ParticipantCaptureArchive(LocalRunStore(tmp_path), _grant())
    payload = _payload()
    payload["records"] = [
        {"output": "accepted response " * 1000, "api_key": "private-canary"}
    ]
    payload["harness_failure_reason"] = termination
    archive.record(payload)
    result = archive.fetch("s", "e")
    assert result.status is CollectorStatus.TRUNCATION
    assert result.records[0]["invocations"][0]["partial_payload"]
    assert result.records[0]["invocations"][0]["harness_failure_reason"] == termination
    assert "private-canary" not in json.dumps(result.records)
    assert result.records[0]["totals"]["input_tokens"] is None
