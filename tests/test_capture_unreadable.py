"""Unreadable tool observations cannot become an observed zero-action result."""

import pytest
from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.runstore import LocalRunStore
from aptl.utils.pathsafe import PathContainmentError, REASON_SYMLINK
from tests.test_participant_capture import _grant, _payload


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("private detail"),
        PathContainmentError(REASON_SYMLINK, "private detail"),
    ],
)
def test_unreadable_tools_keep_invocations_and_report_partial(
    tmp_path, monkeypatch, failure
):
    import aptl.core.evidence.participant_capture as owner

    archive = ParticipantCaptureArchive(LocalRunStore(tmp_path), _grant())
    archive.record(_payload())
    real_list = owner.listdir_contained_nofollow

    def unavailable(base, relative):
        if "participant-tool-capture" in relative.parts:
            raise failure
        return real_list(base, relative)

    monkeypatch.setattr(owner, "listdir_contained_nofollow", unavailable)
    result = archive.fetch("start", "end")
    assert result.status is CollectorStatus.MID_RUN_LOSS
    assert result.records[0]["invocations"]
    assert result.records[0]["tool_capture_complete"] is False
    assert "private detail" not in repr(result)
