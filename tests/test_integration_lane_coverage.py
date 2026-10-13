"""Every integration-marked test runs in a CI lane or says why it cannot (#1321).

The general lanes in `.github/workflows/checks.yml` used `-k "not integration"`.
`-k` matches file and class names as well as markers, so it also dropped the
unmarked tests in `test_api_integration.py` and `test_cortex_integration_config.py`,
and nothing checked that the integration-marked tests it excluded ran anywhere
else. Nineteen files of them ran in no lane, and two had gone stale.

This module reads every `pytest` command in `checks.yml`, works out which tests
each one selects by its `-m` expression and path arguments, and compares that
with what pytest itself collects as integration-marked. Collection is the
authority: decorators, `pytestmark`, class marks and `pytest.param` marks all
count. A test that needs a live lab instead of a hosted runner goes in
`LIVE_LAB_ONLY` with its reason and the command that runs it.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "checks.yml"

# Integration-marked tests no hosted lane can run, each with its reason and how
# to run it. An entry that a lane selects, or that is no longer collected as
# integration-marked, fails the check, so the list cannot go stale.
LIVE_LAB_ONLY: dict[str, str] = {
    "tests/test_techvault_live_gate.py::test_live_gate_passes_on_techvault": (
        "Deploys the full TechVault range and tears it down, which a hosted "
        "runner cannot hold; gated by APTL_LIVE_GATE=1. On a lab host run "
        "`APTL_LIVE_GATE=1 pytest tests/test_techvault_live_gate.py -m integration` "
        "(docs/raes/techvault-live-validation-gate.md)."
    ),
}

# What each `-m` form a lane uses selects: (integration-marked tests, tests
# with neither the integration nor the fuzz marker). A closed table rather than
# an expression evaluator: an unknown form fails until someone adds it here.
MARKER_FORMS: dict[str, tuple[bool, bool]] = {
    "integration": (True, False),
    "not integration and not fuzz": (False, True),
    "fuzz and not integration": (False, False),
    "not fuzz": (True, True),
}

_VALUE_OPTIONS = frozenset({"-m", "-k", "-n", "-p"})
_MATRIX_REF = re.compile(r"\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}")
_API_AND_CORTEX = (
    "tests/test_api_integration.py",
    "tests/test_cortex_integration_config.py",
)


@dataclass(frozen=True)
class PytestConfig:
    marker: str
    testpaths: tuple[str, ...]


@dataclass(frozen=True)
class Lane:
    job: str
    command: str
    marker: str
    keyword: str | None
    paths: tuple[str, ...]

    def selects(self, node_or_path: str) -> bool:
        return any(
            node_or_path == path
            or node_or_path.startswith(f"{path}::")
            or node_or_path.startswith(f"{path.rstrip('/')}/")
            for path in self.paths
        )


def _pytest_config() -> PytestConfig:
    options = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ini = options["tool"]["pytest"]["ini_options"]
    addopts = shlex.split(ini.get("addopts", ""))
    marker = addopts[addopts.index("-m") + 1] if "-m" in addopts else ""
    return PytestConfig(marker=marker, testpaths=tuple(ini.get("testpaths", ())))


def _job_commands(job: dict) -> list[str]:
    """Every shell line a job runs, once per matrix row, continuations joined."""

    rows = ((job.get("strategy") or {}).get("matrix") or {}).get("include") or [{}]
    lines: list[str] = []
    for step in job.get("steps") or []:
        run = step.get("run")
        if not run:
            continue
        for row in rows:
            text = _MATRIX_REF.sub(
                lambda ref, row=row: str(row.get(ref.group(1), ref.group(0))), run
            )
            lines.extend(text.replace("\\\n", " ").splitlines())
    return lines


def _pytest_arguments(line: str) -> list[str] | None:
    """The arguments of a `pytest` / `-m pytest` command, or None for others."""

    if "pytest" not in line:
        return None
    try:
        tokens = shlex.split(line)
    except ValueError:
        return None
    for index, token in enumerate(tokens):
        if token == "pytest" and (index == 0 or tokens[index - 1] == "-m"):
            return tokens[index + 1 :]
    return None


def _lane(job: str, line: str, arguments: list[str], config: PytestConfig) -> Lane:
    marker, keyword, paths = config.marker, None, []
    tokens = iter(arguments)
    for token in tokens:
        if token in _VALUE_OPTIONS:
            value = next(tokens, "")
            marker = value if token == "-m" else marker
            keyword = value if token == "-k" else keyword
        elif not token.startswith("-"):
            paths.append(token.removeprefix("./"))
    return Lane(
        job=job,
        command=line.strip(),
        marker=marker,
        keyword=keyword,
        paths=tuple(paths) or config.testpaths,
    )


def workflow_lanes(workflow: dict, config: PytestConfig) -> list[Lane]:
    lanes: list[Lane] = []
    for job_id, job in (workflow.get("jobs") or {}).items():
        for line in _job_commands(job):
            arguments = _pytest_arguments(line)
            if arguments is not None:
                lanes.append(_lane(job_id, line, arguments, config))
    return lanes


def _lane_problems(lanes: list[Lane]) -> list[str]:
    problems: list[str] = []
    for lane in lanes:
        if lane.keyword is not None:
            problems.append(
                f"{lane.job}: selects by -k {lane.keyword!r}, which also matches "
                f"file and class names; select by -m instead: {lane.command}"
            )
        if lane.marker not in MARKER_FORMS:
            problems.append(
                f"{lane.job}: unknown -m form {lane.marker!r}; add it to "
                f"MARKER_FORMS in {Path(__file__).name}: {lane.command}"
            )
    return problems


def _live_lab_problems(
    integration_ids: set[str], selected: set[str], live_lab: dict[str, str]
) -> list[str]:
    problems: list[str] = []
    for node, reason in live_lab.items():
        if node not in integration_ids:
            problems.append(
                f"{node}: listed live-lab test is not collected as integration-marked"
            )
        elif node in selected:
            problems.append(
                f"{node}: listed live-lab test is selected by a lane; remove its entry"
            )
        if not reason.strip():
            problems.append(f"{node}: listed live-lab test has no reason")
    return problems


def audit(
    workflow: dict,
    integration_ids: set[str],
    live_lab: dict[str, str],
    config: PytestConfig,
) -> list[str]:
    """Return every way the lanes and the live-lab list fail to cover the tests."""

    lanes = workflow_lanes(workflow, config)
    # A `-k` expression cannot be read from the workflow alone, so a lane that
    # uses one is counted as selecting nothing (and reported above).
    integration_lanes = [
        lane
        for lane in lanes
        if lane.keyword is None and MARKER_FORMS.get(lane.marker, (False, False))[0]
    ]
    selected = {
        node
        for node in integration_ids
        if any(lane.selects(node) for lane in integration_lanes)
    }
    orphans = sorted(integration_ids - selected - set(live_lab))
    return [
        *_lane_problems(lanes),
        *(
            f"{node}: integration-marked but selected by no checks.yml lane and "
            f"not in LIVE_LAB_ONLY (file {node.split('::', 1)[0]})"
            for node in orphans
        ),
        *_live_lab_problems(integration_ids, selected, live_lab),
    ]


def _collect(marker: str, *paths: str, keyword: str | None = None) -> set[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            marker,
            *(["-k", keyword] if keyword is not None else []),
            *paths,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    # Exit code 5 means nothing was collected: an empty selection, not an error.
    assert result.returncode in (0, 5), result.stdout[-2000:] + result.stderr[-2000:]
    return {line for line in result.stdout.splitlines() if "::" in line}


@pytest.fixture(scope="module")
def checks_workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_every_integration_test_has_a_lane_or_a_live_lab_reason(checks_workflow):
    integration_ids = _collect("integration", "tests/")
    assert integration_ids, "collection found no integration-marked tests"

    problems = audit(checks_workflow, integration_ids, LIVE_LAB_ONLY, _pytest_config())

    assert problems == [], "\n".join(problems)


def test_the_coverage_lane_runs_the_unmarked_api_and_cortex_tests(checks_workflow):
    (lane,) = [
        lane
        for lane in workflow_lanes(checks_workflow, _pytest_config())
        if lane.job == "python-tests" and lane.command.startswith("coverage run")
    ]

    assert all(lane.selects(path) for path in _API_AND_CORTEX), lane
    collected = {
        node.split("::", 1)[0]
        for node in _collect(lane.marker, *_API_AND_CORTEX, keyword=lane.keyword)
    }
    assert collected == set(_API_AND_CORTEX)


_CONFIG = PytestConfig(marker="not fuzz", testpaths=("tests",))
_LIVE = "tests/test_live.py::test_boot"
_DOCKER = "tests/test_docker.py::test_up"


def _workflow(*runs: str, matrix: list[dict] | None = None) -> dict:
    job: dict = {"steps": [{"run": run} for run in runs]}
    if matrix is not None:
        job["strategy"] = {"matrix": {"include": matrix}}
    return {"jobs": {"lane": job}}


_GENERAL = 'python -m pytest tests/ -q -m "not integration and not fuzz"'


@pytest.mark.parametrize(
    ("workflow", "live_lab", "expected"),
    [
        pytest.param(
            _workflow(
                _GENERAL,
                "python -m pytest -q -m integration \\\n  tests/test_docker.py",
            ),
            {_LIVE: "needs a lab"},
            [],
            id="continued-file-lane-and-live-lab-entry-cover-everything",
        ),
        pytest.param(
            _workflow(_GENERAL),
            {_LIVE: "needs a lab"},
            [f"{_DOCKER}: integration-marked but selected by no checks.yml lane"],
            id="orphan-is-reported-with-its-file",
        ),
        pytest.param(
            _workflow('python -m pytest tests/ -q -k "not integration"'),
            {_LIVE: "needs a lab"},
            [
                "lane: selects by -k 'not integration'",
                f"{_DOCKER}: integration-marked but selected by no checks.yml lane",
            ],
            id="keyword-selection-is-rejected",
        ),
        pytest.param(
            _workflow(f"python -m pytest -m 'docker or integration' {_DOCKER}"),
            {_LIVE: "needs a lab"},
            [
                "lane: unknown -m form 'docker or integration'",
                f"{_DOCKER}: integration",
            ],
            id="unknown-marker-form-fails-closed",
        ),
        pytest.param(
            _workflow(
                f"python -m pytest -q -m integration tests/test_docker.py {_LIVE}"
            ),
            {_LIVE: "needs a lab"},
            [f"{_LIVE}: listed live-lab test is selected by a lane"],
            id="stale-live-lab-entry-is-rejected",
        ),
        pytest.param(
            _workflow(f"python -m pytest -m integration {_DOCKER}"),
            {_LIVE: " ", "tests/test_gone.py::test_x": "removed"},
            [
                f"{_LIVE}: listed live-lab test has no reason",
                "tests/test_gone.py::test_x: listed live-lab test is not collected",
            ],
            id="live-lab-entry-needs-a-reason-and-a-collected-test",
        ),
        pytest.param(
            _workflow("python -m pytest"),
            {},
            [],
            id="addopts-marker-and-testpaths-apply-without-arguments",
        ),
        pytest.param(
            _workflow(f"coverage run -m pytest -m integration {_DOCKER}"),
            {_LIVE: "needs a lab"},
            [],
            id="node-id-argument-selects-that-test",
        ),
        pytest.param(
            _workflow("python -m pytest -m integration tests/test_docker.py::test_u"),
            {_LIVE: "needs a lab"},
            [f"{_DOCKER}: integration-marked but selected by no checks.yml lane"],
            id="node-id-prefix-selects-nothing-else",
        ),
        pytest.param(
            _workflow(
                "python -m pytest ${{ matrix.args }}",
                matrix=[
                    {"args": _GENERAL.split("pytest ", 1)[1]},
                    {"args": f"-m integration {_DOCKER}"},
                ],
            ),
            {_LIVE: "needs a lab"},
            [],
            id="matrix-values-are-expanded-per-row",
        ),
    ],
)
def test_audit_rules(workflow, live_lab, expected):
    problems = audit(workflow, {_LIVE, _DOCKER}, live_lab, _CONFIG)

    assert len(problems) == len(expected), problems
    for prefix, problem in zip(expected, problems, strict=True):
        assert problem.startswith(prefix), problems
