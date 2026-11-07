"""The trial path with the real pinned OpenCode binary and local providers (#1670).

No lab runs. Participants come from a concrete trial SDL, the real OpenCode
child talks to loopback providers, and the trial seals a real run store.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aptl.core.archival import verify_sealed_archive
from aptl.core.config import ExperimentSettings
from aptl.core.runstore import LocalRunStore
from aptl.core.trial_attempt import TrialAttempt
from aptl.core.trial_control import TrialControl
from aptl.core.trial_record import seal_trial_record
from aptl.core.trial_sdl import declared_participants
from aptl.workbench.trial_launch import TrialLaunchSettings, invocation_fields, trial_executors
from aptl.workbench.trial_run import run_declared_trial
from tests.test_opencode_transport import provider
from tests.trial_sdl_fixture import ASSET_BYTES, parse_trial, read_fixture_asset, trial_document

pytestmark = pytest.mark.integration

_PROVIDERS = {
    "openrouter/vendor-a/model-a": "vendor-a",
    "openrouter/vendor-b/model-b": "vendor-b",
}


@pytest.fixture
def opencode_binary():
    selected = os.environ.get("LILRAE_TEST_OPENCODE")
    if not selected:
        pytest.skip("the trial path requires the pinned OpenCode qualification binary")
    return Path(selected).resolve(strict=True)


def _settings(tmp_path, opencode_binary, *, endpoint, sources, environment):
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    return TrialLaunchSettings(
        executable=opencode_binary,
        work_root=work,
        experiment=ExperimentSettings.model_validate(
            {
                "participant_credential_sources": sources,
                "participant_serving_providers": _PROVIDERS,
            }
        ),
        source_environment=environment,
        max_output_tokens=64,
        openrouter_endpoint=endpoint,
    )


def _run_trial(tmp_path, scenario, settings, attempt, *, control):
    participants = declared_participants(scenario)
    store = LocalRunStore(tmp_path / "runs")
    store.create_run(attempt.run_id)
    store.write_json(attempt.run_id, "manifest.json", {"startup": "synthetic"})
    evidence: dict[str, dict[str, object]] = {}
    control.claim(attempt)
    control.begin(attempt)
    try:
        with trial_executors(
            scenario,
            participants,
            run_id=attempt.run_id,
            deadline=attempt.deadline,
            settings=settings,
            read_asset=read_fixture_asset,
            evidence_sink=lambda address, item: evidence.__setitem__(
                address, invocation_fields(item)
            ),
        ) as executors:
            record = run_declared_trial(
                attempt=attempt,
                scenario_sha256="sha256:" + "2" * 64,
                participants=participants,
                invocations=executors,
                evidence=evidence,
                stop_requested=control.stop_requested,
                store=store,
                clock=lambda: datetime.now(UTC),
                poll_seconds=0.2,
            )
        record = record.model_copy(update={"cleanup": {"provider_access": "removed"}})
        seal_trial_record(store, record)
    finally:
        control.release(attempt)
    return store, record


def _router_settings(tmp_path, opencode_binary, endpoint):
    return _settings(
        tmp_path,
        opencode_binary,
        endpoint=endpoint,
        sources={"opencode": {"kind": "process-environment", "variable": "TEST_ROUTER_KEY"}},
        environment={"TEST_ROUTER_KEY": "private-test-credential"},
    )


def test_real_participants_receive_declared_models_and_prompts_then_seal(
    tmp_path, opencode_binary
):
    scenario = parse_trial(trial_document())
    attempt = TrialAttempt("run-real", "attempt-1", datetime.now(UTC) + timedelta(minutes=5))
    with provider() as (endpoint, requests):
        store, record = _run_trial(
            tmp_path,
            scenario,
            _router_settings(tmp_path, opencode_binary, endpoint),
            attempt,
            control=TrialControl(tmp_path),
        )

    assert record.terminal_cause == "completed"
    assert {item.status for item in record.participants} == {"completed"}
    models = sorted(request["model"] for _, request in requests)
    assert models == ["vendor-a/model-a", "vendor-b/model-b"]
    prompts = {
        request["model"]: json.dumps(request["messages"]) for _, request in requests
    }
    for model, role, playbook in (
        ("vendor-a/model-a", "red", "red-playbook-quiet"),
        ("vendor-b/model-b", "blue", "blue-playbook-watch"),
    ):
        for asset in (f"{role}-preamble", playbook, f"{role}-task"):
            assert ASSET_BYTES[asset].decode().strip() in prompts[model]
    for _, request in requests:
        assert request["provider"]["allow_fallbacks"] is False
    sealed = verify_sealed_archive(store.base_dir, "run-real")
    assert sealed is not None
    for path in store.get_run_path("run-real").rglob("*"):
        if path.is_file():
            assert b"private-test-credential" not in path.read_bytes()


@pytest.mark.parametrize("cause", ["deadline", "stopped"])
def test_real_participants_stop_at_deadline_or_stop_request(
    tmp_path, opencode_binary, cause
):
    from aptl.core.lab import request_trial_stop

    scenario = parse_trial(trial_document())
    seconds = 8 if cause == "deadline" else 300
    attempt = TrialAttempt(
        f"run-{cause}", "attempt-1", datetime.now(UTC) + timedelta(seconds=seconds)
    )
    pause = threading.Event()
    stop_results = []
    with provider(pause=pause) as (endpoint, requests):
        if cause == "stopped":

            def stop_after_both_requests():
                while len(requests) < 2:
                    threading.Event().wait(0.2)
                stop_results.append(request_trial_stop(tmp_path, wait_seconds=120))

            stopper = threading.Thread(target=stop_after_both_requests, daemon=True)
            stopper.start()
        try:
            store, record = _run_trial(
                tmp_path,
                scenario,
                _router_settings(tmp_path, opencode_binary, endpoint),
                attempt,
                control=TrialControl(tmp_path),
            )
        finally:
            pause.set()
    if cause == "stopped":
        stopper.join(120)
        assert stop_results == [None]

    assert record.terminal_cause == cause
    assert len(requests) == 2
    assert {item.status for item in record.participants} == {"cancelled"}
    for item in record.participants:
        assert item.invocation["status"] == "failed"
        assert item.invocation["requested_model"] == item.model
    assert verify_sealed_archive(store.base_dir, f"run-{cause}") is not None
    assert TrialControl(tmp_path).active() is None


def _service_account_key() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    key = {
        "type": "service_account",
        "project_id": "synthetic-project",
        "private_key_id": "synthetic-key-id",
        "private_key": pem,
        "client_email": "participant@synthetic-project.iam.gserviceaccount.com",
        "client_id": "1",
    }
    return json.dumps(key), pem


def test_real_vertex_participant_key_stays_out_of_the_run(tmp_path, opencode_binary):
    """No real Google account exists, so participants fail; the key must not leak."""
    document = trial_document(
        red_model="google-vertex/vendor-d/model-d", blue_model="google-vertex/vendor-e/model-e"
    )
    scenario = parse_trial(document)
    attempt = TrialAttempt("run-vertex", "attempt-1", datetime.now(UTC) + timedelta(minutes=3))
    key, pem = _service_account_key()
    settings = _settings(
        tmp_path,
        opencode_binary,
        endpoint="https://openrouter.ai/api/v1",
        sources={"vertex": {"kind": "process-environment", "variable": "TEST_VERTEX_KEY"}},
        environment={"TEST_VERTEX_KEY": key},
    )
    store, record = _run_trial(
        tmp_path, scenario, settings, attempt, control=TrialControl(tmp_path)
    )

    assert record.terminal_cause == "failed"
    assert {item.status for item in record.participants} == {"failed"}
    assert {item.invocation["requested_model"] for item in record.participants} == {
        "google-vertex/vendor-d/model-d",
        "google-vertex/vendor-e/model-e",
    }
    assert not list((tmp_path / "work").glob("lilrae-vertex-*"))
    secret = pem.split("\n")[1].encode()
    encoded = base64.b64encode(secret)
    for path in store.get_run_path("run-vertex").rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert secret not in data and encoded not in data, path
    assert hashlib.sha256(key.encode()).hexdigest() not in json.dumps(record.model_dump())
    assert verify_sealed_archive(store.base_dir, "run-vertex") is not None
