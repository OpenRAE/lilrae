"""Lab start's single backend retry against the real RAES runtime owner.

raes 7 lets one ``RuntimeManager`` own a target's components until it is
closed, so the retry must release the first attempt's manager before it builds
the second. The deployment backend and the retry hook are modelled. The runtime
manager, its RAES claim, and ``close()`` are real; the skip test subclasses the
real manager only to leave a clock driver that does not stop. The CLI test
replaces only the lab steps around the handoff.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from aptl.backends import raes
from aptl.backends.raes_planning_compat import AptlRuntimeManager
from aptl.core.config import AptlConfig
from aptl.core.lab_types import LabResult
from tests.test_raes_backend import (
    _bundle,
    _execution_plan_with_realization_requirements,
    _RealizedBackend,
    _write_compose,
)

_START_FAILED = "aptl.provisioner.backend-start-failed"
_FIRST_ERROR = "Node wazuh-dashboard exited after compose start"
_RETRY_ERROR = "Node shuffle-backend exited after compose start"
_CONFIG = AptlConfig(lab={"name": "test"}, containers={"victim": True})


def _realized_backend(*realize_results: LabResult) -> _RealizedBackend:
    """Model a daemon that runs ``vm`` and answers each apply in turn."""

    backend = _RealizedBackend(containers=("vm",), platform="linux")
    if realize_results:
        backend.realize.side_effect = list(realize_results)
    return backend


def _target(tmp_path: Path, backend: _RealizedBackend):
    _write_compose(tmp_path, {"vm": ["victim"]})
    return raes.create_aptl_runtime_target(
        project_dir=tmp_path,
        bundle=_bundle(tmp_path),
        config=_CONFIG,
        backend=backend,
    )


def _start(tmp_path: Path, target, before_retry):
    return raes._apply_with_backend_retry(
        target,
        _execution_plan_with_realization_requirements(),
        tmp_path / "scenarios" / "demo.sdl.yaml",
        None,
        before_retry,
    )


def _failed(error: str) -> LabResult:
    return LabResult(success=False, error=error)


def _started() -> LabResult:
    return LabResult(success=True, message="ok")


def _assert_still_owned(target) -> None:
    """RAES refuses a second manager while an open one owns the target."""

    with pytest.raises(RuntimeError, match="already has a runtime owner"):
        AptlRuntimeManager(target)


def test_retry_releases_the_first_runtime_owner_and_starts(tmp_path):
    """The live crash: raes 7 refused the retry's second runtime manager."""

    backend = _realized_backend(_failed(_FIRST_ERROR), _started())
    applies_before_hook = []
    before_retry = MagicMock(
        side_effect=lambda: applies_before_hook.append(backend.realize.call_count)
    )

    target = _target(tmp_path, backend)

    result = _start(tmp_path, target, before_retry)

    assert result.lab_result.success is True, result.lab_result.error
    assert backend.realize.call_count == 2
    assert applies_before_hook == [1]
    assert isinstance(result.runtime_manager, AptlRuntimeManager)
    _assert_still_owned(target)


def test_failed_retry_reports_both_attempts(tmp_path):
    backend = _realized_backend(_failed(_FIRST_ERROR), _failed(_RETRY_ERROR))
    before_retry = MagicMock()

    result = _start(tmp_path, _target(tmp_path, backend), before_retry)

    error = result.lab_result.error
    assert result.lab_result.success is False
    assert backend.realize.call_count == 2
    before_retry.assert_called_once_with()
    assert error.count(_START_FAILED) == 2
    retry_part, initial_part = error.split("\nInitial attempt: ")
    assert _RETRY_ERROR in retry_part
    assert _FIRST_ERROR not in retry_part
    assert _FIRST_ERROR in initial_part
    assert _START_FAILED in initial_part


class _StuckClockDriver:
    """A participant clock driver that does not stop when asked."""

    active = True
    failure = None

    def stop(self) -> bool:
        return False


class _ManagerWithStuckClock(AptlRuntimeManager):
    """The real manager, left with a clock driver that outlives its apply."""

    def apply(self, execution_plan):
        result = super().apply(execution_plan)
        self._participant_clock_driver = _StuckClockDriver()
        return result


def test_unreleasable_first_owner_skips_the_retry(mocker, tmp_path):
    mocker.patch("aptl.backends.raes.RuntimeManager", _ManagerWithStuckClock)
    backend = _realized_backend(_failed(_FIRST_ERROR), _started())
    before_retry = MagicMock()

    result = _start(tmp_path, _target(tmp_path, backend), before_retry)

    error = result.lab_result.error
    assert result.lab_result.success is False
    assert backend.realize.call_count == 1
    before_retry.assert_not_called()
    assert _START_FAILED in error
    assert _FIRST_ERROR in error
    assert "Automatic retry skipped" in error
    assert "runtime manager clock driver remains active" in error
    assert "Initial attempt" not in error


@pytest.mark.parametrize(
    ("backend_factory", "hook", "started"),
    [
        pytest.param(
            lambda: _realized_backend(_started()),
            MagicMock(),
            True,
            id="first-attempt-starts",
        ),
        pytest.param(
            lambda: _RealizedBackend(containers=()),
            MagicMock(),
            False,
            id="non-retryable-first-failure",
        ),
        pytest.param(
            lambda: _realized_backend(_failed(_FIRST_ERROR)),
            None,
            False,
            id="no-admitted-retry-hook",
        ),
    ],
)
def test_first_attempt_without_retry_keeps_its_owner(
    tmp_path, backend_factory, hook, started
):
    backend = backend_factory()
    target = _target(tmp_path, backend)

    result = _start(tmp_path, target, hook)

    error = result.lab_result.error or ""
    assert result.lab_result.success is started, error
    assert backend.realize.call_count == 1
    assert "Initial attempt" not in error
    assert "Automatic retry skipped" not in error
    assert isinstance(result.runtime_manager, AptlRuntimeManager)
    _assert_still_owned(target)
    if hook is not None:
        hook.assert_not_called()


def test_lab_start_json_reports_both_attempts_after_a_failed_retry(mocker, tmp_path):
    """``lilrae lab start --json`` printed nothing when the retry crashed.

    Only the lab steps around the RAES handoff and ``time.sleep`` are replaced;
    the handoff, lab start's retry callback and the runtime manager are real.
    """
    from aptl.backends.raes_start_model import AdmittedScenarioStart
    from aptl.backends.scenario_startup import ScenarioStartupPlan, StartupHook
    from aptl.cli.main import app
    from aptl.core.lab import _LabStartContext, _step_start_containers

    backend = _realized_backend(_failed(_FIRST_ERROR), _failed(_RETRY_ERROR))
    bundle = _bundle(tmp_path)
    ctx = _LabStartContext(project_dir=tmp_path, skip_seed=False)
    ctx.config = _CONFIG
    ctx.backend = backend
    ctx.admitted_start = AdmittedScenarioStart(
        bundle=bundle,
        target=_target(tmp_path, backend),
        execution_plan=_execution_plan_with_realization_requirements(),
        realization=None,
    )
    ctx.scenario_startup = ScenarioStartupPlan(
        seed_script="scripts/seed.sh",
        required_profiles=(),
        activation_profiles=(),
        startup_hooks=frozenset({StartupHook.BEFORE_BACKEND_RETRY}),
    )
    sleep = mocker.patch("time.sleep")
    mocker.patch(
        "aptl.cli.lab.orchestrate_lab_start",
        side_effect=lambda *_args, **_kwargs: _step_start_containers(ctx),
    )

    result = CliRunner().invoke(app, ["lab", "start", "--json"])

    payload = json.loads(result.stdout)
    error = payload["error"]
    assert result.exit_code == 1
    assert payload["ok"] is False
    assert error.count(_START_FAILED) == 2
    assert _RETRY_ERROR in error
    assert _FIRST_ERROR in error
    assert f"Initial attempt: RAES runtime handoff failed: {_START_FAILED}" in error
    assert backend.realize.call_count == 2
    sleep.assert_called_once_with(60)
