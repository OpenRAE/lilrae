"""Immutable identity commitments before an admitted trial can cause effects."""

import hashlib
from dataclasses import asdict
from typing import Annotated, Literal

import rfc8785
from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.errors import RaesError
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.trial_unit import TrialUnitRequest

from aptl.core.cleanup import CleanupBinding
from aptl.core.readiness_record import readiness_request_digest
from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import PathContainmentError, open_contained_nofollow

TRIAL_INTENT_PATH = "trial-serving/intent.json"
MAX_TRIAL_INTENT_BYTES = 16384

type Identity = Annotated[str, Field(min_length=1, max_length=256)]
type Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
type ContractDigest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


class TrialIntent(BaseModel):
    """Routing commitments never grant native cleanup authority."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )

    schema_version: Literal["lilrae.trial-intent/v1"] = "lilrae.trial-intent/v1"
    run_id: Identity
    execution_attempt_id: Identity
    plan_entry_id: Identity
    plan_digest: ContractDigest
    instantiated_sdl_digest: ContractDigest
    request_digest: Digest
    native_attempt_id: Identity
    native_binding_digest: Digest
    owner: Digest
    daemon_digest: Digest


def trial_intent(
    request: TrialUnitRequest, binding: CleanupBinding, owner: bytes, daemon: str
) -> TrialIntent:
    """Bind the public request and installed owner without retaining secrets."""
    native = asdict(binding)
    native["project_dir"] = str(binding.project_dir.resolve())
    return TrialIntent(
        run_id=request.run_id,
        execution_attempt_id=request.execution_attempt_id,
        plan_entry_id=request.plan_entry_id,
        plan_digest=request.plan.plan_digest,
        instantiated_sdl_digest=request.instantiated_sdl_digest,
        request_digest=readiness_request_digest(request),
        native_attempt_id=binding.native_attempt_id,
        native_binding_digest=hashlib.sha256(rfc8785.dumps(native)).hexdigest(),
        owner=owner.decode("ascii"),
        daemon_digest=hashlib.sha256(daemon.encode()).hexdigest(),
    )


def retain_trial_intent(store: LocalRunStore, intent: TrialIntent) -> None:
    """Commit the exact admitted identity before external work begins."""
    try:
        store.create_run_json_once(
            intent.run_id, TRIAL_INTENT_PATH, intent.model_dump(mode="json")
        )
    except ValueError:
        raise ValueError("trial-intent-conflict") from None


def load_trial_intent(store: LocalRunStore, expected: TrialIntent) -> TrialIntent:
    """Validate the original bytes and installed identity before redelivery."""
    try:
        # Reuse store ID validation, then traverse the original path no-follow.
        store.get_run_path(expected.run_id)
        with open_contained_nofollow(
            store.base_dir, f"{expected.run_id}/{TRIAL_INTENT_PATH}"
        ) as source:
            data = source.read(MAX_TRIAL_INTENT_BYTES + 1)
        payload = parse_bounded_json_object(
            data, max_bytes=MAX_TRIAL_INTENT_BYTES, max_depth=8
        )
        retained = TrialIntent.model_validate(payload)
    except (OSError, PathContainmentError, RaesError, ValueError):
        raise ValueError("trial-intent-invalid") from None
    if retained != expected:
        raise ValueError("trial-intent-conflict")
    return retained
