"""Version 1 request and report models of the shared containment interface."""

import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aptl.core.containment import (
    REPORT_SCHEMA,
    REQUEST_SCHEMA,
    AppliedBounds,
    EngineIdentity,
    ExecutionReport,
    ExecutionRequest,
    FailureOrigin,
    HostIdentity,
    PropertyObservation,
    PropertyState,
    RequiredProperty,
    RunStatus,
    TargetOutcome,
    profile_properties,
)
from aptl.utils.strict_json import model_validate_json_strict


def _request_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": REQUEST_SCHEMA,
        "profile": "linux-full",
        "label": "fixture.run-1",
        "argv": ["/usr/bin/python3", "-c", "print(1)"],
        "env": {"FIXTURE_MODE": "proof"},
        "stdin": base64.b64encode(b"payload").decode(),
        "input_dir": None,
        "limits": {"deadline_seconds": 5, "max_output_bytes": 4096},
        "network": "none",
    }
    document.update(overrides)
    return document


def _parse(document: dict[str, object]) -> ExecutionRequest:
    return model_validate_json_strict(ExecutionRequest, json.dumps(document))


def test_request_round_trips_with_base64_stdin() -> None:
    request = _parse(_request_document())

    assert request.stdin == b"payload"
    assert request.argv[0] == "/usr/bin/python3"
    assert request.limits.cpu_seconds is None
    assert json.loads(request.model_dump_json())["stdin"] == base64.b64encode(b"payload").decode()


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": "lilrae.containment.request/v2"},
        {"profile": "linux-partial"},
        {"network": "relay"},
        {"argv": []},
        {"argv": ["python3", "-c", "1"]},
        {"argv": ["/bin/sh", "a\x00b"]},
        {"env": {"BAD-NAME": "x"}},
        {"env": {"NAME": "a\x00b"}},
        {"env": {f"V{index}": "x" for index in range(65)}},
        {"stdin": "not base64!"},
        {"input_dir": "relative/dir"},
        {"label": "Upper"},
        {"limits": {"deadline_seconds": 0, "max_output_bytes": 1}},
        {"limits": {"deadline_seconds": 3601, "max_output_bytes": 1}},
        {"limits": {"deadline_seconds": 1, "max_output_bytes": 16 * 1024 * 1024 + 1}},
        {"limits": {"deadline_seconds": 1, "max_output_bytes": True}},
        {"unexpected": True},
    ],
)
def test_request_refuses_invalid_documents(overrides: dict[str, object]) -> None:
    document = _request_document(**overrides)
    with pytest.raises(ValidationError):
        _parse(document)


def test_request_refuses_stdin_over_the_bound() -> None:
    oversized = base64.b64encode(b"x" * (8 * 1024 * 1024 + 1)).decode()

    document = _request_document(stdin=oversized)
    with pytest.raises(ValidationError):
        _parse(document)


def test_request_refuses_duplicate_keys() -> None:
    payload = json.dumps(_request_document())[:-1] + ', "network": "none"}'

    with pytest.raises(ValueError, match="duplicate"):
        model_validate_json_strict(ExecutionRequest, payload)


def test_linux_full_profile_requires_every_property() -> None:
    assert profile_properties("linux-full") == tuple(RequiredProperty)
    assert len(RequiredProperty) == 5


def _report(**overrides: object) -> ExecutionReport:
    delivered = tuple(
        PropertyObservation(property=item, state=PropertyState.DELIVERED, basis="probe")
        for item in RequiredProperty
    )
    fields: dict[str, object] = {
        "schema_version": REPORT_SCHEMA,
        "run_id": "0" * 32,
        "label": "fixture",
        "status": RunStatus.COMPLETED,
        "failure_origin": FailureOrigin.NONE,
        "reason": None,
        "detail": None,
        "contained": True,
        "properties": delivered,
        "target": TargetOutcome(
            exit_code=0, stdout=b"ok", stderr=b"",
            stdout_bytes=2, stderr_bytes=0, truncated=False,
        ),
        "engine": EngineIdentity(
            implementation="lilrae.containment.bubblewrap/v1",
            bubblewrap_version="0.9.0",
            landlock_abi=4,
            libseccomp_version="2.5.5",
        ),
        "host": HostIdentity(kernel_release="6.8.0"),
        "bounds": AppliedBounds(
            deadline_seconds=5,
            max_output_bytes=4096,
            cpu_seconds=None,
            max_file_mb=None,
            address_space_mb=None,
        ),
        "cleanup": None,
        "run_dir": Path("/tmp/run"),
    }
    fields.update(overrides)
    return ExecutionReport.model_validate(fields)


def test_report_serializes_output_as_base64_and_states_memory_bound() -> None:
    document = json.loads(_report().model_dump_json())

    assert document["target"]["stdout"] == base64.b64encode(b"ok").decode()
    assert document["bounds"]["peak_memory"] == "not-enforced"
    assert model_validate_json_strict(ExecutionReport, json.dumps(document)) == _report()


def test_report_refuses_contained_claim_without_every_property() -> None:
    partial = tuple(
        PropertyObservation(
            property=item,
            state=PropertyState.UNKNOWN if item is RequiredProperty.SUPERVISION else PropertyState.DELIVERED,
            basis="probe",
        )
        for item in RequiredProperty
    )

    with pytest.raises(ValidationError, match="contained"):
        _report(properties=partial)


def test_report_refuses_contained_claim_without_a_target() -> None:
    with pytest.raises(ValidationError, match="contained"):
        _report(target=None)


def test_report_requires_one_observation_per_property() -> None:
    with pytest.raises(ValidationError, match="each required property"):
        _report(contained=False, properties=())
