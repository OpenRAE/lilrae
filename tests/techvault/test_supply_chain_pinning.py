"""The verification-artifact job runs the TechVault wheel test (#1700)."""

from __future__ import annotations

from tests.test_supply_chain_pinning import WORKFLOW_DIR


def test_scenario_verification_artifact_boundary_runs_in_ci() -> None:
    """The core-only/plugin-installed wheel proof must not be an optional local test."""

    import yaml

    workflow = yaml.safe_load((WORKFLOW_DIR / "checks.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["scenario-verification-artifacts"]
    commands = "\n".join(
        str(step.get("run", "")) for step in job["steps"] if "run" in step
    )

    # This job executes pytest as well as building wheels, so it needs the
    # hash-locked development/test export rather than the CI-tool-only export.
    assert "pip install --require-hashes -r requirements/dev.txt" in commands
    assert "tests/techvault/test_scenario_verification_artifacts.py" in commands
    assert "-m integration" in commands
