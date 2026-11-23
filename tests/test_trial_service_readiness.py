"""Experiment service checks reuse the ordinary durable-service owners."""

from types import SimpleNamespace

import pytest

from aptl.core.deployment._compose_stateful_readiness import (
    ComposeStatefulReadinessMixin,
)
from aptl.core.lab_types import LabResult


class Backend(ComposeStatefulReadinessMixin):
    def __init__(self, *, running=True, health="healthy", authenticated=True):
        self.running, self.health, self.authenticated = running, health, authenticated
        self.auth_calls = 0

    def container_inspect(self, name):
        return {"State": {"Running": self.running, "Health": {"Status": self.health}}}

    def _verify_stateful_authenticated_readiness(self, spec):
        self.auth_calls += 1
        return None if self.authenticated else LabResult(success=False)


@pytest.mark.parametrize(
    "running,health,authenticated,passes",
    [
        (True, "healthy", True, True),
        (False, "healthy", True, False),
        (True, "unhealthy", True, False),
        (True, "healthy", False, False),
    ],
)
def test_required_services_need_live_health_and_existing_authenticated_check(
    running, health, authenticated, passes
):
    backend = Backend(running=running, health=health, authenticated=authenticated)
    spec = SimpleNamespace(
        nodes=(SimpleNamespace(container_name="required", runtime=None),)
    )
    assert backend.verify_required_service_readiness(spec) is passes
    if running and health == "healthy":
        assert backend.auth_calls == 1
