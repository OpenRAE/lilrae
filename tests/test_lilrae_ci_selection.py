"""Changed inputs select consumers without hiding unknown changes."""

import importlib.util
from pathlib import Path


def selector():
    path = Path(__file__).resolve().parents[1] / "tools/ci/select_checks.py"
    spec = importlib.util.spec_from_file_location("select_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docs_changes_do_not_select_runtime_but_unknown_paths_do():
    select = selector().select_lanes
    docs = select(["docs/guide.md"])
    assert docs["docs"]
    assert not docs["python"]
    assert not docs["mcp"]
    assert all(select(["new-component/config.ini"]).values())
    assert all(select([], full=True).values())


def test_api_and_common_changes_select_their_consumers():
    select = selector().select_lanes
    assert select(["src/aptl/api/main.py"])["web"]
    for path in (
        "mcp/aptl-mcp-common/src/server.ts",
        "containers/kali-capture/broker.py",
        "tests/test_mcp_capture_lifecycle.py",
    ):
        assert select([path])["mcp"]
    assert select(["uv.lock"])["dependencies"]
    assert select(["tools/ci/select_checks.py"])["python"]


def test_project_wide_analysis_has_complete_current_coverage():
    select = selector().select_lanes
    for path in (
        "web/src/routes/+page.svelte",
        "src/aptl/core/lab.py",
        "mcp/mcp-red/src/index.ts",
    ):
        lanes = select([path])
        assert all(lanes[name] for name in ("python", "mcp", "web"))


def test_every_dockerfile_selects_the_iac_gate():
    select = selector().select_lanes
    for path in (
        "web/Dockerfile",
        "web/Dockerfile.api",
        "containers/base/Dockerfile.ubuntu",
    ):
        assert select([path])["iac"]


def test_image_copy_inputs_and_parent_changes_select_descendants(tmp_path):
    module = selector()
    (tmp_path / "containers").mkdir()
    (tmp_path / "containers/base").write_text("FROM debian\nCOPY scripts/tool /tool\n")
    (tmp_path / "containers/child").write_text("FROM parent\n")
    rows = [
        {"name": "base", "dockerfile": "containers/base", "context": "."},
        {
            "name": "child",
            "dockerfile": "containers/child",
            "context": ".",
            "parent_dockerfile": "containers/base",
            "parent_context": ".",
        },
    ]
    assert module.select_images(["scripts/tool"], rows, tmp_path) == ["base", "child"]
    assert module.select_images(["docs/note.md"], rows, tmp_path) == []


def test_qualification_pulls_and_checks_the_catalog_dashboard(monkeypatch):
    from aptl.backends._raes_backend_implementation_catalog import (
        BACKEND_IMPLEMENTATION_PROFILES,
    )

    path = (
        Path(__file__).resolve().parents[1] / "tools/ci/build_qualification_images.py"
    )
    spec = importlib.util.spec_from_file_location("qualification_images", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(
        module.yaml,
        "safe_load",
        lambda _: {"jobs": {"trivy-image": {"strategy": {"matrix": {"include": []}}}}},
    )
    monkeypatch.setattr(
        module.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs))
    )
    module.main()
    image = next(
        item.image_ref
        for item in BACKEND_IMPLEMENTATION_PROFILES
        if item.profile_id == "wazuh-dashboard-4.12"
    )
    assert (["docker", "pull", image], {"check": True}) in calls
    assert (["docker", "image", "inspect", image], {"check": True}) in calls
