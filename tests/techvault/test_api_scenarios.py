"""The scenario API projects the released pack the repository selects (#1700)."""

from pathlib import Path

import pytest

from tests.test_api_scenarios import api_client


@pytest.fixture
def released_api_client(api_client, tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    (tmp_path / "aptl.json").write_bytes((project_root / "aptl.json").read_bytes())
    return api_client


def test_list_reports_validated_acquired_pack_identity(released_api_client, tmp_path):
    response = released_api_client.get("/api/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == ["techvault-participant-study"]
    assert body[0]["name"] == "TechVault Participant Study"
    assert body[0]["pack"] == {
        "id": "techvault-participant-study",
        "version": "7.2.4",
        "set_digest": "sha256:cac134be0c2d9a5a99266623c5438718c6cca7996cc80cbc7d8bbd5c4fff6b6a",
        "maturity": "built",
    }
    assert body[0]["validation"]["valid"] is True
    assert body[0]["required_containers"]
    assert ".aptl/staged-packs" not in response.text
    assert ".sdl.yaml" not in response.text
    assert not list((tmp_path / ".aptl").rglob("pack.yaml"))


def test_detail_projects_same_validated_identity(released_api_client, tmp_path):
    response = released_api_client.get("/api/scenarios/techvault-participant-study")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "techvault-participant-study"
    assert body["pack"]["id"] == "techvault-participant-study"
    assert body["pack"]["version"] == "7.2.4"
    assert body["pack"]["maturity"] == "built"
    assert body["blocks"][0]["type"] == "narrative"
    assert ".aptl/staged-packs" not in response.text
    assert not list((tmp_path / ".aptl").rglob("pack.yaml"))
