"""Contracts for issue #1114 documentation publishing and badge evidence."""

from __future__ import annotations

import json
from pathlib import Path
import shlex

import yaml


ROOT = Path(__file__).parents[1]


def test_reader_routes_keep_real_pages_and_home() -> None:
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8").replace(
        "!!python/name:pymdownx.superfences.fence_code_format",
        "'pymdownx.superfences.fence_code_format'",
    )
    nav = yaml.safe_load(text)["nav"]
    routes = {key: value for entry in nav for key, value in entry.items()}
    assert routes["Home"] == "index.md"
    def check_targets(entries: list[dict]) -> None:
        for entry in entries:
            for target in entry.values():
                if isinstance(target, str):
                    if "://" in target:
                        continue
                    assert (ROOT / "docs" / target).is_file(), target
                else:
                    check_targets(target)

    for route in ("Tutorials", "How-to guides", "Reference", "Explanation"):
        assert routes[route]
        check_targets(routes[route])


def _yaml(relative_path: str) -> dict[str, object]:
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


#: The generic documentation checks the docs lane runs.
DOCS_LANE_GENERIC_TESTS = frozenset({
    "tests/test_documentation_checks.py", "tests/test_docs_publishing.py",
    "tests/test_docs_user_journey.py", "tests/test_scenario_pack_ownership_contract.py",
    "tests/test_hosted_seat_helper.py", "tests/test_stage_hosted_seat_payload.py",
})


def docs_lane_test_paths() -> set[str]:
    """Return the test paths of the docs lane's one unconditional pytest step."""
    docs = _yaml(".github/workflows/checks.yml")["jobs"]["docs"]
    commands = [
        (step, shlex.split(step["run"]))
        for step in docs["steps"] if "run" in step
    ]
    tests = [(step, args) for step, args in commands if args[:3] == ["python", "-m", "pytest"]]
    assert len(tests) == 1
    step, args = tests[0]
    assert "if" not in step
    return set(args[4:])


def test_docs_lane_runs_targeted_behavior_checks_without_runtime_selection() -> None:
    paths = docs_lane_test_paths()

    assert DOCS_LANE_GENERIC_TESTS <= paths
    assert all((ROOT / path).is_file() for path in paths)


def test_read_the_docs_reuses_the_strict_canonical_mkdocs_build() -> None:
    config = _yaml(".readthedocs.yaml")

    assert config["version"] == 2
    assert config["mkdocs"] == {
        "configuration": "mkdocs.yml",
        "fail_on_warning": True,
    }
    assert config["python"]["install"] == [
        {"requirements": "requirements/docs.txt"}
    ]

    jobs = config["build"]["jobs"]
    assert any("--unshallow" in command for command in jobs["post_checkout"])
    assert jobs["post_install"] == [
        "pip install -e . --no-deps --no-build-isolation"
    ]


def test_both_publishers_require_full_history_and_one_source_tree() -> None:
    pages = _yaml(".github/workflows/docs-deploy.yml")
    checkout = pages["jobs"]["build"]["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0

    read_the_docs = _yaml(".readthedocs.yaml")
    assert read_the_docs["mkdocs"]["configuration"] == "mkdocs.yml"
    assert "requirements/docs.txt" in json.dumps(read_the_docs)


def test_badge_proposals_link_to_real_public_evidence() -> None:
    proposals = json.loads(
        (ROOT / ".bestpractices.json").read_text(encoding="utf-8")
    )

    required = {
        "description_good_justification": "https://openrae.github.io/lilrae/",
        "contribution_justification": (
            "https://github.com/OpenRAE/lilrae/blob/main/CONTRIBUTING.md"
        ),
        "documentation_basics_justification": (
            "https://openrae.github.io/lilrae/getting-started/"
        ),
        "documentation_interface_justification": (
            "https://openrae.github.io/lilrae/reference/cli/"
        ),
        "report_process_justification": (
            "https://github.com/OpenRAE/lilrae/blob/main/SUPPORT.md"
        ),
    }
    assert {key: proposals.get(key) for key in required} == required

    for key in required:
        assert proposals[key].startswith("https://")
