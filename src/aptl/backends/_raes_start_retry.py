"""Lab start's single backend retry under RAES single runtime ownership."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from aptl.backends.raes_start_model import AcesStartOutcome
from aptl.utils.logging import get_logger
from aptl.utils.redaction import redact

log = get_logger("raes-backend")

_RETRY_SKIPPED = (
    "Automatic retry skipped: the first runtime owner could not be released"
)


def apply_with_single_retry(
    run_attempt: Callable[[], AcesStartOutcome],
    before_retry: Callable[[], None] | None,
) -> AcesStartOutcome:
    """Run one attempt, and one retry when it failed retryably and a hook exists.

    raes 7 lets one ``RuntimeManager`` own a target's components until it is
    closed, and each attempt builds its own manager, so the first attempt's
    manager is closed before the hook runs. If it cannot be released, the retry
    is skipped and the first diagnostic is kept. A failed retry also carries the
    first attempt's diagnostic.
    """

    first = run_attempt()
    if not first.retryable or before_retry is None:
        return first
    release_failure = _release_runtime_owner(first)
    if release_failure is not None:
        log.warning("Automatic backend retry skipped: %s", release_failure)
        return _with_error(
            first, f"{first.lab_result.error}\n{_RETRY_SKIPPED} ({release_failure})."
        )
    before_retry()
    retry = run_attempt()
    if retry.lab_result.success:
        return retry
    return _with_error(
        retry, f"{retry.lab_result.error}\nInitial attempt: {first.lab_result.error}"
    )


def _release_runtime_owner(outcome: AcesStartOutcome) -> str | None:
    """Close the attempt's manager; return why it stayed open, if it did."""

    manager = outcome.runtime_manager
    if manager is None:
        return None
    try:
        manager.close()
    except (RuntimeError, TimeoutError) as exc:
        # RAES refuses while callbacks run or its clock driver does not stop.
        return redact(f"{type(exc).__name__}: {exc}")
    return None


def _with_error(outcome: AcesStartOutcome, error: str) -> AcesStartOutcome:
    return replace(outcome, lab_result=replace(outcome.lab_result, error=error))
