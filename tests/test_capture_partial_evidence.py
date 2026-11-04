"""A failed source retains accepted evidence under its original failure."""

import json

import pytest

from aptl.core.evidence.adapters.sources import SourceResult, source_result_to_outcome
from aptl.core.evidence.outcomes import AcquisitionDisposition, CollectorStatus
from tests.test_evidence_coordinator import _FakeCollector, _acquire, _binding


@pytest.mark.parametrize(
    "status",
    [
        CollectorStatus.TIMEOUT,
        CollectorStatus.MID_RUN_LOSS,
        CollectorStatus.FINALIZATION_FAILURE,
    ],
)
def test_failed_capture_keeps_redacted_partial_records(tmp_path, status):
    outcome = source_result_to_outcome(
        SourceResult(
            status=status,
            records=[{"message": "accepted", "api_key": "private-canary"}],
        ),
        "2026-07-20T00:00:00Z",
        "2026-07-20T00:00:05Z",
    )
    binding = _binding(redaction_required=True, redaction_policy="redact_secrets")
    result = _acquire(
        tmp_path,
        [binding],
        {
            binding.registration_id: _FakeCollector(
                binding.registration_id, outcome=outcome
            )
        },
    )
    assert result.disposition is AcquisitionDisposition.INVALIDATED
    assert result.reports[0].status is status
    assert len(result.records) == 1
    record = result.records[0]
    assert status.value in record.raw_content.loss_disclosure
    retained = (
        tmp_path / "runs" / "run-1" / record.raw_content.content_uri
    ).read_bytes()
    assert b"private-canary" not in retained
    assert json.loads(retained)[0]["message"] == "accepted"


def test_failure_without_content_never_creates_empty_success(tmp_path):
    outcome = source_result_to_outcome(
        SourceResult(status=CollectorStatus.TIMEOUT),
        "2026-07-20T00:00:00Z",
        "2026-07-20T00:00:05Z",
    )
    binding = _binding()
    result = _acquire(
        tmp_path,
        [binding],
        {
            binding.registration_id: _FakeCollector(
                binding.registration_id, outcome=outcome
            )
        },
    )
    assert result.disposition is AcquisitionDisposition.INVALIDATED
    assert not result.records


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_trial_interruption_persists_accepted_artifact_references(
    tmp_path, interruption
):
    from aptl.utils.pathsafe import read_contained_nofollow

    binding = _binding(redaction_required=True, redaction_policy="redact_secrets")
    outcome = source_result_to_outcome(
        SourceResult(
            status=CollectorStatus.MID_RUN_LOSS,
            records=[
                {"message": "accepted before interruption", "api_key": "private-canary"}
            ],
        ),
        "2026-07-20T00:00:00Z",
        "2026-07-20T00:00:05Z",
    )

    def interrupted():
        raise interruption()

    collector = _FakeCollector(binding.registration_id, outcome=outcome)
    with pytest.raises(interruption):
        _acquire(
            tmp_path,
            [binding],
            {binding.registration_id: collector},
            trial_body=interrupted,
        )
    run = tmp_path / "runs" / "run-1"
    ledger = list(run.glob("evidence/records/*.json"))
    assert ledger, list(run.rglob("*.json"))
    record = json.loads(ledger[0].read_bytes())
    retained = read_contained_nofollow(run, record["raw_content"]["content_uri"])
    assert json.loads(retained)[0]["message"] == "accepted before interruption"
    assert b"private-canary" not in retained


@pytest.mark.parametrize("operation", ["logs", "file"])
@pytest.mark.parametrize("failure", ["timeout", "interrupted"])
def test_native_timeout_prefix_and_peer_survive_artifact_persistence(
    tmp_path, operation, failure
):
    from subprocess import TimeoutExpired
    from types import SimpleNamespace
    from aptl.backends.scenario_runtime_hooks import AdmittedRuntimeOperations
    from aptl.core.evidence.adapters.builtins import (
        ContainerFileSource,
        ContainerLogSource,
    )
    from tests.test_evidence_coordinator import _ok_outcome

    def interrupted(*args, **kwargs):
        if failure == "timeout":
            raise TimeoutExpired(
                ["private-command"],
                30,
                output=b"accepted stdout\n",
                stderr=b"accepted stderr\n",
            )
        error = InterruptedError("private-command")
        error.stdout, error.stderr = b"accepted stdout\n", b"accepted stderr\n"
        raise error

    operations = AdmittedRuntimeOperations(
        SimpleNamespace(container_logs_capture=interrupted, container_exec=interrupted),
        [SimpleNamespace(name="soc")],
    )
    source = (
        ContainerLogSource(operations, ["soc"])
        if operation == "logs"
        else ContainerFileSource(
            operations,
            [("soc", "/var/log/events")],
            timestamp_of=lambda line: "2026-07-20T00:00:01Z",
        )
    )
    outcome = source_result_to_outcome(
        source.fetch(
            "2026-07-20T00:00:00Z",
            "2026-07-20T00:00:05Z",
        ),
        "2026-07-20T00:00:00Z",
        "2026-07-20T00:00:05Z",
    )
    binding = _binding()
    peer = _binding(registration_id="peer", requirement_id="peer")
    result = _acquire(
        tmp_path,
        [binding, peer],
        {
            binding.registration_id: _FakeCollector(
                binding.registration_id, outcome=outcome
            ),
            peer.registration_id: _FakeCollector(
                peer.registration_id, outcome=_ok_outcome()
            ),
        },
    )
    assert len(result.refs) == 2
    assert result.reports[0].status is (
        CollectorStatus.TIMEOUT
        if failure == "timeout"
        else CollectorStatus.MID_RUN_LOSS
    )
    retained = (tmp_path / "runs" / "run-1" / result.refs[0].content_uri).read_bytes()
    assert b"accepted stdout" in retained
    assert b"accepted stderr" in retained
    assert b"private-command" not in retained
