"""Structural gate for the first-time user documentation in issue #851."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shlex

import yaml
from typer.main import get_command

from aptl.api.routers import config, kill, lab, scenarios, terminal
from aptl.cli.main import app as cli_app
from aptl.core.opencode import SUPPORTED_OPENCODE_BUILD


ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"


def _document(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _section(relative_path: str, heading: str) -> str:
    document = _document(relative_path)
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", document
    )
    assert match is not None, f"{relative_path} must contain a {heading!r} section"
    return match.group(1)


def _table(relative_path: str, heading: str) -> list[dict[str, str]]:
    lines = [
        line
        for line in _section(relative_path, heading).splitlines()
        if line.startswith("|")
    ]
    assert len(lines) >= 3, f"{relative_path} {heading!r} must contain a table"
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def _links(document: str) -> dict[str, str]:
    return {
        label: target
        for label, target in re.findall(r"\[([^]]+)]\(([^)]+)\)", document)
    }


def _headings(relative_path: str) -> list[str]:
    return re.findall(r"(?m)^## (.+)$", _document(relative_path))


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")


def test_navigation_puts_operator_tasks_before_design_records() -> None:
    mkdocs = _document("mkdocs.yml").replace(
        "!!python/name:pymdownx.superfences.fence_code_format",
        "'pymdownx.superfences.fence_code_format'",
    )
    nav = yaml.safe_load(mkdocs)["nav"]
    top_level = [next(iter(item)) for item in nav]

    assert top_level[:4] == ["Home", "Tutorials", "How-to guides", "Reference"]
    assert top_level.index("How-to guides") < top_level.index("Explanation")
    assert top_level.index("Reference") < top_level.index("Decisions")


def test_home_links_directly_to_the_complete_first_time_journey() -> None:
    links = _links(_document("docs/index.md"))
    task_targets = {
        "Check prerequisites": "getting-started/prerequisites.md",
        "Install LilRAE": "getting-started/installation.md",
        "Start and verify the lab": (
            "getting-started/quick-start.md#start-and-verify-the-lab"
        ),
        "Choose a scenario": "getting-started/quick-start.md#choose-a-scenario",
        "Inspect the running lab": (
            "getting-started/quick-start.md#inspect-the-running-lab"
        ),
        "Generate safe test activity": (
            "getting-started/quick-start.md#generate-safe-test-activity"
        ),
        "Inspect results": "getting-started/quick-start.md#inspect-results",
        "Troubleshoot": "troubleshooting/index.md",
        "Stop or reset the lab": (
            "getting-started/quick-start.md#stop-or-reset-the-lab"
        ),
    }
    assert {label: links.get(label) for label in task_targets} == task_targets

    for target in task_targets.values():
        path_text, _, fragment = target.partition("#")
        target_path = DOCS / path_text
        assert target_path.is_file()
        if fragment:
            assert fragment in {
                _slug(heading) for heading in _headings(f"docs/{path_text}")
            }


def test_quick_start_follows_the_operator_workflow_in_order() -> None:
    headings = _headings("docs/getting-started/quick-start.md")
    required_order = [
        "Choose The Execution Boundary",
        "Choose A Scenario",
        "Start And Verify The Lab",
        "Inspect The Running Lab",
        "Generate Safe Test Activity",
        "Inspect Results",
        "Stop Or Reset The Lab",
    ]
    assert [heading for heading in headings if heading in required_order] == required_order


def test_workshop_routes_separate_setup_from_learning() -> None:
    """A learner can reach setup, recovery and cleanup without design records."""
    tutorial = _links(_document("docs/workshop/walkthrough.md"))
    setup = _links(_document("docs/workshop/setup.md"))
    assert "setup.md" in tutorial.values()
    assert "setup.md#recover-a-session" in tutorial.values()
    assert "setup.md#clean-up" in tutorial.values()
    assert "walkthrough.md" in setup.values()
    for document in ("docs/workshop/walkthrough.md", "docs/workshop/setup.md"):
        for target in _links(_document(document)).values():
            if "://" in target:
                continue
            path, _, fragment = target.partition("#")
            destination = ROOT / document
            destination = destination.parent / path if path else destination
            assert destination.is_file(), target
            if fragment:
                headings = re.findall(
                    r"(?m)^#{1,6} (.+)$", destination.read_text(encoding="utf-8")
                )
                assert fragment in {_slug(heading) for heading in headings}, target


def test_split_operator_pages_are_reachable_from_reader_navigation() -> None:
    """Every split page has a reader route; source archives remain separate."""
    mkdocs = _document("mkdocs.yml").replace(
        "!!python/name:pymdownx.superfences.fence_code_format",
        "'pymdownx.superfences.fence_code_format'",
    )

    def targets(value: object) -> set[str]:
        if isinstance(value, str):
            return {value}
        if isinstance(value, list):
            return set().union(*(targets(item) for item in value))
        if isinstance(value, dict):
            return set().union(*(targets(item) for item in value.values()))
        return set()

    nav = yaml.safe_load(mkdocs)["nav"]
    routes = {next(iter(item)): targets(item) for item in nav}
    assert {
        "getting-started/host-requirements.md",
        "getting-started/installation-reference.md",
        "getting-started/pack-reference.md",
        "troubleshooting/diagnostics.md",
        "components/wazuh-siem.md",
        "components/wazuh-active-response.md",
        "components/victim-containers.md",
        "reference/opencode-participants.md",
        "reference/windows-endpoint.md",
        "sdl/curated-variant-reference.md",
        "raes/techvault-static-validation-gate.md",
        "raes/techvault-live-validation-gate.md",
        "workshop/reference.md",
        "workshop/hosted-backup-reference.md",
    } <= routes["Reference"]
    assert {
        "workshop/setup.md",
        "troubleshooting/search-index-backup.md",
        "sdl/index.md",
        "sdl/techvault-curated-variants.md",
        "containers/victim-template-guide.md",
        "components/victim-operations.md",
        "components/kali-operations.md",
        "reference/source-image-maintenance.md",
        "components/wazuh-operations.md",
        "components/wazuh-response-operations.md",
        "components/defensive-posture-operations.md",
        "components/appliance-qualification.md",
        "raes/scenario-validation.md",
        "raes/live-validation.md",
        "raes/install-cleanup.md",
        "reference/appliance-seat-operations.md",
        "reference/evidence-bundle-operations.md",
        "reference/host-mcp-operations.md",
        "reference/mcp-operations.md",
        "reference/opencode-operations.md",
        "reference/project-configuration.md",
        "reference/migrate-configuration.md",
        "reference/run-operations.md",
        "reference/web-proxy.md",
        "reference/family-adapter-operations.md",
        "reference/participant-request-operations.md",
        "components/workbench-composition.md",
    } <= routes["How-to guides"]
    assert {"sdl/paper-walkthrough.md", "workshop/walkthrough.md"} <= routes["Tutorials"]
    assert {
        "getting-started/execution-boundaries.md",
        "getting-started/environment-bindings.md",
        "reference/seat-containment.md",
        "components/red-side-capture-boundary.md",
        "sdl/runtime-architecture.md",
        "components/techvault-adapter-boundary.md",
    } <= routes["Explanation"]
    for target in set().union(*routes.values()):
        assert (DOCS / target).is_file(), target

    split_pages = {
        "reference/appliance-seat-launcher.md": "reference/appliance-seat-operations.md",
        "reference/host-mcp-access.md": "reference/host-mcp-operations.md",
        "reference/evidence-bundle-export.md": "reference/evidence-bundle-operations.md",
        "reference/opencode-participants.md": "reference/opencode-operations.md",
        "reference/family-adapters.md": "reference/family-adapter-operations.md",
        "reference/participant-request-manifests.md": "reference/participant-request-operations.md",
        "raes/techvault-static-validation-gate.md": "raes/scenario-validation.md",
        "raes/techvault-live-validation-gate.md": "raes/live-validation.md",
    }
    for source, guide in split_pages.items():
        for origin, destination in ((source, guide), (guide, source)):
            links = {
                (DOCS / origin).parent / target.split("#", 1)[0]
                for target in _links(_document(f"docs/{origin}")).values()
                if "://" not in target
            }
            assert (DOCS / destination) in links, (origin, destination)


def test_cli_reference_tracks_every_registered_command_group() -> None:
    rows = _table("docs/reference/cli.md", "Command Groups")
    documented = {row["Command"].removeprefix("lilrae ") for row in rows}
    registered = set(get_command(cli_app).commands)

    assert documented == registered

    # Check the documented command paths and flags against the real CLI.
    # This detects renamed/removed subcommands and options without running a lab.
    root = get_command(cli_app)
    for row in _table("docs/reference/cli.md", "First-Lab Commands"):
        arguments = shlex.split(row["Command"])[1:]
        command = root
        while arguments and hasattr(command, "commands"):
            name = arguments.pop(0)
            assert name in command.commands, row["Command"]
            command = command.commands[name]
        options = {
            option
            for parameter in command.params
            for option in (*parameter.opts, *parameter.secondary_opts)
        }
        assert {value for value in arguments if value.startswith("-")} <= options


def test_mcp_reference_tracks_built_and_enabled_server_surfaces() -> None:
    rows = _table("docs/reference/mcp.md", "Server Availability")
    documented = {
        row["Artifact"]: {
            "client": row["Generated client entry"],
            "prefix": row["Tool prefix"],
            "enabled": row["Default client config"] == "yes",
        }
        for row in rows
    }
    generated = json.loads(_document(".mcp.json.example"))["mcpServers"]
    expected: dict[str, dict[str, str | bool]] = {}
    for config_path in sorted((ROOT / "mcp").glob("mcp-*/docker-lab-config.json")):
        config_doc = json.loads(config_path.read_text(encoding="utf-8"))
        artifact = config_path.parent.name
        client = f"aptl-{artifact.removeprefix('mcp-')}"
        expected[artifact] = {
            "client": client,
            "prefix": config_doc["server"]["toolPrefix"],
            "enabled": client in generated,
        }

    assert documented == expected


def test_web_reference_tracks_cli_defaults_and_supported_api() -> None:
    defaults = {
        row["Setting"]: row["Default"]
        for row in _table("docs/reference/web.md", "Serve Defaults")
    }
    serve = get_command(cli_app).commands["web"].commands["serve"]
    parameters = {parameter.name: parameter.default for parameter in serve.params}
    assert defaults["Bind address"] == parameters["host"]
    assert int(defaults["Port"]) == parameters["port"]

    documented_routes = {
        row["Method and path"]
        for row in _table("docs/reference/web.md", "Supported API Surface")
    }
    runtime_routes = {"GET /api/health", "GET /api/auth/login"}
    for router in (lab.router, config.router, terminal.router, kill.router, scenarios.router):
        for route in router.routes:
            path = f"/api{route.path}"
            methods = getattr(route, "methods", None)
            if methods:
                runtime_routes.update(f"{method} {path}" for method in methods)
            else:
                runtime_routes.add(f"WEBSOCKET {path}")

    assert documented_routes == runtime_routes


def test_support_and_security_actions_use_the_canonical_repository_policies() -> None:
    for relative_path in ("README.md", "docs/index.md"):
        links = _links(_document(relative_path))
        assert links["Contribute"] == (
            "https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md"
        )
        assert links["Get support"] == (
            "https://github.com/OpenRAE/lilrae/blob/dev/SUPPORT.md"
        )
        assert links["Report a vulnerability privately"] == (
            "https://github.com/OpenRAE/lilrae/security/advisories/new"
        )


def test_opencode_reference_matches_the_supported_executable() -> None:
    rows = _table("docs/reference/opencode-participants.md", "Supported build and route")
    values = {row["Identity"]: row["Supported value"] for row in rows}
    assert values["OpenCode"].split(",", 1)[0] == SUPPORTED_OPENCODE_BUILD.version
    assert values["Executable SHA-256"] == SUPPORTED_OPENCODE_BUILD.executable_sha256
