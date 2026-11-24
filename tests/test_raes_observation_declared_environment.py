"""Readback reports only the environment that the scenario declares."""

from types import SimpleNamespace

from raes.runtime_configuration import RuntimeConfiguration

from aptl.backends._raes_observation_index import _declared_environment_runtime


def test_profile_added_variables_are_not_read_back():
    selected = RuntimeConfiguration.model_validate({"environment": [
        {"name": "MODE", "value": "on"},
        {"name": "REDIS_PASSWORD", "value_classification": "redacted",
         "value_from": {"generated_artifact": "misp-cache-credential", "output": "password"}},
    ]})
    declared = SimpleNamespace(payload={"spec": {"node": {"runtime": {"environment": [{"name": "MODE", "value": "on"}]}}}})
    assert [v.name for v in _declared_environment_runtime(selected, declared).environment] == ["MODE"]
    undeclared = SimpleNamespace(payload={"spec": {"node": {"runtime": {}}}})
    assert _declared_environment_runtime(selected, undeclared).environment == []
