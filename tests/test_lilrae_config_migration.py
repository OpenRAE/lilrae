"""Explicit pack selection and recoverable conversion of historical topology."""

import json

import pytest

from aptl.core.config import AptlConfig, ContainerSettings


def test_initialization_has_no_implicit_scenario():
    assert AptlConfig().scenario.identity is None
    assert ContainerSettings().model_dump() == {"profiles": None}


def test_removed_topology_keys_are_not_runtime_configuration():
    with pytest.raises(ValueError):
        ContainerSettings(wazuh=True)


def test_unselected_source_is_rejected_before_pack_acquisition(tmp_path, monkeypatch):
    from aptl.backends import _raes_scenario_resolution as resolver

    def unexpected(*args, **kwargs):
        pytest.fail("an unselected workspace attempted pack acquisition")
    monkeypatch.setattr(resolver, "env_pack_bundle", unexpected)
    config = AptlConfig()
    with pytest.raises(ValueError, match="explicit scenario"):
        resolver.resolve_scenario_bundle(tmp_path, None, config)
    assert not (tmp_path / ".aptl").exists()


def test_migration_keeps_disabled_groups_and_original_bytes(tmp_path):
    from aptl.core.lilrae_config_migration import migrate_config

    path = tmp_path / "aptl.json"
    original = b'{"lab":{"name":"owned"},"containers":{"soc":false},"scenario":{"identity":"example"}}\n'
    path.write_bytes(original)
    assert migrate_config(path)
    result = json.loads(path.read_text())
    assert result["scenario"]["identity"] == "example"
    assert result["lab"]["name"] == "owned"
    assert set(result["containers"]["profiles"]) == {"wazuh", "victim", "kali", "enterprise", "fileshare", "dns"}
    assert (tmp_path / "aptl.json.bak").read_bytes() == original
    assert not migrate_config(path)
    assert (tmp_path / "aptl.json.bak").read_bytes() == original


def test_migration_needs_operator_identity_when_old_default_was_used(tmp_path):
    from aptl.core.lilrae_config_migration import migrate_config

    path = tmp_path / "aptl.json"
    original = b'{"containers":{"victim":true}}'
    path.write_bytes(original)
    with pytest.raises(ValueError, match="explicit scenario"):
        migrate_config(path)
    assert path.read_bytes() == original
    assert not (tmp_path / "aptl.json.bak").exists()
    assert migrate_config(path, scenario_identity="example")
    assert AptlConfig.model_validate_json(path.read_bytes()).scenario.identity == "example"


@pytest.mark.parametrize("topology", [{}, {"containers": {}}])
def test_migration_materializes_omitted_historical_profile_defaults(topology):
    from aptl.core.lilrae_config_migration import migrated_config

    converted = migrated_config({**topology, "scenario": {"identity": "example"}})
    assert set(converted["containers"]["profiles"]) == {
        "wazuh", "victim", "kali", "enterprise", "soc", "fileshare", "dns",
    }


@pytest.mark.parametrize("settings", [{"unknown": True}, {"soc": []}, {"soc": False, "profiles": []}, {"mail": True}, {"reverse": True}])
def test_ambiguous_or_retired_selection_is_not_silently_discarded(tmp_path, settings):
    from aptl.core.lilrae_config_migration import migrate_config

    path = tmp_path / "aptl.json"
    original = json.dumps({"containers": settings, "scenario": {"identity": "example"}}).encode()
    path.write_bytes(original)
    with pytest.raises(ValueError):
        migrate_config(path)
    assert path.read_bytes() == original
    assert not (tmp_path / "aptl.json.bak").exists()


def test_migration_refuses_symlinked_source(tmp_path):
    from aptl.core.lilrae_config_migration import migrate_config
    from aptl.utils.pathsafe import PathContainmentError

    original = tmp_path / "other.json"
    original.write_text('{"containers": {"soc": true}}')
    path = tmp_path / "aptl.json"
    path.symlink_to(original)
    with pytest.raises(PathContainmentError):
        migrate_config(path, scenario_identity="example")
    assert path.is_symlink()
    assert not (tmp_path / "aptl.json.bak").exists()


def test_migration_holds_lifecycle_lock_through_replacement(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from aptl.core import lilrae_config_migration as migration
    from aptl.core.lifecycle_policy import LifecycleBusyError

    path = tmp_path / "aptl.json"
    original = b'{"containers":{"soc":false}}'
    path.write_bytes(original)
    replace = migration.replace_private_nofollow
    checking = False
    def checked_replace(*args, **kwargs):
        nonlocal checking
        if not checking:
            checking = True
            with ThreadPoolExecutor(max_workers=1) as workers:
                competing = workers.submit(migration.migrate_config, path, scenario_identity="other")
                with pytest.raises(LifecycleBusyError):
                    competing.result(timeout=10)
        return replace(*args, **kwargs)
    monkeypatch.setattr(migration, "replace_private_nofollow", checked_replace)
    assert migration.migrate_config(path, scenario_identity="selected")
    assert json.loads(path.read_bytes())["scenario"]["identity"] == "selected"
    assert (tmp_path / "aptl.json.bak").read_bytes() == original


def test_migration_refuses_a_lock_held_by_another_lifecycle_operation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from aptl.core.lilrae_config_migration import migrate_config
    from aptl.core.lifecycle_guard import lifecycle_mutation_lock
    from aptl.core.lifecycle_policy import LifecycleBusyError

    path = tmp_path / "aptl.json"
    original = b'{"containers":{"soc":false}}'
    path.write_bytes(original)
    with lifecycle_mutation_lock(tmp_path), ThreadPoolExecutor(max_workers=1) as workers:
        competing = workers.submit(migrate_config, path, scenario_identity="selected")
        with pytest.raises(LifecycleBusyError):
            competing.result(timeout=10)
    assert path.read_bytes() == original
    assert not (tmp_path / "aptl.json.bak").exists()
