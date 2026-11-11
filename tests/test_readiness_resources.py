"""Startup resource demands follow the exact sealed environment entry."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from aptl.backends._raes_admission_helpers import bind_admission_trial
from aptl.backends.raes_provisioner import AptlProvisioner
from aptl.backends.readiness_apparatus import ReadinessApparatus
from aptl.backends.scenario_family import FamilyTrialInput, admit_family_trial
from aptl.backends.scenario_startup import ScenarioStartupPlan, select_scenario_startup
from aptl.core.config import AptlConfig
from tests.test_family_adapter_contract import (
    BACKEND,
    _install_family_entries,
)
from tests.test_family_adapter_contract import (
    family_input as family_input,
)


def test_entry_resources_reject_absent_and_previous_selections(
    monkeypatch, family_input, tmp_path
):
    backend_identity = replace(
        BACKEND, provider="docker-compose", transport="docker-compose"
    )
    previous = None
    for path, minimum in (("/opt/a", 262144), ("/opt/b", 524288)):
        bundle, family, plan = family_input(path)
        trial = admit_family_trial(
            bundle, backend_identity, FamilyTrialInput(plan, "entry-a", family)
        )
        entries = _install_family_entries(monkeypatch, trial)
        startup = next(
            entry.load() for entry in entries if entry.group == "aptl.scenario_startup"
        )
        startup.resolve = lambda context: ScenarioStartupPlan(
            "seed.sh",
            ("baseline",),
            ("baseline",),
            minimum_max_map_count=(
                262144
                if context.trial.scenario.content["payload"].path == "/opt/a"
                else 524288
            ),
        )
        config = AptlConfig()
        bound = bind_admission_trial(
            bundle, config, FamilyTrialInput(plan, "entry-a", family), None, None
        )
        required = select_scenario_startup(bound)
        provisioner = AptlProvisioner(tmp_path, config, object(), bundle)
        apparatus = ReadinessApparatus(
            SimpleNamespace(plan=plan, family=family),
            SimpleNamespace(provisioner=provisioner),
            None,
            bundle.root,
        )
        with pytest.raises(ValueError, match="trial-resource-selection-mismatch"):
            apparatus.required_resource_minimum("entry-a")
        provisioner.startup_selection = required
        assert apparatus.required_resource_minimum("entry-a") == minimum
        if previous is not None:
            provisioner.startup_selection = previous
            with pytest.raises(ValueError, match="trial-resource-selection-mismatch"):
                apparatus.required_resource_minimum("entry-a")
        provisioner.startup_selection = replace(
            required, plan=replace(required.plan, minimum_max_map_count=None)
        )
        with pytest.raises(ValueError, match="trial-resource-selection-mismatch"):
            apparatus.required_resource_minimum("entry-a")
        previous = required
