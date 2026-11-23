"""Backend observers and operator accesses that deployment must realize."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentCaptureApparatus(object):
    """One scope-admitted backend observer that deployment must realize."""

    apparatus_id: str
    service_name: str
    container_name: str
    target_refs: tuple[str, ...]
    governing_scopes: tuple[str, ...]
    environment_visible: bool
    observer_effects: tuple[str, ...]

    def details(self) -> dict[str, object]:
        return {
            "apparatus_id": self.apparatus_id,
            "service_name": self.service_name,
            "container_name": self.container_name,
            "target_refs": list(self.target_refs),
            "governing_scopes": list(self.governing_scopes),
            "environment_visible": self.environment_visible,
            "observer_effects": list(self.observer_effects),
        }


@dataclass(frozen=True)
class DeploymentOperatorAccess(object):
    """One declared operator interactive access the backend must make reachable.

    A scenario declares that a participant reaches a node interactively
    (``agents.<agent>.interactive_access.<id>``). That is an in-world fact; how
    an operator on the host actually reaches an internal node is the backend's
    choice under open realization, and the backend must make it true or refuse
    admission (issue #1006).
    """

    access_id: str
    agent: str
    target_node: str
    channel: str

    def details(self) -> dict[str, object]:
        return {
            "access_id": self.access_id,
            "agent": self.agent,
            "target_node": self.target_node,
            "channel": self.channel,
        }
