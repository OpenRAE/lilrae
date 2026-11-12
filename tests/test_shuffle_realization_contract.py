"""Issue #913: consume Shuffle's released contract without post-start repair."""

from __future__ import annotations

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ENVIRONMENT = {
    "SHUFFLE_APP_SDK_TIMEOUT": ("120", "plain"),
    "SHUFFLE_DEFAULT_APIKEY": (
        "31a211c4-ea5c-4a49-b022-5e2434e758a7",
        "secret_fixture",
    ),
    "SHUFFLE_OPENSEARCH_PASSWORD": ("StrongPassword123!", "secret_fixture"),
    "SHUFFLE_OPENSEARCH_SKIPSSL_VERIFY": ("true", "plain"),
    "SHUFFLE_OPENSEARCH_URL": ("https://shuffle-opensearch:9200", "plain"),
    "SHUFFLE_OPENSEARCH_USERNAME": ("admin", "plain"),
}


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def test_release_manual_has_executable_reverse_negative_harness() -> None:
    manual = (PROJECT_ROOT / "docs" / "testing" / "smoke-test-plan.md").read_text(
        encoding="utf-8"
    )

    reverse_section = manual.split("### QA-MCP-REVERSE:", 1)[1].split(
        "### QA-ARCHIVE:", 1
    )[0]
    assert "aptl.validation.mcp_protocol" in reverse_section
    assert '"mcp/mcp-reverse/build/index.js"' in reverse_section
    assert '"reverse_run_command"' in reverse_section
    assert 'payload.get("success") is not False' in reverse_section
    assert '"outcome": "expected-unavailable"' in reverse_section


def test_release_manual_requires_valid_browser_trust_for_soc_uis() -> None:
    """The hands-on UI path must be executable without TLS bypasses."""

    manual = (PROJECT_ROOT / "docs" / "testing" / "smoke-test-plan.md").read_text(
        encoding="utf-8"
    )

    assert "config/wazuh_indexer_ssl_certs/root-ca.pem" in manual
    assert "config/soc_certs/lab-ca.pem" in manual
    assert "https://wazuh.dashboard:<reported-host-port>" in manual
    assert "443` is only the default" in manual
    assert "aptl lab status --json --output qa-start-status.json" in manual
    assert "certificate warning" in manual
    assert "aptl container shell aptl-suricata" in manual
    assert "does not claim passive visibility" in manual


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False},
        {"success": False, "error": "internal error", "command": "which r2"},
        {"success": False, "command": "which r2", "output": {"code": 1}},
        {
            "success": False,
            "command": "different",
            "error": "Reverse Engineering instance is not enabled",
        },
    ],
)
def test_reverse_negative_harness_rejects_unrelated_failures(monkeypatch, payload):
    import json
    from aptl.validation import mcp_protocol

    manual = (PROJECT_ROOT / "docs/testing/smoke-test-plan.md").read_text()
    section = manual.split("### QA-MCP-REVERSE:", 1)[1].split("### QA-ARCHIVE:", 1)[0]
    program = section.split("import json\n", 1)[1].split("\nPY\n", 1)[0]
    monkeypatch.setattr(
        mcp_protocol,
        "call_mcp_tool",
        lambda *_a, **_kw: {"content": [{"type": "text", "text": json.dumps(payload)}]},
    )
    with pytest.raises(SystemExit, match="FAIL"):  # NOSONAR
        exec(compile("import json\n" + program, "reverse-negative-harness", "exec"), {})
