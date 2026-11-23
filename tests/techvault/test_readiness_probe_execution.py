"""A TechVault native source is refused without read-only readiness (#1700)."""

import pytest

from aptl.utils.probe_execution import bounded_probe_commands
from tests.test_readiness_probe_execution import Runner


def test_stimulating_native_source_is_refused_without_read_only_readiness():
    from aptl.core.correlation.clock import FixedClockProvider
    from aptl.core.evidence.adapters.sources import WindowedQueryCollector
    from aptl_techvault.evidence.techvault import SuricataWazuhSqliSource

    def forbidden(*args):
        pytest.fail("readiness invoked the target stimulus or acquisition query")

    source = SuricataWazuhSqliSource(forbidden, forbidden, forbidden)
    with bounded_probe_commands(Runner(), 1024):
        assert not WindowedQueryCollector("native", source).check_readiness(
            FixedClockProvider(measurement_time="2026-11-03T04:00:00Z")
        )
