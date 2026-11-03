"""Run the shared HTTP outcome cases on the Python release before the Go port."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aptl.utils import curl_safe

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "conformance/testdata/http-outcomes.json")
    .read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_http_outcome_contract(case, monkeypatch):
    """Classify curl results without inspecting error text or leaking payloads."""

    def run(_cmd, _timeout):
        if case["failure"] == "request_timeout":
            raise subprocess.TimeoutExpired(cmd="curl", timeout=30)
        if case["failure"] == "curl_unavailable":
            raise OSError("synthetic unavailable transport")
        return SimpleNamespace(
            returncode=case["exit"], stdout=f'{{}}\n{case["status"]:03d}'
        )

    monkeypatch.setattr(curl_safe, "_run_curl", run)
    result = curl_safe.curl_request("https://example.test/")
    assert result.category == case["category"], case["id"]
    assert result.http_status == (case["status"] or None), case["id"]
    assert result.exit_code == case["exit"], case["id"]
