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
    ],
)
def test_allowed(old, new):
    check_transition(old, new)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (S.QUEUED, S.COMPLETED),  # can't finish without downloading
        (S.COMPLETED, S.DOWNLOADING),  # finished states are final
        (S.FAILED, S.QUEUED),
        (S.CANCELLED, S.DOWNLOADING),
        (S.INTERRUPTED, S.DOWNLOADING),  # resuming is M4
    ],
)
def test_refused(old, new):
    with pytest.raises(ValueError, match="can't go from"):
        check_transition(old, new)


def test_active_states():
    assert {s for s in S if s.is_active} == {S.QUEUED, S.DOWNLOADING}
