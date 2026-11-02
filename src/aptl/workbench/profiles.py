"""Closed, secret-free participant workbench profile definitions."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Collection, Mapping
from pathlib import Path

from aptl.core.mcp_policy import (
    ProfileId,
    ServerProfile,
    WorkbenchConfigurationError,
    WorkbenchProfile,
    profile_for,
)

from aptl.utils.pathsafe import PathContainmentError, create_exclusive_nofollow

_TRACE_ID_RE = re.compile(r"^[a-f0-9]{32}$")

def _validate_run_id(run_id: str) -> str:
    """Return a canonical active trace identifier or reject the input."""
    if not _TRACE_ID_RE.fullmatch(run_id):
        raise WorkbenchConfigurationError(
            "run_id must be the active 32-character trace id"
        )
    return run_id


def _validate_aliases(
    profile: WorkbenchProfile, credential_aliases: Collection[str]
) -> None:
    """Require every alias selected by the closed workbench profile."""
    available = set(credential_aliases)
    missing = [alias for alias in profile.credential_aliases if alias not in available]
    if missing:
        raise WorkbenchConfigurationError(
            "missing required credential alias: " + ", ".join(missing)
        )


def _validate_artifacts(profile: WorkbenchProfile, payload_root: Path) -> None:
    """Require each released MCP artifact to remain inside the payload root."""
    root = payload_root.resolve()
    for server in profile.servers:
        artifact = (root / server.artifact_ref).resolve()
        if not artifact.is_relative_to(root) or not artifact.is_file():
            raise WorkbenchConfigurationError(
                f"missing released MCP artifact for {server.server_id}"
            )


def verify_profile_tool_inventory(
    profile: ProfileId | str | WorkbenchProfile, inventory: Mapping[str, Collection[str]]
) -> None:
    """Reject a launched profile unless every server reports its exact tools/list set."""
    selected = profile if isinstance(profile, WorkbenchProfile) else profile_for(profile)
    expected = {
        server.server_id: frozenset(server.tool_names) for server in selected.servers
    }
    actual = {
        server_id: frozenset(tool_names) for server_id, tool_names in inventory.items()
    }
    if actual != expected:
        raise WorkbenchConfigurationError(
            "MCP tool inventory does not match the selected profile"
        )


def render_profile_config(
    *,
    profile: ProfileId | str | WorkbenchProfile,
    payload_root: Path,
    output_dir: Path,
    state_dir: Path,
    node_executable: Path,
    run_id: str,
    credential_aliases: Collection[str],
    runtime_environment: Mapping[str, Mapping[str, str]] | None = None,
) -> Path:
    """Render one private, standard Claude Code MCP config for an active run.

    Secret values stay with the management-owned credential broker. The
    client expands only the selected aliases into the stdio server processes.
    """
    selected = profile if isinstance(profile, WorkbenchProfile) else profile_for(profile)
    active_run_id = _validate_run_id(run_id)
    _validate_aliases(selected, credential_aliases)
    _validate_artifacts(selected, payload_root)
    node = node_executable.resolve(strict=True)
    if (
        not node_executable.is_absolute()
        or not node.is_file()
        or not os.access(node, os.X_OK)
    ):
        raise WorkbenchConfigurationError("node executable is not admissible")
    canonical_state_dir = state_dir.resolve()
    payload = payload_root.resolve()

    document = {
        "mcpServers": {
            server.server_id: {
                "command": str(node),
                "args": [str((payload / server.artifact_ref).resolve())],
                "env": {
                    **((runtime_environment or {}).get(server.server_id, {})),
                    "APTL_MCP_DISABLE_DOTENV": "1",
                    "APTL_STATE_DIR": str(canonical_state_dir),
                    **{
                        alias: f"${{{alias}}}"
                        for alias in server.credential_aliases
                    },
                },
            }
            for server in selected.servers
        },
    }
    output_parent = output_dir.parent
    relative_path = (
        f"{output_dir.name}/{selected.profile_id.value}-{active_run_id}.json"
    )
    try:
        create_exclusive_nofollow(
            output_parent,
            relative_path,
            (
                json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode(),
        )
    except (FileExistsError, PathContainmentError) as exc:
        raise WorkbenchConfigurationError(
            "unable to create private profile config"
        ) from exc
    return output_parent / relative_path
