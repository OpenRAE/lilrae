"""The docs lane also runs the TechVault documentation checks (#1700)."""

from tests.test_docs_publishing import DOCS_LANE_GENERIC_TESTS, docs_lane_test_paths


def test_docs_lane_runs_exactly_the_generic_and_techvault_doc_checks() -> None:
    assert docs_lane_test_paths() == DOCS_LANE_GENERIC_TESTS | {
        "tests/techvault/test_docs_user_journey.py",
        "tests/techvault/test_scenario_pack_ownership_contract.py",
    }
