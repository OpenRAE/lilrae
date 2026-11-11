"""Unit coverage for live-smoke configuration helpers."""

from __future__ import annotations

import pytest

from tests import helpers


def test_credential_falls_back_to_generated_project_env(monkeypatch):
    monkeypatch.delenv("APTL_SMOKE", raising=False)
    monkeypatch.delenv("MISP_API_KEY", raising=False)
    monkeypatch.setattr(helpers, "load_dotenv", lambda _path: {"MISP_API_KEY": "generated"})

    with pytest.raises(RuntimeError, match="APTL_SMOKE=1"):
        helpers.live_credentials()
    monkeypatch.setenv("APTL_SMOKE", "1")
    assert helpers.live_credentials()["MISP_API_KEY"] == "generated"


def test_credential_prefers_explicit_process_environment(monkeypatch):
    monkeypatch.setenv("APTL_SMOKE", "1")
    monkeypatch.setenv("MISP_API_KEY", "operator")
    monkeypatch.setattr(helpers, "load_dotenv", lambda _path: {"MISP_API_KEY": "generated"})

    assert helpers.live_credentials()["MISP_API_KEY"] == "operator"


def test_curl_json_uses_lab_ca_for_soc_https(tmp_path, monkeypatch):
    ca_path = tmp_path / "lab-ca.pem"
    ca_path.touch()
    monkeypatch.setattr(helpers, "LAB_CA_PATH", str(ca_path))
    captured = {}

    def fake_request(url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        return {}

    monkeypatch.setattr("aptl.utils.curl_safe.curl_json", fake_request)

    assert helpers.curl_json(f"{helpers.MISP_URL}/events/restSearch") == {}
    assert captured["ca_cert_path"] == str(ca_path)
    assert captured["insecure"] is False
