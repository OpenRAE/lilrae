"""A selected adapter declares kernel demand; core owns the probe."""

from types import SimpleNamespace

import pytest


def _plan(minimum):
    from aptl.backends.scenario_startup import ScenarioStartupPlan
    return ScenarioStartupPlan("scripts/seed.sh", ("fixture",), ("fixture",), minimum_max_map_count=minimum)


def test_no_demand_never_probes_the_cli_hosts_kernel(monkeypatch):
    from aptl.core import sysreqs
    def unexpected(*args, **kwargs):
        pytest.fail("an adapter-free scenario probed the host kernel")
    monkeypatch.setattr(sysreqs, "check_max_map_count", unexpected)
    result = sysreqs.check_scenario_max_map_count(None, selected_mode="native-linux")
    assert result.passed
    assert not result.applicable


@pytest.mark.parametrize("minimum", [True, 0, -1, "262144", 2**40])
def test_malformed_adapter_demand_is_rejected(minimum):
    from aptl.backends.scenario_startup import _validated_plan, ScenarioStartupProviderError
    plan = _plan(minimum)
    with pytest.raises(ScenarioStartupProviderError):
        _validated_plan(plan)


def test_generic_demand_is_used_without_a_product_or_pack_name(monkeypatch):
    from aptl.core import sysreqs
    calls = []
    def observe(minimum, *, selected_mode):
        calls.append((minimum, selected_mode))
        return sysreqs.SysReqResult(True, minimum, minimum)
    monkeypatch.setattr(sysreqs, "check_max_map_count", observe)
    result = sysreqs.check_scenario_max_map_count(400000, selected_mode="selected-engine")
    assert result.passed
    assert calls == [(400000, "selected-engine")]


def test_doctor_skips_kernel_requirement_when_selected_pack_has_none(monkeypatch):
    from aptl.core import sysreqs
    from aptl.core._doctor_runtime import _max_map_count_check
    from aptl.core._doctor_common import CheckStatus
    def unexpected(*args, **kwargs):
        pytest.fail("doctor probed a kernel for a scenario without that demand")
    monkeypatch.setattr(sysreqs, "check_max_map_count", unexpected)
    check = _max_map_count_check(SimpleNamespace(), minimum=None)
    assert check.status is CheckStatus.SKIPPED


def test_doctor_derives_no_kernel_demand_for_the_admitted_owned_fixture(monkeypatch):
    from pathlib import Path
    from importlib.metadata import EntryPoint
    from aptl.core._doctor_runtime import _selected_kernel_demand
    from aptl.core.config import AptlConfig
    from tests.fixture_pack import FIXTURE_PACK_IDENTITY
    original = EntryPoint.load
    def guarded(entry):
        if entry.value.startswith('aptl_techvault'):
            pytest.fail('fixture selected the original pack adapter')
        return original(entry)
    monkeypatch.setattr(EntryPoint, 'load', guarded)
    config = AptlConfig(scenario={
        'identity': FIXTURE_PACK_IDENTITY,
        'pack_directory': 'tests/fixtures/packs/' + FIXTURE_PACK_IDENTITY,
    })
    root = Path(__file__).resolve().parents[1]
    assert _selected_kernel_demand(config, root) == (None, False)


def test_public_artifact_locator_rejects_an_unknown_producer(tmp_path):
    from aptl.backends.scenario_service_policy import artifact_source_path
    artifact = SimpleNamespace(generator='rendered_config', provenance='unknown-owner:unknown/v1', name='example')
    with pytest.raises(ValueError, match='unsupported generated artifact'):
        artifact_source_path(tmp_path, artifact)


@pytest.mark.parametrize("kernel_sufficient", [False, True])
def test_start_enforces_demand_without_host_tools_before_build_or_apply(tmp_path, monkeypatch, kernel_sufficient):
    from aptl.core import lab, sysreqs

    plan = _plan(400000)
    assert not plan.lifecycle_capabilities
    ctx = lab._LabStartContext(project_dir=tmp_path, skip_seed=True)
    ctx.scenario_startup = plan
    ctx.start_selection = SimpleNamespace(startup=plan)
    effects = []
    def build_or_apply(context):
        effects.append(context)
    monkeypatch.setattr(lab, "_LAB_START_STEPS", (lab._step_check_sysreqs, build_or_apply))
    monkeypatch.setattr(lab, "check_scenario_max_map_count", lambda minimum, **kwargs: sysreqs.SysReqResult(kernel_sufficient, 1 if not kernel_sufficient else minimum, minimum))
    monkeypatch.setattr(lab, "check_docker_buildx", lambda: pytest.fail("HOST_TOOLS was not requested"))
    failure = None
    for step in lab._selected_start_steps(ctx):
        failure = step(ctx)
        if failure is not None:
            break
    if kernel_sufficient:
        assert failure is None
        assert effects == [ctx]
    else:
        assert failure is not None
        assert not failure.success
        assert effects == []
