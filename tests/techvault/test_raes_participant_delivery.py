"""The TechVault participant study declares its delivery collectors (#1700)."""

from __future__ import annotations

from types import SimpleNamespace

from aptl_techvault.study import StudyCapture


def test_study_capture_declares_all_four_delivery_collectors() -> None:
    contribution = StudyCapture.resolve(SimpleNamespace())
    registration_ids = {
        registration.registration_id for registration in contribution.registrations
    }

    assert {
        "aptl.collector.participant-delivery.red-start",
        "aptl.collector.participant-delivery.red-stop",
        "aptl.collector.participant-delivery.blue-start",
        "aptl.collector.participant-delivery.blue-stop",
    } <= registration_ids
