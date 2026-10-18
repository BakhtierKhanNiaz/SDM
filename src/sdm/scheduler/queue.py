"""Which waiting downloads to start, which to pause, and when to retry (M6, ADR-0013).

Pure logic: no Qt, no network, no database. The controller describes the queue, the settings
and the current time; `plan_queue` answers. Because the time is passed in, tests use a fake
clock.

- Waiting downloads start in queue order, up to the limit (1-8, default 3).
- "Start now" (forced) downloads start at once, ignoring the limit and the schedule.
- Outside the schedule's window, queue downloads that are running are paused (they go back
  to waiting, keeping their partial file) and nothing new starts.
- If the limit is lowered, the downloads furthest down the queue are paused back to waiting.
- A failed download waiting for its automatic retry starts only once its retry time has come.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time

MIN_LIMIT, MAX_LIMIT, DEFAULT_LIMIT = 1, 8, 3
RETRY_DELAYS = (60.0, 300.0, 900.0)  # seconds before automatic retries 1, 2 and 3
ALL_DAYS = frozenset(range(7))  # 0 = Monday ... 6 = Sunday, as datetime.weekday()


@dataclass(frozen=True)
class Schedule:
    """When the queue may run. Disabled means always."""

    enabled: bool = False
    start: time = time(0, 0)
    stop: time = time(0, 0)
    days: frozenset[int] = ALL_DAYS

    def is_open(self, now: datetime) -> bool:
        if not self.enabled:
            return True
        clock, day = now.time(), now.weekday()
        if self.start == self.stop:  # the whole day
            return day in self.days
        if self.start < self.stop:
            return day in self.days and self.start <= clock < self.stop
        # Overnight, e.g. 23:00-06:00: the window belongs to the day it starts on.
        return (clock >= self.start and day in self.days) or (
            clock < self.stop and (day - 1) % 7 in self.days
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "enabled": self.enabled,
                "start": self.start.strftime("%H:%M"),
                "stop": self.stop.strftime("%H:%M"),
                "days": sorted(self.days),
            }
        )

    @classmethod
    def from_json(cls, text: str | None) -> "Schedule":
        """Read a saved schedule; anything malformed gives the default (always open)."""
        try:
            data = json.loads(text or "")
            days = frozenset(int(d) for d in data["days"])
            if not days <= ALL_DAYS or not isinstance(data["enabled"], bool):
                raise ValueError
            return cls(
                enabled=data["enabled"],
                start=time.fromisoformat(data["start"]),
                stop=time.fromisoformat(data["stop"]),
                days=days,
            )
        except (ValueError, TypeError, KeyError):
            return cls()


@dataclass(frozen=True)
class QueueSettings:
    limit: int = DEFAULT_LIMIT
    schedule: Schedule = field(default_factory=Schedule)
    category_subfolders: bool = False  # IDM-style Downloads\\Compressed\\... (off by default)

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit", max(MIN_LIMIT, min(MAX_LIMIT, int(self.limit))))


@dataclass(frozen=True)
class QueueEntry:
    """What the planner needs to know about one queued or running download."""

    id: int
    position: int
    running: bool  # handed to the engine already
    forced: bool = False  # "Start now"
    retry_at: datetime | None = None  # waiting for an automatic retry until then


@dataclass(frozen=True)
class QueuePlan:
    start: tuple[int, ...] = ()
    pause: tuple[int, ...] = ()  # back to waiting, partial file kept


def plan_queue(entries: Sequence[QueueEntry], settings: QueueSettings, now: datetime) -> QueuePlan:
    running = [e for e in entries if e.running and not e.forced]
    waiting = sorted((e for e in entries if not e.running), key=lambda e: e.position)
    start = [e.id for e in waiting if e.forced]
    if not settings.schedule.is_open(now):
        return QueuePlan(start=tuple(start), pause=tuple(e.id for e in running))
    pause: list[int] = []
    excess = len(running) - settings.limit
    if excess > 0:  # the limit was lowered: the last in the queue wait again
        by_position = sorted(running, key=lambda e: e.position, reverse=True)
        pause = [e.id for e in by_position[:excess]]
    slots = max(0, settings.limit - len(running))
    ready = [e for e in waiting if not e.forced and (e.retry_at is None or e.retry_at <= now)]
    start += [e.id for e in ready[:slots]]
    return QueuePlan(start=tuple(start), pause=tuple(pause))


def retry_delay(retries_so_far: int) -> float | None:
    """Seconds before the next automatic retry, or None when the 3 retries are used up."""
    if 0 <= retries_so_far < len(RETRY_DELAYS):
        return RETRY_DELAYS[retries_so_far]
    return None


def reorder(order: Sequence[int], target: int, where: str) -> list[int]:
    """Move `target` within `order`: where is 'up', 'down', 'top' or 'bottom'."""
    items = list(order)
    if target not in items:
        return items
    index = items.index(target)
    items.pop(index)
    new_index = {
        "up": max(0, index - 1),
        "down": min(len(items), index + 1),
        "top": 0,
        "bottom": len(items),
    }.get(where)
    if new_index is None:
        raise ValueError(f"unknown move: {where}")
    items.insert(new_index, target)
    return items
