"""Native creation receipts retain causal identity without granting new authority."""

from dataclasses import replace
import json

import pytest

from aptl.core.deployment._compose_resource_ownership import (
    OwnershipConflictError,
    WorkspaceOwnership,
)
from tests.test_raes_runtime_orchestration import _runtime, _spec


def test_timeout_survives_an_empty_template_collection():
    runtime = _runtime()
    authority = runtime.orchestration_authorities[0].model_copy(
        update={"spawn_templates": ()}
    )
    runtime = runtime.model_copy(update={"orchestration_authorities": (authority,)})
    admission = _spec(runtime).docker_authority_admissions[0]
    assert admission.spawn_requirements == ()
    assert admission.execution_timeout_seconds == 600


def _store(tmp_path, *, attempt="attempt-1", clock=lambda: 1000.0):
    from aptl.core.deployment.lilrae_docker_recording import RecordingStore

    return RecordingStore(
        WorkspaceOwnership.ensure(tmp_path, "aptl"),
        daemon_id="daemon-1",
        attempt_id=attempt,
        wall_clock=clock,
    )


def test_create_response_pins_native_id_and_retry_preserves_the_receipt(tmp_path):
    store = _store(tmp_path)
    intent = store.begin("provision.node.holder", timeout_seconds=60)
    creation = store.commit(intent, "a" * 64)
    assert creation == store.commit(intent, "a" * 64)
    (receipt,) = store.ownership.receipts("container")
    assert receipt.managed_by == "child"
    assert receipt.native_id == "a" * 64
    assert receipt.node_address == creation.address
    assert store.verify(receipt) == creation
    assert not store.pending()
    assert creation.deadline_utc == 1060.0
    assert creation.source_address == "provision.node.holder"
    assert creation.parent_native_id == ""


def test_delegation_keeps_source_and_cannot_extend_parent_deadline(tmp_path):
    now = [1000.0]
    store = _store(tmp_path, clock=lambda: now[0])
    parent = store.commit(
        store.begin("provision.node.holder", timeout_seconds=60), "a" * 64
    )
    now[0] = 1050.0
    child = store.commit(
        store.begin(
            parent.source_address, parent_native_id=parent.native_id, timeout_seconds=60
        ),
        "b" * 64,
    )
    assert child.parent_native_id == parent.native_id
    assert child.parent_address == parent.address
    assert child.source_address == parent.source_address
    assert child.deadline_utc == parent.deadline_utc
    assert child.address != parent.address


def test_prior_attempt_cannot_authorize_current_attempt_observation(tmp_path):
    old = _store(tmp_path, attempt="old")
    old.commit(old.begin("provision.node.holder", timeout_seconds=60), "a" * 64)
    (receipt,) = old.ownership.receipts("container")
    current = _store(tmp_path, attempt="new")
    with pytest.raises(OwnershipConflictError):
        current.verify(receipt)
    with pytest.raises(OwnershipConflictError):
        current.begin(
            "provision.node.holder",
            parent_native_id=receipt.native_id,
            timeout_seconds=60,
        )
    assert current.records() == ()


def test_foreign_and_legacy_child_receipts_have_no_creation_authority(tmp_path):
    store = _store(tmp_path)
    creation = store.commit(
        store.begin("provision.node.holder", timeout_seconds=60), "a" * 64
    )
    (receipt,) = store.ownership.receipts("container")
    for altered in (
        replace(receipt, native_id="b" * 64),
        replace(receipt, daemon_id="another-daemon"),
        replace(receipt, node_address="provision.node.foreign"),
    ):
        with pytest.raises(OwnershipConflictError):
            store.verify(altered)
    assert store.verify(receipt) == creation


def test_unfinished_create_is_a_durable_gap_and_grants_no_native_authority(tmp_path):
    store = _store(tmp_path)
    intent = store.begin("provision.node.holder", timeout_seconds=60)
    recovered = _store(tmp_path)
    assert recovered.pending() == (intent,)
    assert recovered.records() == ()
    assert recovered.ownership.receipts("container") == ()


def test_conflicting_response_cannot_replace_a_native_incarnation(tmp_path):
    store = _store(tmp_path)
    intent = store.begin("provision.node.holder", timeout_seconds=60)
    store.commit(intent, "a" * 64)
    with pytest.raises(OwnershipConflictError):
        store.commit(intent, "b" * 64)


def test_record_files_are_private_and_do_not_capture_api_payloads(tmp_path):
    store = _store(tmp_path)
    store.commit(store.begin("provision.node.holder", timeout_seconds=60), "a" * 64)
    files = list(tmp_path.rglob("*.json"))
    assert files
    for path in files:
        assert path.stat().st_mode & 0o777 == 0o600
        payload = json.loads(path.read_bytes())
        assert not {"Env", "Cmd", "HostConfig", "AuthConfig"} & payload.keys()


def test_response_publication_crash_can_recover_only_the_already_recorded_id(
    tmp_path, monkeypatch
):
    store = _store(tmp_path)
    intent = store.begin("provision.node.holder", timeout_seconds=60)
    publish = store._publish

    def interrupted(relative, value):
        if relative.parts[0] == "children":
            raise OSError("interrupted receipt publication")
        return publish(relative, value)

    monkeypatch.setattr(store, "_publish", interrupted)
    with pytest.raises(OSError):
        store.commit(intent, "a" * 64)
    recovered = _store(tmp_path)
    assert recovered.pending() == (intent,)
    recovered.recover_responses()
    assert recovered.pending() == ()
    assert recovered.creation("a" * 64).created_utc == intent.created_utc
