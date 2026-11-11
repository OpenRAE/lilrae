"""Concrete trial SDL fixtures for the #1670 trial path.

The fixture has one red and one blue agent, the service nodes that the
operator's MCP bindings name, and an optional threat-intelligence node.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy

import yaml
from raes import parse_sdl
from raes_contracts.contracts import ParticipantControlContextAssetModel
from raes_contracts.participant_control_context import control_context_asset_reference

ASSET_BYTES = {
    "red-preamble": b"You are the red participant.\n",
    "red-playbook-quiet": b"Move slowly and avoid noise.\n",
    "red-playbook-loud": b"Move fast.\n",
    "red-task": b"Reach the target host.\n",
    "blue-preamble": b"You are the blue participant.\n",
    "blue-playbook-watch": b"Watch the alerts first.\n",
    "blue-playbook-block": b"Block early.\n",
    "blue-task": b"Defend the target host.\n",
}


def _asset(name: str, role: str) -> dict[str, object]:
    data = ASSET_BYTES[name]
    return {
        "schema_version": "participant-control-context-asset/v1",
        "asset_id": name,
        "asset_version": "1",
        "kind": "directive",
        "content": {
            "artifact_id": name,
            "role": "documentation",
            "media_type": "text/plain",
            "uri": f"urn:sha256:{hashlib.sha256(data).hexdigest()}",
            "checksum": {"algorithm": "sha256", "value": hashlib.sha256(data).hexdigest()},
            "size_bytes": len(data),
            "created_at": "2026-11-06T00:00:00Z",
            "source": "test-fixture",
            "satisfies_refs": [],
            "sensitivity": "public",
        },
        "participant_addresses": [],
        "role_refs": [role],
        "publication_authority_ref": "urn:test:author",
        "retention_policy_ref": "urn:test:retention",
        "provenance_refs": ["urn:test:provenance"],
    }


def _service_host(port: int | None) -> dict[str, object]:
    services = [] if port is None else [{"name": "service", "port": port, "protocol": "tcp"}]
    return {"type": "compute", "os": "linux", "services": services}


def _host(model: str | None) -> dict[str, object]:
    components = [
        {"component_id": "nodejs", "name": "Node.js", "version": "22", "component_type": "platform"}
    ]
    if model is not None:
        components.append(
            {
                "component_id": "participant-harness",
                "name": "participant-harness",
                "component_type": "application",
                "model": model,
            }
        )
    return {
        "type": "compute",
        "os": "linux",
        "services": [{"name": "ssh", "port": 22, "protocol": "tcp"}],
        "runtime": {"software_components": components},
    }


def trial_document(
    *,
    red_model: str = "openrouter/vendor-a/model-a",
    blue_model: str = "openrouter/vendor-b/model-b",
    red_playbook: str = "red-playbook-quiet",
    blue_playbook: str = "blue-playbook-watch",
    intel_present: bool = True,
) -> dict[str, object]:
    """Return one concrete trial SDL document for the given experiment variables."""
    assets = {name: _asset(name, name.split("-", 1)[0]) for name in ASSET_BYTES}
    document: dict[str, object] = {
        "name": "trial-fixture",
        # Node names follow the operator's MCP service bindings.
        "nodes": {
            "kali": _host(red_model),
            "analyst": _host(blue_model),
            "target": _host(None),
            "wazuh-indexer": _service_host(9200),
            "wazuh-manager": _service_host(55000),
            "suricata": _service_host(None),
            "shuffle-frontend": _service_host(443),
        },
        "control_context_assets": assets,
        "agents": {},
    }
    if intel_present:
        document["nodes"]["misp"] = _service_host(443)
    for agent, role, node, playbook in (
        ("red-operator", "red", "kali", red_playbook),
        ("blue-operator", "blue", "analyst", blue_playbook),
    ):
        slots = {}
        for slot, asset in (
            ("preamble", f"{role}-preamble"),
            ("playbook", playbook),
            ("task", f"{role}-task"),
        ):
            pin = control_context_asset_reference(
                ParticipantControlContextAssetModel.model_validate(assets[asset])
            )
            slots[slot] = {
                "declaration_ref": asset,
                "asset_ref": pin.model_dump(mode="json"),
                "disposition": "selected",
            }
        document["agents"][agent] = {
            "role": role,
            "interactive_access": {f"{node}-ssh": {"target_ref": node, "channel": "ssh"}},
            "control_context": slots,
        }
    return document


def parse_trial(document: dict[str, object]):
    """Parse a fixture document through the public RAES parser."""
    return parse_sdl(yaml.safe_dump(deepcopy(document), sort_keys=False))


def read_fixture_asset(asset: ParticipantControlContextAssetModel) -> bytes:
    """Return the fixture bytes that the asset descriptor pins."""
    return ASSET_BYTES[asset.content.artifact_id]


def mcp_document(command: str) -> dict[str, object]:
    """Return a run MCP configuration with one entry for every catalog server."""
    from aptl.core.mcp_policy import SERVER_IDS

    return {
        "mcpServers": {
            name: {"command": command, "args": ["-c", "pass"], "env": {"SERVER": name}}
            for name in SERVER_IDS
        }
    }


def catalog_inventory(name, command, args, environment):
    """Report each server's catalog tools, as a live tools/list would."""
    from aptl.core.mcp_policy import profile_for

    for role in ("red", "blue"):
        for server in profile_for(role).servers:
            if server.server_id == name:
                return server.tool_names
    raise AssertionError(name)
