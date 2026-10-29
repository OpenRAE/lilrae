"""Which scenario APTL realizes, and where its bytes come from, is configuration.

APTL currently hardcodes a scenario path inside its own tree. A backend is handed
a scenario; it does not own one. Selecting it is an operator decision made before
`aptl lab start`, not something the backend decides or switches at runtime.

The strict-config rules apply: unknown keys are errors, and a root that escapes
the project is refused rather than silently accepted.
"""

from __future__ import annotations

import json

import pytest

from aptl.core.config import AptlConfig, load_config


def _write(tmp_path, payload):
    path = tmp_path / "aptl.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_default_requires_an_explicit_scenario():
    """Initialization does not choose a scenario for the operator."""

    config = AptlConfig()

    assert config.scenario.identity is None
    assert config.scenario.source == "env-pack"
    assert config.scenario.root is None


def test_an_operator_can_select_a_scenario_and_its_root(tmp_path):
    config = load_config(
        _write(
            tmp_path,
            {"scenario": {"identity": "bounded-participant-agency-techvault",
                          "root": "environments/bounded-participant"}},
        )
    )

    assert config.scenario.identity == "bounded-participant-agency-techvault"
    assert config.scenario.root == "environments/bounded-participant"


def test_unknown_scenario_keys_are_rejected(tmp_path):
    """ADR-025: aptl.json is strict at every level, so typos fail loudly."""

    config_path = _write(tmp_path, {"scenario": {"identiy": "typo"}})
    with pytest.raises(ValueError):
        load_config(config_path)


def test_an_empty_identity_is_rejected(tmp_path):
    config_path = _write(tmp_path, {"scenario": {"identity": "  "}})
    with pytest.raises(ValueError):
        load_config(config_path)


@pytest.mark.parametrize("identity", ["../elsewhere", "/etc", "a/b", ".", ".."])
def test_identity_cannot_act_as_a_path(tmp_path, identity):
    with pytest.raises(ValueError):  # NOSONAR
        load_config(_write(tmp_path, {"scenario": {"identity": identity}}))


@pytest.mark.parametrize(
    "hostile", ["../elsewhere", "/etc", "packs/../../etc", "a\x00b"]
)
def test_a_root_that_escapes_the_project_is_refused(tmp_path, hostile):
    """A configured root is operator input and is treated as untrusted."""

    config_path = _write(tmp_path, {"scenario": {"root": hostile}})
    with pytest.raises(ValueError):
        load_config(config_path)


def test_the_configured_scenario_is_what_the_start_path_resolves(tmp_path):
    """Configuration that nothing reads is not configuration.

    The bundle seam was once wired this way — a type with tests and no caller —
    so the wiring itself is asserted here rather than the model in isolation.
    """

    from aptl.backends.raes import _resolve_scenario_path

    config = AptlConfig.model_validate(
        {"scenario": {"identity": "bounded-participant-agency-techvault"}}
    )

    resolved = _resolve_scenario_path(tmp_path, None, config)

    assert resolved.name == "bounded-participant-agency-techvault.sdl.yaml"


def test_an_explicit_scenario_path_still_wins(tmp_path):
    """Selecting one explicitly must override the configured default."""

    from pathlib import Path

    from aptl.backends.raes import _resolve_scenario_path

    config = AptlConfig()
    explicit = Path("scenarios") / "paper-agent-loop.sdl.yaml"

    assert _resolve_scenario_path(tmp_path, explicit, config).name == (
        "paper-agent-loop.sdl.yaml"
    )


def test_a_configured_root_anchors_the_scenario(tmp_path):
    """The scenario's bytes come from the configured root, not the checkout."""

    from aptl.backends.raes import _resolve_scenario_path

    config = AptlConfig.model_validate(
        {"scenario": {"identity": "demo", "root": "environments/demo"}}
    )

    resolved = _resolve_scenario_path(tmp_path, None, config)

    assert (tmp_path / "environments" / "demo") in resolved.parents


def test_no_implicit_project_tree_default_without_config(tmp_path):
    from aptl.backends.raes import _resolve_scenario_path

    with pytest.raises(ValueError, match="explicit scenario path or configuration"):
        _resolve_scenario_path(tmp_path, None, None)


def test_configured_release_directory_is_loaded(tmp_path):
    config = load_config(_write(tmp_path, {"scenario": {
        "identity": "third-party", "pack_directory": "releases/third-party",
    }}))
    assert config.scenario.pack_directory == "releases/third-party"
    assert AptlConfig().scenario.pack_directory is None


@pytest.mark.parametrize("directory", [
    "", " ", "/etc", "../pack", "packs/../pack", "packs//pack",
    "packs/./pack", "packs/pack/", "a\x00b", "~", "~/pack", "$PACK",
    ".aptl/staged-packs/pack", ".aptl", "packs\\pack",
])
def test_unsafe_release_locator_is_rejected(tmp_path, directory):
    config_path = _write(tmp_path, {"scenario": {"pack_directory": directory}})
    with pytest.raises(ValueError):
        load_config(config_path)


@pytest.mark.parametrize("selection", [
    {"source": "project-tree"}, {"root": "scenarios"},
])
def test_release_directory_cannot_be_combined_with_development_root(selection):
    with pytest.raises(ValueError):
        AptlConfig(scenario={**selection, "pack_directory": "releases/pack"})
