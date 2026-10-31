"""Normalization helpers for observed Docker network metadata."""

from __future__ import annotations

from typing import Any


def network_bridge(
    payload: dict[str, Any], options: dict[str, str], network_id: str
) -> str:
    """Return the explicit or deterministic default bridge interface name."""

    bridge = options.get("com.docker.network.bridge.name", "")
    if not bridge and payload.get("Driver") == "bridge" and network_id:
        bridge = f"br-{network_id[:12]}"
    return bridge
