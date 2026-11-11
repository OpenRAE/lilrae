"""Only the installed route, key, model, and serving provider establish access."""

import json
from pathlib import Path

import pytest

from aptl.core.opencode import OpenRouterRoute
from aptl.utils.probe_execution import bounded_probe_commands
from aptl.workbench.process import ProcessCleanup, ProcessResult
from aptl.workbench.provider_readiness import openrouter_access_ready


class ProviderRunner:
    def __init__(self, failure=None):
        self.failure, self.calls = failure, []

    def run(self, argv, **options):
        self.calls.append(tuple(argv))
        assert options["max_output_bytes"] <= 65536
        if argv[-1] == "--version":
            return ProcessResult(0, b"1.19.5", b"", ProcessCleanup(1, 0))
        url = next(value for value in argv if value.startswith("https://"))
        headers = [value[1:] for value in argv if value.startswith("@")]
        assert headers
        assert "Bearer synthetic-key" in Path(headers[0]).read_text()
        if self.failure == "transport":
            return ProcessResult(7, b"", b"private failure", ProcessCleanup(1, 0))
        if url.endswith("/key"):
            data = {"data": {"is_free_tier": False, "limit_remaining": 10}}
            if self.failure == "exhausted":
                data["data"]["limit_remaining"] = 0
        elif "/models/user?" in url:
            data = {"data": [{"id": "model"}] if self.failure != "model" else []}
        else:
            assert url.endswith("/models/model/endpoints")
            data = {
                "data": {
                    "id": "model",
                    "endpoints": [
                        {
                            "tag": "test-provider"
                            if self.failure != "provider"
                            else "other",
                            "status": 0 if self.failure != "down" else 1,
                            "max_completion_tokens": 256
                            if self.failure != "capacity"
                            else 1,
                        }
                    ],
                }
            }
        if self.failure == "malformed":
            data = {"data": "private malformed data"}
        output = json.dumps(data).encode()
        if self.failure == "oversized":
            output *= 10000
        return ProcessResult(0, output, b"", ProcessCleanup(1, 0))


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "transport",
        "exhausted",
        "model",
        "provider",
        "down",
        "capacity",
        "malformed",
        "oversized",
        "missing-key",
    ],
)
def test_selected_provider_and_model_access(failure):
    runner = ProviderRunner(failure)
    route = OpenRouterRoute("https://openrouter.ai/api/v1", "test-provider")
    with bounded_probe_commands(runner, 65536):
        assert openrouter_access_ready(
            "openrouter/model",
            route,
            {} if failure == "missing-key" else {"OPENROUTER_API_KEY": "synthetic-key"},
            128,
        ) is (failure is None)
    assert "synthetic-key" not in repr(runner.calls)
    assert all("chat/completions" not in str(call) for call in runner.calls)
