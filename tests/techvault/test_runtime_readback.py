"""Released TechVault plan and adapter readback limits (#1700)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from raes_contracts.vocabulary import ObservationStrength
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH

from aptl.backends._raes_planning_entry import AptlPlanningOptions
from aptl.backends.raes_runtime import plan_for_target
from aptl.backends.scenario_startup import (
    observe_scenario_runtime_concerns,
)
from aptl.core.runtime_readback import ConcernReading
from tests.test_runtime_readback import _selection


def test_full_released_techvault_plan_fits_normal_finite_limits(
    released_techvault_bundle, released_techvault_scenario
):
    from pathlib import Path

    from raes_contracts.realization_structure import validate_realization_value
    from raes_contracts.runtime_value_limits import PLAN_VALUE_LIMITS
    from raes_processor.compiler import compile_scenario_runtime_model
    from raes_runtime.backend_input_contracts import backend_input_violation
    from raes_runtime.backend_realization_authority import _RealizationApplyContext

    from aptl.backends.raes import create_aptl_runtime_target
    from aptl.core.config import AptlConfig
    from tests.techvault.pack import _TECHVAULT_FLAG_PARAMETERS

    target = create_aptl_runtime_target(
        project_dir=Path(__file__).resolve().parents[2],
        config=AptlConfig(lab={"name": "finite-plan"}),
        backend=MagicMock(),
        bundle=released_techvault_bundle,
    )
    compiled = compile_scenario_runtime_model(
        released_techvault_scenario, parameters=_TECHVAULT_FLAG_PARAMETERS
    )
    result = plan_for_target(
        target,
        released_techvault_scenario,
        AptlPlanningOptions(parameters=_TECHVAULT_FLAG_PARAMETERS),
    )
    plan = result.provisioning
    assert len(plan.resources) > 100
    assert len(compiled.realization_requirements) > 1000
    assert len(plan.realization_authority) > 1000
    assert (
        backend_input_violation(
            (plan,),
            authority=_RealizationApplyContext(
                requirements=compiled.realization_requirements,
                plan=plan,
            ),
        )
        is None
    )
    assert validate_realization_value(
        plan, limits=PLAN_VALUE_LIMITS, python_carriers=True
    ).conformant
    assert not validate_realization_value(
        "x" * (PLAN_VALUE_LIMITS.max_scalar_bytes + 1), limits=PLAN_VALUE_LIMITS
    ).conformant


def test_adapter_native_value_varies_without_any_release_key():
    from subprocess import CompletedProcess

    from raes.runtime_configuration import RuntimeConfiguration

    from aptl_techvault.database_readback import database_services

    current = {"database": "first"}

    class Backend:
        def container_exec(self, name, cmd, *, timeout=None):
            sql = cmd[-1]
            replies = {
                "SHOW server_version": "16.1",
                "SHOW port": "5432",
                "SHOW listen_addresses": "0.0.0.0",
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename": "records",
                "SELECT rolname || '|' || rolcanlogin FROM pg_roles WHERE rolname = 'app'": "app|true",
            }
            if "FROM pg_database" in sql:
                text = current["database"]
            else:
                text = replies[sql]
            return CompletedProcess(cmd, 0, text, "")

    def reader(backend, node):
        kind = "runtime-database-services"
        return {
            CONCERN_PAYLOAD_PATH[kind]: ConcernReading(
                kind,
                database_services(backend, node),
                ObservationStrength.GUEST_OBSERVED,
            )
        }

    identity, selection = _selection(reader)
    observed = []
    for name in ("first", "second"):
        current["database"] = name
        runtime = RuntimeConfiguration.model_validate(
            {
                "database_services": [
                    {
                        "database_service_id": "selected-db",
                        "engine": "postgresql",
                        "version": "16.1",
                        "databases": [
                            {
                                "database_id": "data",
                                "name": name,
                                "schemas": [
                                    {
                                        "schema_id": "public",
                                        "name": "public",
                                        "tables": [
                                            {"table_id": "records", "name": "records"},
                                        ],
                                    },
                                ],
                            }
                        ],
                        "roles": [{"role_id": "app", "name": "app", "can_login": True}],
                    }
                ]
            }
        )
        node = SimpleNamespace(runtime=runtime, container_name="isolated-db")
        readings = observe_scenario_runtime_concerns(
            identity, Backend(), node, selection=selection
        )
        observed.append(
            readings[CONCERN_PAYLOAD_PATH["runtime-database-services"]].value[0][
                "databases"
            ][0]["name"]
        )
        current["database"] = "wrong-native-database"
        assert (
            observe_scenario_runtime_concerns(
                identity, Backend(), node, selection=selection
            )
            == {}
        )
    assert observed == ["first", "second"]
