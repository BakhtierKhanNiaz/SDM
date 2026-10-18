"""Which state changes a download may make."""

import pytest

from sdm.core.downloads import DownloadState, check_transition

S = DownloadState


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (S.QUEUED, S.DOWNLOADING),
        (S.QUEUED, S.CANCELLED),
        (S.QUEUED, S.INTERRUPTED),
        (S.DOWNLOADING, S.COMPLETED),
        (S.DOWNLOADING, S.FAILED),
        (S.DOWNLOADING, S.CANCELLED),
        (S.DOWNLOADING, S.INTERRUPTED),
        (S.DOWNLOADING, S.PAUSED),
        (S.QUEUED, S.PAUSED),
        (S.PAUSED, S.QUEUED),  # resume
        (S.INTERRUPTED, S.QUEUED),  # resume after a crash
        (S.FAILED, S.QUEUED),  # retry
        (S.PAUSED, S.CANCELLED),  # discard the partial file
    ],
)
def test_allowed(old, new):
    check_transition(old, new)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (S.QUEUED, S.COMPLETED),  # can't finish without downloading
        (S.COMPLETED, S.DOWNLOADING),  # completed and cancelled are final
        (S.COMPLETED, S.QUEUED),
        (S.CANCELLED, S.QUEUED),
        (S.INTERRUPTED, S.DOWNLOADING),  # resuming goes through queued
        (S.PAUSED, S.DOWNLOADING),
        (S.PAUSED, S.COMPLETED),
    ],
)
def test_refused(old, new):
    with pytest.raises(ValueError, match="can't go from"):
        check_transition(old, new)


def test_active_states():
    assert {s for s in S if s.is_active} == {S.QUEUED, S.DOWNLOADING}


def test_resumable_states():
    assert {s for s in S if s.can_resume} == {S.PAUSED, S.FAILED, S.INTERRUPTED}
