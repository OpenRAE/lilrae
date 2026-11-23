"""The TechVault serving provider lives in its own adapter package (#1700)."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

from aptl.backends.pack_interaction import (
    ENTRY_POINT_GROUP,
)


def test_the_framework_holds_no_pack_specific_serving_logic() -> None:
    """Scenario knowledge lives in an adapter package, never in the framework.

    The distribution registers the TechVault provider, because an adapter is
    the backend's to own and ships in the backend's release. What must stay
    true is the *code* boundary: no module under ``aptl.`` maps a named pack's
    components to operator groups. If one did, a second pack would mean editing
    the framework rather than adding an adapter package.
    """

    registered = {
        entry_point.name
        for entry_point in metadata.entry_points(group=ENTRY_POINT_GROUP)
    }
    assert "techvault.aptl" in registered

    for entry_point in metadata.entry_points(group=ENTRY_POINT_GROUP):
        if entry_point.name == "techvault.aptl":
            assert entry_point.value.startswith("aptl_techvault."), (
                "a pack adapter must live in its own top-level package, not "
                "inside the framework"
            )

    framework = Path(__file__).resolve().parents[2] / "src" / "aptl"
    offenders = {
        str(path.relative_to(framework))
        for path in framework.rglob("*.py")
        if "provision.node.wazuh-manager" in path.read_text(encoding="utf-8")
    }
    assert not offenders, f"pack component addresses leaked into core: {offenders}"
