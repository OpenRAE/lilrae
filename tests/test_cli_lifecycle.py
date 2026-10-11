"""CLI tests for the DEP-003 lifecycle commands.

The lifecycle logic itself is covered by ``test_lifecycle_policy.py``. Here
the core entrypoints (`enforce_once`, `run_monitor`), or only the monitor's
tick body (`_monitor_tick`), are patched so no Docker or real lab is touched.
"""

import json

import pytest
import typer
from typer.testing import CliRunner

from aptl.cli.main import app
from aptl.core import lifecycle_enforce as le
from aptl.core.lifecycle_guard import lifecycle_monitor_lock
from aptl.core.lifecycle_policy import LifecycleBusyError
from aptl.core.lab_types import LabResult, StartupOutcome


@pytest.fixture
def runner():
    return CliRunner()


def _write_config(tmp_path, lifecycle_policy=None):
    payload = {"lab": {"name": "aptl"}}
    if lifecycle_policy is not None:
        payload["lifecycle_policy"] = lifecycle_policy
    (tmp_path / "aptl.json").write_text(json.dumps(payload))


_TICK_OK = LabResult(success=True, message="lifecycle: no action (stopped_no_schedule)")
_TICK_SKIPPED = LabResult(
    success=True,
    message="lifecycle: tick skipped (another lab lifecycle operation is active)",
)
_TICK_FAILED = LabResult(
    success=False, message="lifecycle: teardown (ttl_exceeded)", error="boom"
)


def _script_monitor_ticks(monkeypatch, *outcomes):
    """Replace only the monitor's tick body; the CLI and loop stay real.

    Each tick echoes ``tick <n> starts`` and then returns its outcome, or
    raises it when the outcome is an exception. The marker shows which
    results the command printed before the next tick began.
    """
    pending = list(outcomes)
    started = []

    def fake_tick(project_root, policy, backend, grace_minutes):
        started.append(project_root)
        typer.echo(f"tick {len(started)} starts")
        outcome = pending.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(le, "_monitor_tick", fake_tick)


def _invoke_monitor(runner, project_dir, *args):
    return runner.invoke(
        app,
        ["lab", "monitor", "--project-dir", str(project_dir), "--interval", "0", *args],
    )


class TestEnforceCommand:
    def test_help(self, runner):
        result = runner.invoke(app, ["lab", "enforce", "--help"])
        assert result.exit_code == 0
        assert "idempotent" in result.stdout.lower()

    def test_success_prints_message(self, runner, monkeypatch):
        monkeypatch.setattr(
            le,
            "enforce_once",
            lambda *a, **k: LabResult(success=True, message="lifecycle: no action (x)"),
        )
        result = runner.invoke(app, ["lab", "enforce"])
        assert result.exit_code == 0
        assert "lifecycle: no action" in result.stdout

    def test_passes_grace_minutes(self, runner, monkeypatch):
        seen = {}

        def fake(project_dir, **kwargs):
            seen.update(kwargs)
            return LabResult(success=True, message="ok")

        monkeypatch.setattr(le, "enforce_once", fake)
        result = runner.invoke(app, ["lab", "enforce", "--grace-minutes", "15"])
        assert result.exit_code == 0
        assert seen["grace_minutes"] == 15

    def test_failure_exits_nonzero(self, runner, monkeypatch):
        monkeypatch.setattr(
            le,
            "enforce_once",
            lambda *a, **k: LabResult(
                success=False,
                message="lifecycle: teardown (ttl_exceeded)",
                error="boom",
            ),
        )
        result = runner.invoke(app, ["lab", "enforce"])
        assert result.exit_code == 1

    def test_busy_exits_nonzero(self, runner, monkeypatch):
        def raise_busy(*a, **k):
            raise LifecycleBusyError("locked")

        monkeypatch.setattr(le, "enforce_once", raise_busy)
        result = runner.invoke(app, ["lab", "enforce"])
        assert result.exit_code == 1
        assert "locked" in result.stdout + result.stderr


class TestMonitorCommand:
    def test_help(self, runner):
        result = runner.invoke(app, ["lab", "monitor", "--help"])
        assert result.exit_code == 0

    def test_wires_arguments(self, runner, monkeypatch):
        seen = {}

        def fake(project_dir, **kwargs):
            seen.update(kwargs)
            tick = LabResult(success=True, message="tick")
            kwargs["on_result"](tick)
            return [tick]

        monkeypatch.setattr(le, "run_monitor", fake)
        result = runner.invoke(
            app, ["lab", "monitor", "--interval", "30", "--max-ticks", "2"]
        )
        assert result.exit_code == 0
        assert seen["interval_seconds"] == 30
        assert seen["max_ticks"] == 2
        assert "tick" in result.stdout

    def test_prints_each_tick_result_as_it_happens(self, runner, tmp_path, monkeypatch):
        _write_config(tmp_path, {"ttl_minutes": 60})
        _script_monitor_ticks(monkeypatch, _TICK_OK, _TICK_SKIPPED)
        result = _invoke_monitor(runner, tmp_path, "--max-ticks", "2")
        assert result.exit_code == 0
        assert result.stdout.splitlines() == [
            "tick 1 starts",
            _TICK_OK.message,
            "tick 2 starts",
            _TICK_SKIPPED.message,
        ]

    @pytest.mark.parametrize(
        ("first_tick", "exit_code"), [(_TICK_OK, 0), (_TICK_FAILED, 1)]
    )
    def test_ctrl_c_keeps_the_printed_results(
        self, runner, tmp_path, monkeypatch, first_tick, exit_code
    ):
        _write_config(tmp_path, {"ttl_minutes": 60})
        _script_monitor_ticks(monkeypatch, first_tick, KeyboardInterrupt())
        result = _invoke_monitor(runner, tmp_path)
        assert result.exit_code == exit_code
        assert result.stdout.splitlines() == [
            "tick 1 starts",
            first_tick.message,
            "tick 2 starts",
            "monitor stopped.",
        ]

    def test_a_failed_tick_exits_1_after_the_loop_goes_on(
        self, runner, tmp_path, monkeypatch
    ):
        _write_config(tmp_path, {"ttl_minutes": 60})
        _script_monitor_ticks(monkeypatch, _TICK_FAILED, _TICK_OK)
        result = _invoke_monitor(runner, tmp_path, "--max-ticks", "2")
        assert result.exit_code == 1
        assert result.stdout.splitlines()[-1] == _TICK_OK.message
        assert "error: boom" in result.stderr

    def test_invalid_policy_exits_1_like_enforce(self, runner, tmp_path):
        _write_config(tmp_path, {"ttl_minutes": 0})
        monitored = _invoke_monitor(runner, tmp_path, "--max-ticks", "2")
        enforced = runner.invoke(
            app, ["lab", "enforce", "--project-dir", str(tmp_path)]
        )
        assert "lifecycle: invalid configuration" in monitored.stdout
        assert (monitored.exit_code, enforced.exit_code) == (1, 1)

    def test_second_monitor_exits_1(self, runner, tmp_path, monkeypatch):
        _write_config(tmp_path, {"ttl_minutes": 60})
        _script_monitor_ticks(monkeypatch)
        with lifecycle_monitor_lock(tmp_path):
            result = _invoke_monitor(runner, tmp_path, "--max-ticks", "1")
        assert result.exit_code == 1
        assert "another lifecycle monitor is active" in result.stderr


class TestPolicyShowCommand:
    def test_no_policy(self, runner, tmp_path):
        _write_config(tmp_path)
        result = runner.invoke(
            app, ["lab", "policy", "show", "--project-dir", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "No lifecycle_policy configured" in result.stdout

    def test_renders_policy_fields(self, runner, tmp_path):
        _write_config(
            tmp_path,
            {
                "ttl_minutes": 240,
                "schedule": [{"at": "08:00", "days": ["mon"], "scenario": "tv"}],
            },
        )
        result = runner.invoke(
            app, ["lab", "policy", "show", "--project-dir", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "ttl_minutes: 240" in result.stdout
        assert "08:00 UTC [mon] scenario=tv" in result.stdout

    def test_json_output(self, runner, tmp_path):
        _write_config(tmp_path, {"ttl_minutes": 60})
        result = runner.invoke(
            app, ["lab", "policy", "show", "--project-dir", str(tmp_path), "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["policy"]["ttl_minutes"] == 60
        assert payload["state"]["last_action"] == "none"
