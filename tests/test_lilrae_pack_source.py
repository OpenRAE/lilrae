"""Configured release bytes use ordinary catalog and admission boundaries."""

from __future__ import annotations

import json
import shutil

import pytest

from aptl.backends._raes_scenario_resolution import resolve_scenario_bundle
from aptl.core.config import load_config
from aptl.core.scenario_bundle import EnvPackError, ScenarioSourceKind
from aptl.core.scenario_catalog import load_scenario_catalog, resolve_acquired_scenario
from tests.fixture_pack import FIXTURE_PACK_IDENTITY, FIXTURE_PACK_SOURCE


@pytest.fixture
def release(tmp_path):
    source = tmp_path / "releases" / FIXTURE_PACK_IDENTITY
    shutil.copytree(FIXTURE_PACK_SOURCE, source)
    (tmp_path / "aptl.json").write_text(
        json.dumps(
            {
                "scenario": {
                    "identity": FIXTURE_PACK_IDENTITY,
                    "pack_directory": f"releases/{FIXTURE_PACK_IDENTITY}",
                }
            }
        )
    )
    return source


def test_configured_source_flows_through_catalog_and_raes_parser(
    tmp_path,
    release,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path.parent)
    with load_scenario_catalog(tmp_path) as catalog:
        resolved = resolve_acquired_scenario(
            tmp_path,
            FIXTURE_PACK_IDENTITY,
            catalog=catalog,
        )
        assert resolved.scenario.name == FIXTURE_PACK_IDENTITY
        assert resolved.bundle.source_kind is ScenarioSourceKind.ENV_PACK
        assert resolved.bundle.pack_identity.pack_id == FIXTURE_PACK_IDENTITY
        assert resolved.bundle.root != release
        assert (
            resolved.bundle.read_asset("assets/content/notice.txt")
            == (release / "assets/content/notice.txt").read_bytes()
        )
        staged = resolved.bundle.root
    assert not staged.exists()
    assert release.is_dir()


@pytest.mark.parametrize("damage", ["missing", "tampered", "symlink"])
def test_configured_source_fails_closed(tmp_path, release, damage):
    if damage == "missing":
        shutil.rmtree(release)
    elif damage == "tampered":
        (release / "assets/content/notice.txt").write_text("tampered")
    else:
        saved = release.with_name("saved")
        release.rename(saved)
        release.symlink_to(saved, target_is_directory=True)
    config = load_config(tmp_path / "aptl.json")
    with pytest.raises(EnvPackError) as error:
        resolve_scenario_bundle(tmp_path, None, config)
    assert str(tmp_path) not in str(error.value)
    assert not list((tmp_path / ".aptl").rglob("pack.yaml"))


def test_explicit_development_override_still_wins(tmp_path, release):
    from pathlib import Path

    bundle = resolve_scenario_bundle(
        tmp_path,
        Path("custom.sdl.yaml"),
        load_config(tmp_path / "aptl.json"),
    )
    assert bundle.source_kind is ScenarioSourceKind.PROJECT_TREE


@pytest.mark.parametrize("relationship", ["equal", "source-parent", "staging-parent"])
def test_source_and_staging_must_not_overlap(tmp_path, relationship):
    from aptl.core.scenario_bundle import env_pack_bundle

    source = tmp_path / "pack"
    source.mkdir()
    staging = {
        "equal": source,
        "source-parent": source / "staged",
        "staging-parent": tmp_path,
    }[relationship]
    with pytest.raises(EnvPackError, match="overlap"):
        env_pack_bundle(staging, "demo", source_pack=source)
    assert not list(tmp_path.rglob("demo.*"))


@pytest.mark.parametrize("component", [".aptl", ".aptl/staged-packs"])
def test_staging_symlinks_cannot_redirect_writes(tmp_path, release, component):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / component
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    config = load_config(tmp_path / "aptl.json")
    with pytest.raises(EnvPackError):
        resolve_scenario_bundle(tmp_path, None, config)
    assert list(outside.iterdir()) == []


def test_staging_setup_failure_is_a_bounded_acquisition_error(tmp_path, release):
    (tmp_path / ".aptl").write_text("not a directory")
    config = load_config(tmp_path / "aptl.json")
    with pytest.raises(EnvPackError) as error:
        resolve_scenario_bundle(tmp_path, None, config)
    assert str(tmp_path) not in str(error.value)


def test_staging_swap_cannot_redirect_copy_or_cleanup(tmp_path, release, monkeypatch):
    from aptl.core import _pack_staging

    original = _pack_staging.copy_pack
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = None

    def swap_and_copy(source, staged):
        nonlocal sentinel
        (tmp_path / ".aptl").rename(tmp_path / "owned-state")
        (tmp_path / ".aptl").symlink_to(outside, target_is_directory=True)
        sentinel = outside / "staged-packs" / staged.parent.name / "keep"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("untouched")
        original(source, staged)

    monkeypatch.setattr(_pack_staging, "copy_pack", swap_and_copy)
    config = load_config(tmp_path / "aptl.json")
    with pytest.raises(EnvPackError):
        resolve_scenario_bundle(tmp_path, None, config)
    assert sentinel.read_text() == "untouched"
    assert not list((tmp_path / "owned-state").rglob("pack.yaml"))


def test_catalog_cleanup_never_follows_a_replaced_parent(tmp_path, release):
    catalog = load_scenario_catalog(tmp_path)
    original_state = tmp_path / ".aptl"
    original_state.rename(tmp_path / "owned-state")
    outside = tmp_path / "outside"
    sentinel = outside / "staged-packs" / catalog.bundle.root.parent.name / "keep"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("untouched")
    original_state.symlink_to(outside, target_is_directory=True)
    catalog.close()
    assert sentinel.read_text() == "untouched"


def test_configured_pack_uses_normal_raes_planning(tmp_path, release):
    from unittest.mock import MagicMock
    from aptl.backends.raes import (
        RuntimeManager,
        create_aptl_runtime_target,
        parse_sdl_file,
    )
    from aptl.backends.raes_realization import interpret_provisioning_plan

    config = load_config(tmp_path / "aptl.json")
    bundle = resolve_scenario_bundle(tmp_path, None, config)
    backend = MagicMock()
    target = create_aptl_runtime_target(
        project_dir=tmp_path,
        config=config,
        backend=backend,
        bundle=bundle,
    )
    plan = RuntimeManager(target).plan(parse_sdl_file(bundle.sdl_path))
    assert [diagnostic.code for diagnostic in plan.diagnostics] == []
    realization = interpret_provisioning_plan(
        plan=plan.provisioning,
        config=config,
        bundle=bundle,
        component_root=tmp_path,
    )
    assert realization.nodes
    assert not realization.diagnostics
    backend.realize.assert_not_called()
    bundle.close()


def test_configured_source_does_not_bypass_required_adapter_admission(
    tmp_path, release
):
    from unittest.mock import MagicMock
    from aptl.backends.raes import admit_raes_scenario
    from aptl.backends.scenario_capture_discovery import ScenarioCaptureProviderError

    config = load_config(tmp_path / "aptl.json")
    backend = MagicMock()
    with pytest.raises(ScenarioCaptureProviderError, match="provider-missing"):
        admit_raes_scenario(tmp_path, config, backend)


def test_release_locator_is_absent_from_run_identity(tmp_path, release):
    from aptl.core.provenance.providers.config_identity import safe_config_projection

    config = load_config(tmp_path / "aptl.json")
    assert "releases/" not in json.dumps(safe_config_projection(config))


def test_invalid_config_diagnostic_does_not_echo_source_locator():
    from aptl.core.config import AptlConfig

    rejected = "../private-release-location"
    with pytest.raises(ValueError) as error:
        AptlConfig(scenario={"pack_directory": rejected})
    assert rejected not in str(error.value)


def test_missing_configured_release_never_uses_installed_identity(tmp_path):
    from aptl.core.config import AptlConfig

    config = AptlConfig(
        scenario={
            "identity": "techvault",
            "pack_directory": "releases/missing",
        }
    )
    with pytest.raises(EnvPackError, match="source not found"):
        resolve_scenario_bundle(tmp_path, None, config)


def test_runtime_state_ancestors_cannot_be_writable_by_other_users(tmp_path, release):
    import stat

    state = tmp_path / ".aptl"
    state.mkdir(mode=0o777)
    state.chmod(0o777)
    bundle = resolve_scenario_bundle(
        tmp_path, None, load_config(tmp_path / "aptl.json")
    )
    assert not stat.S_IMODE(state.stat().st_mode) & 0o022
    assert stat.S_IMODE(bundle.root.parent.stat().st_mode) == 0o700
    bundle.close()


def test_cli_catalog_uses_configured_release(tmp_path, release):
    from typer.testing import CliRunner
    from aptl.cli.main import app

    result = CliRunner().invoke(
        app, ["lab", "scenarios", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert FIXTURE_PACK_IDENTITY in result.output
    assert "releases/" not in result.output


@pytest.mark.parametrize("configured", [True, False])
def test_cli_accepts_a_parent_relative_project(
    tmp_path, release, monkeypatch, configured
):
    from typer.testing import CliRunner
    from aptl.cli.main import app

    if not configured:
        (tmp_path / "aptl.json").write_text("{}")
    child = tmp_path / "working-directory"
    child.mkdir()
    monkeypatch.chdir(child)
    result = CliRunner().invoke(app, ["lab", "scenarios", "--project-dir", ".."])
    assert result.exit_code == 0, result.output
    assert (FIXTURE_PACK_IDENTITY if configured else "techvault") in result.output


@pytest.mark.parametrize("linked_staging", [False, True])
def test_system_temp_alias_preserves_descendant_containment(
    tmp_path,
    monkeypatch,
    linked_staging,
):
    from aptl.core.scenario_bundle import env_pack_bundle

    temporary_root = tmp_path / "system-temp"
    temporary_root.mkdir()
    alias = tmp_path / "temp-alias"
    alias.symlink_to(temporary_root, target_is_directory=True)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(alias))
    if linked_staging:
        outside = tmp_path / "outside"
        outside.mkdir()
        (temporary_root / "staging").symlink_to(outside, target_is_directory=True)
        with pytest.raises(EnvPackError):
            env_pack_bundle(
                alias / "staging",
                FIXTURE_PACK_IDENTITY,
                source_pack=FIXTURE_PACK_SOURCE,
            )
        assert list(outside.iterdir()) == []
    else:
        bundle = env_pack_bundle(
            alias / "staging",
            FIXTURE_PACK_IDENTITY,
            source_pack=FIXTURE_PACK_SOURCE,
        )
        assert bundle.root.is_relative_to(temporary_root)
        bundle.close()
        assert not list(temporary_root.rglob("pack.yaml"))
