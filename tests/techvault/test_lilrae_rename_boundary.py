"""Current decision records describe TechVault as a scenario pack (#1700)."""

from __future__ import annotations

from tests.test_lilrae_rename_boundary import (
    CURRENT_DECISION_FILES,
    REJECTED_CURRENT_PHRASES,
)


def test_current_decisions_reject_the_false_product_split() -> None:
    """Current records describe identity continuity and TechVault as a pack."""

    current_text = "\n".join(
        path.read_text(encoding="utf-8") for path in CURRENT_DECISION_FILES
    )
    lowered = current_text.casefold()

    for phrase in REJECTED_CURRENT_PHRASES:
        assert phrase.casefold() not in lowered
    assert "one product across a rename" in lowered
    assert "techvault is a scenario pack" in lowered
    assert (
        "APTL-to-LilRAE identity continuity and capability ownership".casefold()
        in lowered
    )
