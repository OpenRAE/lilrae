"""TechVault capture assets live in its pack and adapter, not in APTL (#1700)."""

import json
from importlib import resources
from pathlib import Path

from tests.test_scenario_pack_ownership_contract import (
    _ASSET_OWNERSHIP_NOTE,
    _asset_ownership_rows,
)


def test_capture_asset_placement_is_current_and_adapter_explicit() -> None:
    note = _ASSET_OWNERSHIP_NOTE.read_text(encoding="utf-8")
    rows = _asset_ownership_rows(note)

    methodology = next(
        value
        for source, value in rows.items()
        if "asset-inventory-methodology.md" in source
    )
    pack_source, pack_adapter = next(
        (source, value)
        for source, value in rows.items()
        if "aptl-capture-client" in source
    )
    runtime_source, runtime = next(
        (source, value) for source, value in rows.items() if "kali-capture/**" in source
    )

    assert "RAES-owned" in methodology
    assert "OpenRAE/env-packs/packs/techvault/assets/content" in pack_source
    assert "explicit APTL backend adapters" in pack_adapter
    assert "Capture consumer contract" in pack_adapter
    assert "mcp/aptl-mcp-common/src/captures.ts" in runtime_source
    assert "APTL-owned runtime apparatus" in runtime
    assert "https://github.com/OpenRAE/env-packs/tree/main/packs/techvault" in note
    assert "there is no additional APTL asset to move" in " ".join(note.split())


def test_pinned_techvault_pack_leaves_session_capture_to_the_backend() -> None:
    pack_root = Path(
        str(resources.files("raes_env_packs") / "resources" / "packs" / "techvault")
    )
    manifest = json.loads(
        (pack_root / "associated-artifacts.json").read_text(encoding="utf-8")
    )
    artifacts = manifest["artifacts"]
    assert "techvault-kali-capture-client" not in artifacts
    assert "techvault-kali-wrap-shell" not in artifacts
    assert not (pack_root / "assets/content/kali-capture-client").exists()
    assert not (pack_root / "assets/content/kali-wrap-shell.sh").exists()
