"""Create-once readiness observations in the existing private run store."""

import hashlib
from datetime import datetime

import rfc8785
from raes_contracts.diagnostics import Diagnostic, diagnostic_payload
from raes_contracts.trial_unit import TrialUnitRequest

from aptl.core.correlation.clock import ClockProvider
from aptl.core.experiment.capture_plan import CapturePlan
from aptl.core.runstore import LocalRunStore

MAX_READINESS_RECORD_BYTES = 65536


def readiness_request_digest(request: TrialUnitRequest) -> str:
    """Bind public content, excluding private Pydantic validation flags."""
    payload = {
        "plan": request.plan.model_dump(mode="json"),
        "entry": request.plan_entry_id,
        "attempt": request.execution_attempt_id,
        "snapshot": request.instantiated_sdl_digest,
        "plans": [
            plan.model_dump(mode="json")
            for plan in (
                request.provisioning_plan,
                request.orchestration_plan,
                request.evaluation_plan,
            )
        ],
    }
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def retain_readiness_observation(
    request: TrialUnitRequest,
    store: LocalRunStore,
    clock: ClockProvider,
    stage: str,
    checks: list[Diagnostic],
    target_digest: str,
    capture: CapturePlan | None = None,
) -> str:
    """Publish bounded canonical facts, without exposing storage or clock errors."""
    try:
        if stage not in {"clean", "prepared", "live"}:
            raise ValueError
        observed_at = clock.now()
        if not isinstance(observed_at, str) or len(observed_at) > 64:
            raise ValueError
        if datetime.fromisoformat(observed_at).utcoffset() is None:
            raise ValueError
        payload = {
            "schema_version": "lilrae.trial-readiness/v1",
            "stage": stage,
            "plan_id": request.plan.plan_id,
            "plan_digest": request.plan.plan_digest,
            "plan_entry_id": request.plan_entry_id,
            "entry_digest": request.plan.entries[request.plan_entry_id].entry_digest,
            "run_id": request.run_id,
            "execution_attempt_id": request.execution_attempt_id,
            "snapshot_digest": request.instantiated_sdl_digest,
            "target_digest": target_digest,
            "observed_at": observed_at,
            "configuration_digests": [
                item.configuration_digest for item in request.participant_configurations
            ],
            "participants": [
                {
                    "address": item.participant_address,
                    "manifest_digest": item.manifest_digest,
                    "configuration_digest": item.configuration_digest,
                }
                for item in request.participant_configurations
            ],
            "captures": []
            if capture is None
            else [
                {
                    "registration_id": item.registration_id,
                    "configuration_digest": item.effective_config_digest,
                    "requirement_digest": hashlib.sha256(
                        rfc8785.dumps(item.projection())
                    ).hexdigest(),
                }
                for item in capture.bindings
            ],
            "checks": [diagnostic_payload(check) for check in checks],
        }
        raw = rfc8785.dumps(payload)
        if len(raw) > MAX_READINESS_RECORD_BYTES:
            raise ValueError
        digest = hashlib.sha256(raw).hexdigest()
        relative = f"readiness/{stage}/{digest}.json"
        store.create_run_json_once(request.run_id, relative, payload)
        return relative
    except Exception:
        raise ValueError("trial-readiness-storage-unavailable") from None
