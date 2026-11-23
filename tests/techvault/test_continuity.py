"""continuity.default_targets() stays pinned to TechVault closed nodes (#1700)."""

from __future__ import annotations


class TestDefaultTargets:
    """``default_targets`` is the pinned continuity audit surface."""

    def test_default_targets_count_pins_audit_surface(self) -> None:
        # The audit surface remains the in-process-agent set. The audit does
        # not grant missing capabilities; inability to inspect is a reported
        # AUDIT_FAILED outcome.
        from aptl.core.continuity import default_targets

        assert set(default_targets()) == {
            "aptl-webapp",
            "aptl-fileshare",
            "aptl-ad",
            "aptl-dns",
        }

    def test_closed_capability_scopes_are_not_default_targets(self, tmp_path) -> None:
        """No closed TechVault node is silently made audit-capable."""

        from raes import parse_sdl_file

        from aptl.core.continuity import default_targets
        from tests.techvault.pack import techvault_scenario_path

        scenario = parse_sdl_file(techvault_scenario_path(tmp_path))
        closed_nodes = {"webapp", "fileshare", "ad", "dns"}

        assert {
            target.removeprefix("aptl-") for target in default_targets()
        } == closed_nodes
        assert all(
            scenario.nodes[name].runtime.linux_capabilities is None
            for name in closed_nodes
        )
