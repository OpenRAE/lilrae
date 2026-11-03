"""SonarCloud issue-ignore entries name files that exist (#1510).

A ``resourceKey`` without a wildcard names one file. When that file moves or
goes, the entry is stale: it silences nothing and misstates which code has an
exception. Each listed ``eN`` entry has exactly one rule and one resource.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENTRY = re.compile(
    r"^sonar\.issue\.ignore\.multicriteria\.(e\d+)\.(ruleKey|resourceKey)=(.+)$"
)


def _ignore_entries() -> tuple[list[str], dict[str, dict[str, str]]]:
    listed: list[str] = []
    entries: dict[str, dict[str, str]] = {}
    for line in (
        (ROOT / "sonar-project.properties").read_text(encoding="utf-8").splitlines()
    ):
        if line.startswith("sonar.issue.ignore.multicriteria="):
            listed = line.split("=", 1)[1].split(",")
        elif match := _ENTRY.match(line):
            entries.setdefault(match[1], {})[match[2]] = match[3]
    return listed, entries


def test_each_listed_entry_has_one_rule_and_one_resource() -> None:
    listed, entries = _ignore_entries()

    assert len(listed) == len(set(listed))
    assert set(listed) == set(entries)
    assert all(set(entry) == {"ruleKey", "resourceKey"} for entry in entries.values())


def test_each_literal_resource_names_an_existing_file() -> None:
    _, entries = _ignore_entries()

    missing = sorted(
        {
            entry["resourceKey"]
            for entry in entries.values()
            if "*" not in entry["resourceKey"]
            and not (ROOT / entry["resourceKey"]).is_file()
        }
    )

    assert missing == []


def test_internal_go_files_are_in_the_effective_analysis_scope() -> None:
    """Every product Go file is admitted as source or test, never both."""

    properties = dict(
        line.split("=", 1)
        for line in (ROOT / "sonar-project.properties")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    def under(path: Path, key: str) -> bool:
        return any(
            path.is_relative_to(ROOT / prefix) for prefix in properties[key].split(",")
        )

    def matches(path: Path, key: str) -> bool:
        return any(
            path.relative_to(ROOT).full_match(pattern)
            for pattern in properties[key].split(",")
        )

    missing = []
    for path in (ROOT / "internal").rglob("*.go"):
        if "testdata" in path.parts:
            continue
        source = under(path, "sonar.sources") and not matches(path, "sonar.exclusions")
        test = under(path, "sonar.tests") and matches(path, "sonar.test.inclusions")
        expected_test = path.name.endswith("_test.go")
        if (source, test) != (not expected_test, expected_test):
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, f"Go files outside their analysis role: {sorted(missing)}"
