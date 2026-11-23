"""The TechVault gate and adapter pages keep their reader routes (#1700)."""

from tests.test_docs_user_journey import assert_split_pages_cross_link, reader_routes


def test_techvault_pages_are_reachable_from_reader_navigation() -> None:
    routes = reader_routes()

    assert {
        "raes/techvault-static-validation-gate.md",
        "raes/techvault-live-validation-gate.md",
    } <= routes["Reference"]
    assert "sdl/techvault-curated-variants.md" in routes["How-to guides"]
    assert "components/techvault-adapter-boundary.md" in routes["Explanation"]
    assert_split_pages_cross_link({
        "raes/techvault-static-validation-gate.md": "raes/scenario-validation.md",
        "raes/techvault-live-validation-gate.md": "raes/live-validation.md",
    })
