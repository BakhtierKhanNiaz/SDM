"""Splitting a download into parts for parallel connections, and saving the parts map (M5).

A file of `total` bytes is covered by segments that sit end to end with no gaps or overlaps:
[0 .. a-1], [a .. b-1], ... [z .. total-1]. Each segment records how many of its bytes have
arrived (always a prefix of the segment). The map is saved in the history so a paused or
interrupted download asks only for what is missing.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: int  # first byte
    end: int  # last byte, inclusive
    received: int = 0  # bytes from `start` already on disk

    @property
    def size(self) -> int:
        return self.end - self.start + 1

    @property
    def next_byte(self) -> int:
        return self.start + self.received

    @property
    def remaining(self) -> int:
        return self.size - self.received

    @property
    def done(self) -> bool:
        return self.received >= self.size


def plan_segments(total: int, max_connections: int, min_part: int) -> list[Segment]:
    """Split `total` bytes into at most `max_connections` equal parts of at least `min_part`.

    The last part takes the remainder. Returns a single segment when splitting isn't worth it.
    """
    if total <= 0:
        raise ValueError("total must be positive")
    count = max(1, min(max_connections, total // max(1, min_part)))
    base = total // count
    segments = []
    start = 0
    for index in range(count):
        end = total - 1 if index == count - 1 else start + base - 1
        segments.append(Segment(start, end))
        start = end + 1
    return segments


def total_received(segments: Iterable[Segment]) -> int:
    return sum(segment.received for segment in segments)


def segments_cover(segments: Sequence[Segment], total: int) -> bool:
    """True if the segments sit end to end over exactly [0, total) with sane progress."""
    if not segments or total <= 0:
        return False
    expected_start = 0
    for segment in segments:
        values = (segment.start, segment.end, segment.received)
        if any(type(v) is not int for v in values):  # rejects bools and floats too
            return False
        if segment.start != expected_start or segment.end < segment.start:
            return False
        if not 0 <= segment.received <= segment.size:
            return False
        expected_start = segment.end + 1
    return expected_start == total


def encode_segments(segments: Iterable[Segment]) -> str:
    return json.dumps([[s.start, s.end, s.received] for s in segments], separators=(",", ":"))


def decode_segments(text: str | None, total: int | None) -> tuple[Segment, ...] | None:
    """Read a saved parts map; None if it is missing, malformed, or doesn't fit the file.

    The text comes from the database, so nothing in it is trusted until checked.
    """
    if not text or not total:
        return None
    try:
        rows = json.loads(text)
    except ValueError:
        return None
    if not isinstance(rows, list) or len(rows) > 10_000:
        return None
    try:
        segments = tuple(Segment(*row) for row in rows if isinstance(row, list) and len(row) == 3)
    except TypeError:
        return None
    if len(segments) != len(rows) or not segments_cover(segments, total):
        return None
    return segments


def pick_split(parts: Sequence[tuple[int, int]], min_part: int) -> tuple[int, int] | None:
    """Dynamic splitting: which part to halve for a free connection, and where.

    `parts` are (next byte still needed, last byte) of the parts still downloading. The part
    with the most bytes left gives its second half to a new connection, if both halves keep at
    least `min_part` bytes. Returns (index into `parts`, first byte of the new part) or None.
    On ties the earliest part wins. (OBS-001 suggested IDM does this: each new start point was
    half as far from the previous one as the one before.)
    """
    best: tuple[int, int] | None = None
    best_left = 0
    for index, (next_byte, last) in enumerate(parts):
        left = last - next_byte + 1
        if left >= 2 * min_part and left > best_left:
            best, best_left = (index, next_byte + left // 2), left
    return best
