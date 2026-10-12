"""Emergency stop of the lab containers, the optional step of the kill switch.

``aptl.core.kill`` runs it when ``aptl kill --containers`` asks for it and
re-exports ``kill_lab_containers``.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from aptl.core.config import find_config, load_config
from aptl.core.lifecycle_guard import (
    LifecycleLockUnavailableError,
    lifecycle_mutation_lock,
)
from aptl.core.lifecycle_policy import LifecycleBusyError

if TYPE_CHECKING:
    from aptl.core.deployment.backend import DeploymentBackend


def kill_lab_containers(
    project_dir: Optional[Path] = None,
    backend: Optional["DeploymentBackend"] = None,
) -> tuple[bool, str]:
    """Emergency-stop all lab containers.

    Uses the configured deployment backend's kill method for immediate
    shutdown. A missing config uses the bounded default Compose backend;
    an invalid present config fails closed rather than guessing identity.

    Args:
        project_dir: Working directory for Docker Compose.
        backend: Optional pre-created deployment backend.

    Returns:
        Tuple of (success, error_message).
    """
    resolved_dir = Path(project_dir) if project_dir is not None else Path(".")
    try:
        with lifecycle_mutation_lock(resolved_dir) as project_root:
            result = _kill_lab_containers_owned(project_root, backend)
    except LifecycleBusyError:
        result = (
            False,
            "[lifecycle-owner-busy] Another lab lifecycle operation is active; "
            "wait for it to finish before retrying container kill.",
        )
    except LifecycleLockUnavailableError:
        result = (
            False,
            "[lifecycle-lock-unavailable] Container kill blocked because safe "
            "project lifecycle ownership could not be established.",
        )
    return result


def _kill_lab_containers_owned(
    project_dir: Path,
    backend: Optional["DeploymentBackend"],
) -> tuple[bool, str]:
    """Kill project containers while the caller owns the lifecycle lock."""

    resolved_backend, error = _kill_backend(project_dir, backend)
    if error:
        return False, error
    assert resolved_backend is not None
    try:
        from aptl.core.operator_group_state import load_admitted_operator_groups

        profiles = list(load_admitted_operator_groups(project_dir))
    except (OSError, ValueError):
        return False, "invalid operator-group recovery state"
    return resolved_backend.kill(profiles)


def _kill_backend(
    project_dir: Path,
    backend: Optional["DeploymentBackend"],
) -> tuple[Optional["DeploymentBackend"], str]:
    """Resolve the configured backend without guessing an invalid identity."""

    resolved_backend = backend
    error = ""
    if resolved_backend is None:
        from aptl.core.deployment import get_backend
        from aptl.core.deployment.docker_compose import DockerComposeBackend

        config_path = find_config(project_dir)
        if config_path is None:
            resolved_backend = DockerComposeBackend(project_dir=project_dir)
        else:
            try:
                config = load_config(config_path)
            except (FileNotFoundError, ValueError):
                error = (
                    "[lifecycle-invalid-configuration] Container kill blocked: "
                    "invalid configuration; refusing to guess the deployment "
                    "project identity."
                )
            else:
                resolved_backend = get_backend(config, project_dir)
    return resolved_backend, error
