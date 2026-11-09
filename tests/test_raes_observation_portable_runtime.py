"""Readback leaves out variables that read a backend-owned generated artifact."""

from raes.runtime_configuration import RuntimeConfiguration

from aptl.backends._raes_observation_index import _portable_runtime


def test_backend_owned_artifact_variables_are_not_read_back():
    runtime = RuntimeConfiguration.model_validate({"environment": [
        {"name": "MODE", "value": "on"},
        {"name": "TLS_KEY", "value_classification": "redacted",
         "value_from": {"generated_artifact": "soc-certificates", "output": "key"}},
        {"name": "REDIS_PASSWORD", "value_classification": "redacted",
         "value_from": {"generated_artifact": "misp-cache-credential", "output": "password"}},
    ]})
    portable = _portable_runtime(runtime, {"soc-certificates"})
    assert [variable.name for variable in portable.environment] == ["MODE", "TLS_KEY"]
    assert _portable_runtime(runtime, {"soc-certificates", "misp-cache-credential"}) is runtime
