"""Resolve which scenario a RAES run realizes, and where its bytes come from.

Split out of :mod:`aptl.backends.raes` so that module keeps the runtime-target
composition and start/apply flow while this one carries the selection seam:
explicit development path or configured acquired pack, and the staged-env-pack
vs project-tree bundle choice. Both names are re-exported from
``aptl.backends.raes`` unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

from aptl.core.config import AptlConfig
from aptl.core.scenario_bundle import (
    EnvPackError,
    ScenarioBundle,
    env_pack_bundle,
    project_tree_bundle,
)
from aptl.utils.pathsafe import PathContainmentError, open_private_dir_contained_nofollow

_PACK_STAGING_RELPATH = Path(".aptl/staged-packs")


def _resolve_scenario_path(
    project_dir: Path,
    scenario_path: Path | None,
    config: AptlConfig | None = None,
) -> Path:
    """Resolve which scenario to realize, and where its bytes come from.

    An explicit project-contained path is a development override. Otherwise a
    project-tree source must be configured explicitly; there is no implicit
    in-tree scenario fallback. A backend is handed a scenario rather than
    owning one, so the operator chooses it before ``lilrae lab start``.
    """

    if scenario_path is not None:
        return (
            scenario_path
            if scenario_path.is_absolute()
            else project_dir / scenario_path
        )
    if config is not None:
        selection = config.scenario
        if selection.identity is None:
            raise ValueError("scenario selection requires an explicit scenario identity or path")
        relative = Path(f"{selection.identity}.sdl.yaml")
        base = Path(selection.root) if selection.root else Path("scenarios")
        return project_dir / base / relative
    raise ValueError(
        "scenario selection requires an explicit scenario path or configuration"
    )


def resolve_scenario_bundle(
    project_dir: Path,
    scenario_path: Path | None,
    config: AptlConfig | None = None,
    *,
    staging_root: Path | None = None,
) -> ScenarioBundle:
    """Resolve the scenario bundle: a staged env-pack when selected, else in-tree.

    An explicit ``scenario_path`` always wins (an operator overriding with a
    local file), so the pack is used only for the default/configured selection
    when ``config.scenario.source`` is ``env-pack``. Staging + validation happen
    inside :func:`env_pack_bundle`; the pack is never read in place.
    """

    # The operator selects this trusted anchor; only appended source/staging
    # components are untrusted locators and must retain no-follow traversal.
    project_dir = project_dir.resolve()
    if scenario_path is None and config is not None and config.scenario.identity is None:
        raise ValueError("scenario selection requires an explicit scenario identity or path")
    if (
        scenario_path is None
        and config is not None
        and config.scenario.source == "env-pack"
    ):
        directory = config.scenario.pack_directory
        source = project_dir / directory if directory is not None else None
        if staging_root is None:
            try:
                fd = open_private_dir_contained_nofollow(
                    project_dir, _PACK_STAGING_RELPATH
                )
                os.close(fd)
            except (OSError, PathContainmentError) as exc:
                raise EnvPackError("env-pack staging unavailable") from exc
        return env_pack_bundle(
            staging_root
            if staging_root is not None
            else project_dir / _PACK_STAGING_RELPATH,
            config.scenario.identity,
            source_pack=source,
        )
    return project_tree_bundle(
        project_dir, _resolve_scenario_path(project_dir, scenario_path, config)
    )
