"""Deployment selection, operator grants and workspace identity configuration."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aptl.core._credential_sources import EnvironmentGrant
from aptl.core._range_policy_config import RangeEgressAllowance

_COMPOSE_PROJECT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def validate_compose_project_name(value: str) -> str:
    """Return a bounded Compose project token or raise ``ValueError``."""

    if not _COMPOSE_PROJECT_NAME_PATTERN.fullmatch(value):
        raise ValueError(
            "deployment.project_name must be 1-63 lowercase letters, "
            "digits, hyphens, or underscores and start with a letter or digit"
        )
    return value


class DeploymentConfig(BaseModel):
    """Configuration for deployment backend selection.

    Controls which deployment backend is used for lab lifecycle
    operations (start, stop, status, kill).  Defaults to local
    Docker Compose.
    """

    model_config = ConfigDict(extra="forbid")

    # "docker-compose" or "ssh-compose"
    range_egress_allowances: list[RangeEgressAllowance] = Field(default_factory=list)

    provider: str = "docker-compose"
    project_name: str = "aptl"

    # SSH-specific fields (only used when provider == "ssh-compose")
    ssh_host: str | None = None
    ssh_user: str | None = None
    ssh_key: str | None = None
    ssh_port: int = 22
    remote_dir: str | None = None

    # Operator grants: the only way an operator-supplied value reaches a
    # declared scenario variable (issue #965). Locators, never values.
    environment_grants: list[EnvironmentGrant] = Field(default_factory=list)
    # The lab host is a VM built only to run this lab, such as a BigRAE worker.
    # Nodes may then hold host-root-equivalent authority (the Docker socket).
    dedicated_vm: bool = False

    @field_validator("environment_grants")
    @classmethod
    def validate_unique_grants(
        cls, grants: list[EnvironmentGrant]
    ) -> list[EnvironmentGrant]:
        """Refuse two grants for the same pack, consumer and variable."""

        keys = [grant.key for grant in grants]
        if len(keys) != len(set(keys)):
            raise ValueError("environment grants must be unique per variable")
        return grants

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"docker-compose", "ssh-compose"}
        if v not in allowed:
            raise ValueError(
                f"Unknown deployment provider '{v}'. "
                f"Supported: {', '.join(sorted(allowed))}"
            )
        return v

    @field_validator("project_name")
    @classmethod
    def validate_project_name(cls, value: str) -> str:
        """Validate the identity used by Compose and destructive label queries."""

        return validate_compose_project_name(value)
