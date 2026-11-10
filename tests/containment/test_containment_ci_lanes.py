"""Only the dedicated CI job selects the containment proof (review finding).

The proof needs the engine submodule and two host phases with opposite
user-namespace states, so the default run and the catch-all integration lane
must not collect it.
"""

import shlex
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "checks.yml"


def _marker_expressions(job: str) -> list[str]:
    """Return the pytest marker expressions of the job's LilRAE test commands."""
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"][job]["steps"]
    expressions = []
    for step in steps:
        words = shlex.split(step.get("run", "").replace("\\\n", " "))
        if not any(word.startswith("tests/") for word in words):
            continue
        expressions += [
            words[index + 1]
            for index, word in enumerate(words)
            if word == "-m" and not words[index - 1].endswith("python")
        ]
    return expressions


def _collected(*marker_arguments: str) -> set[str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *marker_arguments, "tests/containment"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    assert completed.returncode in {0, 5}, completed.stdout + completed.stderr
    return {line.split("::")[0] for line in completed.stdout.splitlines() if "::" in line}


def _proof_selected(nodes: set[str]) -> bool:
    return "tests/containment/test_containment_proof.py" in nodes


def test_the_default_run_excludes_the_containment_proof() -> None:
    assert not _proof_selected(_collected())


def test_the_catch_all_integration_lane_excludes_the_containment_proof() -> None:
    (expression,) = [
        item for item in _marker_expressions("integration-qualification") if "integration" in item
    ]

    assert not _proof_selected(_collected("-m", expression))


def test_the_containment_job_selects_the_proof() -> None:
    expressions = _marker_expressions("containment-proof")

    assert expressions and set(expressions) == {"containment"}
    assert _proof_selected(_collected("-m", "containment"))
