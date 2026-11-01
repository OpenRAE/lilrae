"""Select existing CI lanes from changed inputs; unknown inputs select all."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

LANES = ("python", "mcp", "web", "docs", "dependencies", "lab", "images", "iac", "go")

# The Go modules of ADR-065: the product module at the root, the tool modules
# below tools/, and the architecture model. web/caddy-build keeps its own
# module and checks.
_GO_PREFIXES = (
    "cmd/", "internal/", "adapter/", "conformance/", "architecture/",
    "tools/cmd/", "tools/internal/", "tools/lint/", "tools/gates/",
    "docs/reference/schemas/", "docs/reference/conformance-inventory.md",
)
_GO_FILES = {"go.mod", "go.sum", ".golangci.yml", "tools/go.mod", "tools/go.sum", "tools/mutation-thresholds.json"}
# The conformance suite (#1554): its cases, the published schemas that they
# check, and the contract inventory that maps each contract to a case.
_CONFORMANCE_PREFIXES = ("conformance/", "docs/reference/schemas/", "docs/reference/conformance-inventory.md")


def select_lanes(paths: list[str], *, full: bool = False) -> dict[str, bool]:
    lanes = dict.fromkeys(LANES, False)
    for path in paths:
        # Dockerfile security is independent of the owning language stack.
        if Path(path).name.startswith("Dockerfile"):
            lanes["iac"] = True
        if path.startswith((".github/", ".gc/", "tools/ci/")) or path in {
            "pyproject.toml", "uv.lock", "hatch_build.py", ".ground-control.yaml",
            ".pre-commit-config.yaml", ".pre-commit-ci.yaml", "AGENTS.md",
        }:
            full = True
        elif path.startswith("requirements/"):
            full = True
        elif path in _GO_FILES or path.startswith(_GO_PREFIXES) or ("/" not in path and path.endswith(".go")):
            # Vale checks Go comments and Markdown, so these select docs too.
            lanes["go"] = True
            lanes["docs"] |= path.endswith((".go", ".md"))
            # The clean-install lab job runs the lab conformance cases. The
            # serialization vectors are data for the Python tests only.
            lanes["lab"] |= path.startswith(_CONFORMANCE_PREFIXES) and not path.startswith(
                "conformance/testdata/vectors/"
            )
        elif path.startswith(("docs/", ".vale/")) or path.endswith(".md") or path in {"mkdocs.yml", ".vale.ini", ".readthedocs.yaml"}:
            lanes["docs"] = True
        elif path.startswith(("src/", "tests/")):
            lanes.update(python=True, mcp=True, lab=True)
            if path.startswith(("src/aptl/api/", "tests/test_api")):
                lanes["web"] = True
        elif path.startswith("mcp/"):
            lanes.update(mcp=True, python=True, lab=True)
            lanes["dependencies"] |= path.endswith(("package.json", "package-lock.json"))
        elif path.startswith("web/"):
            lanes["web"] = True
            lanes["dependencies"] |= path.endswith(("package.json", "package-lock.json"))
        elif path.startswith(("containers/", "config/", "scripts/", "appliance/", "scenarios/")) or path.startswith("docker-compose"):
            lanes.update(python=True, lab=True, iac=True)
        elif path.startswith("tools/vale-"):
            lanes["docs"] = True
        else:
            full = True
    # SonarCloud analyzes the whole project. Never submit partial coverage or
    # reuse an earlier revision's reports to make omitted stacks look covered.
    if any(lanes[name] for name in ("python", "mcp", "web", "go")):
        lanes.update(python=True, mcp=True, web=True, go=True)
    return dict.fromkeys(LANES, True) if full else lanes


def _copied_inputs(dockerfile: Path, context: str) -> list[str]:
    """Read build-context COPY/ADD sources, excluding copies between stages."""
    text = re.sub(r"\\\n\s*", " ", dockerfile.read_text())
    inputs = []
    for line in text.splitlines():
        match = re.match(r"\s*(?:COPY|ADD)\s+(.+)", line, re.IGNORECASE)
        if not match or "--from=" in match[1]:
            continue
        source = re.sub(r"^--\S+\s+", "", match[1])
        words = json.loads(source) if source.startswith("[") else shlex.split(source)
        for word in words[:-1]:
            # An unresolved build variable means the whole context may matter.
            relative = "." if "$" in word else word
            inputs.append((Path(context) / relative).as_posix().rstrip("/"))
    return inputs


def _matches(path: str, source: str) -> bool:
    return source == "." or path == source or path.startswith(source + "/") or fnmatch.fnmatchcase(path, source)


def select_images(paths: list[str], rows: list[dict], root: Path) -> list[str]:
    selected = []
    for row in rows:
        inputs = []
        for prefix in ("", "parent_"):
            dockerfile = row.get(prefix + "dockerfile")
            if dockerfile:
                inputs.append(dockerfile)
                inputs.extend(_copied_inputs(root / dockerfile, row[prefix + "context"]))
        if any(_matches(path, source) for path in paths for source in inputs):
            selected.append(row["name"])
    return selected


def changed_paths(event: dict, event_name: str) -> list[str] | None:
    if event_name == "pull_request":
        base = event["pull_request"]["base"]["sha"]
        revision = base + "...HEAD"
    elif event_name == "push":
        base = event.get("before", "")
        revision = base + "..HEAD"
    else:
        return None
    if not re.fullmatch(r"[0-9a-f]{40}", base) or base == "0" * 40:
        return None
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", "-z", revision],
        capture_output=True, check=False,
    )
    if result.returncode:
        return None
    return [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def main() -> None:
    import yaml

    root = Path.cwd()
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    paths = changed_paths(event, os.environ["GITHUB_EVENT_NAME"])
    lanes = select_lanes(paths or [], full=paths is None)
    workflow = yaml.safe_load((root / ".github/workflows/checks.yml").read_text())
    rows = workflow["jobs"]["trivy-image"]["strategy"]["matrix"]["include"]
    images = [row["name"] for row in rows] if lanes["images"] else select_images(paths or [], rows, root)
    lanes["images"] = bool(images)
    outputs = {name: str(value).lower() for name, value in lanes.items()}
    outputs["selected_images"] = json.dumps(images, separators=(",", ":"))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        stream.writelines(f"{key}={value}\n" for key, value in outputs.items())
    print(json.dumps(outputs, sort_keys=True))


if __name__ == "__main__":
    main()
