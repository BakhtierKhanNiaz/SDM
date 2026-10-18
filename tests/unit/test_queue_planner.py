"""The queue planner, the schedule, retries and reordering (pure logic, fake times)."""

from datetime import datetime, time

import pytest

from sdm.core.categories import category_for
from sdm.scheduler.queue import (
    QueueEntry,
    QueuePlan,
    QueueSettings,
    Schedule,
    plan_queue,
    reorder,
    retry_delay,
)

MONDAY_NOON = datetime(2026, 10, 19, 12, 0)  # 19 October 2026 is a Monday


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """A time in the week of 19 October 2026: day 0 = Monday."""
    return datetime(2026, 10, 19 + day, hour, minute)


# ----- categories -----


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("setup.exe", "Programs"),
        ("archive.tar.gz", "Compressed"),
        ("REPORT.PDF", "Documents"),
        ("song.flac", "Music"),
        ("movie.mkv", "Video"),
        ("stream", "General"),
        ("data.bin", "General"),
        (".hidden", "General"),
        ("", "General"),
        (None, "General"),
    ],
)
def test_category_for(name, category):
    assert category_for(name) == category


# ----- the schedule -----


def test_disabled_schedule_is_always_open():
    assert Schedule().is_open(at(6, 3))


def test_daytime_window_and_days():
    office = Schedule(True, time(9, 0), time(17, 0), frozenset({0, 1, 2, 3, 4}))
    assert office.is_open(at(0, 9, 0))  # start is inclusive
    assert not office.is_open(at(0, 17, 0))  # stop is exclusive
    assert not office.is_open(at(0, 8, 59))
    assert not office.is_open(at(5, 12))  # Saturday is not in the days


def test_overnight_window_belongs_to_the_day_it_starts():
    nights = Schedule(True, time(23, 0), time(6, 0), frozenset({4}))  # Friday night only
    assert nights.is_open(at(4, 23, 30))  # Friday 23:30
    assert nights.is_open(at(5, 5, 59))  # early Saturday, still Friday's night
    assert not nights.is_open(at(5, 23, 30))  # Saturday night is not included
    assert not nights.is_open(at(4, 5, 0))  # early Friday belongs to Thursday's night


def test_same_start_and_stop_means_the_whole_day():
    weekends = Schedule(True, time(0, 0), time(0, 0), frozenset({5, 6}))
    assert weekends.is_open(at(6, 15))
    assert not weekends.is_open(at(0, 15))


def test_schedule_round_trip_and_bad_input():
    schedule = Schedule(True, time(1, 30), time(7, 0), frozenset({0, 6}))
    assert Schedule.from_json(schedule.to_json()) == schedule
    for bad in (None, "", "not json", '{"enabled": "yes"}', '{"enabled": true, "days": [9]}'):
        assert Schedule.from_json(bad) == Schedule()


def test_limit_is_kept_between_1_and_8():
    assert QueueSettings(limit=0).limit == 1
    assert QueueSettings(limit=99).limit == 8


# ----- planning -----


def entries(*specs) -> list[QueueEntry]:
    return [QueueEntry(id=i, position=i, running=running) for i, running in specs]


def test_starts_in_queue_order_up_to_the_limit():
    queue = entries((1, True), (2, False), (3, False), (4, False))
    assert plan_queue(queue, QueueSettings(limit=3), MONDAY_NOON) == QueuePlan(start=(2, 3))


def test_queue_position_not_id_decides():
    queue = [QueueEntry(1, 30, False), QueueEntry(2, 10, False), QueueEntry(3, 20, False)]
    assert plan_queue(queue, QueueSettings(limit=2), MONDAY_NOON).start == (2, 3)


def test_lowering_the_limit_sends_the_last_running_back():
    queue = entries((1, True), (2, True), (3, True))
    assert plan_queue(queue, QueueSettings(limit=1), MONDAY_NOON) == QueuePlan(pause=(3, 2))


def test_closed_schedule_pauses_running_and_starts_nothing():
    closed = QueueSettings(schedule=Schedule(True, time(1, 0), time(6, 0)))
    queue = entries((1, True), (2, False))
    assert plan_queue(queue, closed, MONDAY_NOON) == QueuePlan(pause=(1,))


def test_start_now_ignores_the_limit_and_the_schedule():
    closed = QueueSettings(limit=1, schedule=Schedule(True, time(1, 0), time(6, 0)))
    queue = [
        QueueEntry(1, 1, running=True, forced=True),
        QueueEntry(2, 2, running=False, forced=True),
        QueueEntry(3, 3, running=False),
    ]
    assert plan_queue(queue, closed, MONDAY_NOON) == QueuePlan(start=(2,))


def test_a_retry_waits_for_its_time():
    later = datetime(2026, 10, 19, 12, 5)
    queue = [QueueEntry(1, 1, False, retry_at=later), QueueEntry(2, 2, False)]
    assert plan_queue(queue, QueueSettings(limit=3), MONDAY_NOON).start == (2,)
    assert plan_queue(queue, QueueSettings(limit=3), later).start == (1, 2)


def test_retry_delays():
    assert [retry_delay(n) for n in range(4)] == [60.0, 300.0, 900.0, None]


@pytest.mark.parametrize(
    ("where", "expected"),
    [("up", [1, 3, 2, 4]), ("down", [1, 2, 4, 3]), ("top", [3, 1, 2, 4]), ("bottom", [1, 2, 4, 3])],
)
def test_reorder(where, expected):
    assert reorder([1, 2, 3, 4], 3, where) == expected


def test_reorder_edges():
    assert reorder([1, 2], 1, "up") == [1, 2]
    assert reorder([1, 2], 2, "down") == [1, 2]
    assert reorder([1, 2], 9, "top") == [1, 2]
    with pytest.raises(ValueError):
        reorder([1, 2], 1, "sideways")
