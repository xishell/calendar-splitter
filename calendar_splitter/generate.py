"""Generate calendar events from declarative specs.

The splitter reshapes events that already exist upstream. Study blocks, workouts
and meal prep have no upstream event, so they are authored here from JSON specs
and fed into the same write path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from calendar_splitter.exceptions import ConfigError
from calendar_splitter.logging import get_logger

_log = get_logger(__name__)

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

# candidate starts are tried on this grid inside the window
_STEP = timedelta(minutes=15)

_WINDOW_PARTS = 2


@dataclass(frozen=True)
class Placed:
    """A session already on the calendar, with what it was, for recovery checks."""

    start: datetime
    end: datetime
    tags: tuple[str, ...] = ()
    # recovery tags apply across every feed, but a per-day cap is about one feed only
    feed: str = ""


@dataclass(frozen=True)
class Slot:
    """A generated event, before it becomes ICS."""

    summary: str
    description: str
    start: datetime
    end: datetime
    location: str = ""


@dataclass
class Rule:
    """One rule inside a spec: either a fixed event or a recurring placement."""

    kind: str
    summary: str
    description: str = ""
    location: str = ""

    # fixed
    start: str = ""
    end: str = ""

    # recurring
    since: str = ""
    until: str = ""
    days: list[str] = field(default_factory=list)
    window: tuple[str, str] = ("09:00", "17:00")
    # tried only for sessions the preferred window could not fit
    fallback_window: tuple[str, str] | None = None
    duration_min: int = 60
    per_week: int = 1
    rotate: list[str] = field(default_factory=list)
    avoid_conflicts: bool = True
    # minutes each way; the event shows the session, the busy interval covers the journey
    travel_min: int = 0

    # "early" packs toward the start of the window, "late" toward the end
    prefer: str = "early"
    # breathing room required either side of anything already scheduled
    min_gap_min: int = 0
    # what this session is, for recovery purposes: e.g. ["lower", "hard"]
    tags: tuple[str, ...] = ()
    # hours that must pass after a session carrying the given tag
    min_hours_after: dict[str, float] = field(default_factory=dict)
    # cap on sessions from this spec in one day; 0 means no cap
    max_per_day: int = 0
    # set from the spec at load time so a cap counts only its own feed
    feed: str = ""


@dataclass
class FeedSpec:
    """A generated feed: a name plus the rules that fill it."""

    feed: str
    name: str = ""
    timezone: str = "Europe/Stockholm"
    # lower runs first, so it claims slots before later feeds see them
    priority: int = 50
    # CSS name or #rrggbb; clients that honour it colour the whole subscription
    color: str = ""
    # waking hours; every rule window is clamped to this so nothing lands while asleep
    day_start: str = ""
    day_end: str = ""
    rules: list[Rule] = field(default_factory=list)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _parse_rule(raw: dict[str, Any], where: str) -> Rule:
    kind = raw.get("kind", "")
    if kind not in ("fixed", "recurring"):
        raise ConfigError(f"{where}: rule kind must be 'fixed' or 'recurring', got {kind!r}")
    if not raw.get("summary"):
        raise ConfigError(f"{where}: rule needs a summary")

    window = raw.get("window", ["09:00", "17:00"])
    if len(window) != _WINDOW_PARTS:
        raise ConfigError(f"{where}: window must be [start, end]")

    days = [d.lower()[:3] for d in raw.get("days", [])]
    for d in days:
        if d not in _WEEKDAYS:
            raise ConfigError(f"{where}: unknown weekday {d!r}")

    rule = Rule(
        kind=kind,
        summary=raw["summary"],
        description=raw.get("description", ""),
        location=raw.get("location", ""),
        start=raw.get("start", ""),
        end=raw.get("end", ""),
        since=raw.get("from", ""),
        until=raw.get("until", ""),
        days=days,
        window=(window[0], window[1]),
        fallback_window=(fb[0], fb[1]) if (fb := raw.get("fallback_window")) else None,
        duration_min=int(raw.get("duration_min", 60)),
        per_week=int(raw.get("per_week", 1)),
        rotate=list(raw.get("rotate", [])),
        avoid_conflicts=bool(raw.get("avoid_conflicts", True)),
        travel_min=int(raw.get("travel_min", 0)),
        prefer=raw.get("prefer", "early"),
        min_gap_min=int(raw.get("min_gap_min", 0)),
        tags=tuple(raw.get("tags", [])),
        min_hours_after={k: float(v) for k, v in raw.get("min_hours_after", {}).items()},
        max_per_day=int(raw.get("max_per_day", 0)),
    )

    if rule.prefer not in ("early", "late"):
        raise ConfigError(f"{where}: prefer must be 'early' or 'late', got {rule.prefer!r}")
    if kind == "fixed" and not (rule.start and rule.end):
        raise ConfigError(f"{where}: fixed rule needs start and end")
    if kind == "recurring":
        if not (rule.since and rule.until):
            raise ConfigError(f"{where}: recurring rule needs from and until")
        if not rule.days:
            raise ConfigError(f"{where}: recurring rule needs at least one day")
        if rule.per_week > len(rule.days):
            raise ConfigError(
                f"{where}: per_week {rule.per_week} exceeds {len(rule.days)} candidate days"
            )
    return rule


def load_specs(specs_dir: Path) -> list[FeedSpec]:
    """Load every *.json in specs_dir as a generated feed."""
    if not specs_dir.is_dir():
        _log.info("No specs dir at %s, skipping generation.", specs_dir)
        return []

    specs: list[FeedSpec] = []
    for path in sorted(specs_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path.name}: invalid JSON: {exc}") from exc
        if not raw.get("feed"):
            raise ConfigError(f"{path.name}: missing 'feed'")
        specs.append(
            FeedSpec(
                feed=raw["feed"],
                name=raw.get("name", raw["feed"]),
                timezone=raw.get("timezone", "Europe/Stockholm"),
                priority=int(raw.get("priority", 50)),
                day_start=raw.get("day_start", ""),
                day_end=raw.get("day_end", ""),
                color=raw.get("color", ""),
                rules=[
                    _parse_rule(r, f"{path.name}[{i}]")
                    for i, r in enumerate(raw.get("rules", []))
                ],
            )
        )
    for spec in specs:
        for rule in spec.rules:
            rule.feed = spec.feed
        _clamp_to_waking_hours(spec)
    specs.sort(key=lambda s: (s.priority, s.feed))
    _log.info("Loaded %d generated feed spec(s).", len(specs))
    return specs


def slug(text: str) -> str:
    """Lowercase ascii-ish slug, used to build stable event uids."""
    text = text.lower().translate(str.maketrans("åäöéèü", "aaoeeu"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40]


def _clamp_to_waking_hours(spec: FeedSpec) -> None:
    """Pull every rule window inside the spec's waking hours."""
    if not (spec.day_start or spec.day_end):
        return
    lo = time.fromisoformat(spec.day_start) if spec.day_start else time.min
    hi = time.fromisoformat(spec.day_end) if spec.day_end else time.max

    def clamp(win: tuple[str, str]) -> tuple[str, str]:
        a, b = time.fromisoformat(win[0]), time.fromisoformat(win[1])
        return (max(a, lo).isoformat("minutes"), min(b, hi).isoformat("minutes"))

    for rule in spec.rules:
        if rule.kind != "recurring":
            continue          # a fixed event is a real commitment, not ours to move
        rule.window = clamp(rule.window)
        if rule.fallback_window:
            rule.fallback_window = clamp(rule.fallback_window)


def _overlaps(start: datetime, end: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    return any(start < b_end and b_start < end for b_start, b_end in busy)


def _weeks(since: date, until: date) -> list[date]:
    """Monday of each week touched by the range."""
    first = since - timedelta(days=since.weekday())
    out, cur = [], first
    while cur <= until:
        out.append(cur)
        cur += timedelta(days=7)
    return out


def _clearance(start: datetime, end: datetime, busy: list[tuple[datetime, datetime]]) -> float:
    """Minutes to the nearest scheduled thing. Higher means more breathing room."""
    gaps = []
    for b_start, b_end in busy:
        if b_start >= end:
            gaps.append((b_start - end).total_seconds() / 60)
        elif b_end <= start:
            gaps.append((start - b_end).total_seconds() / 60)
    return min(gaps, default=24 * 60)


def _recovered(rule: Rule, start: datetime, placed: list[Placed]) -> bool:
    """True if enough time has passed since every session this rule needs to recover from."""
    for tag, hours in rule.min_hours_after.items():
        need = timedelta(hours=hours)
        for prior in placed:
            if tag in prior.tags and prior.end <= start and start - prior.end < need:
                return False
            # a later session must also respect the gap, or order of placement decides recovery
            if tag in prior.tags and prior.start > start and prior.start - start < need:
                return False
    return True


def _candidates(
    rule: Rule, day: date, win: tuple[str, str],
    ctx: tuple[ZoneInfo, list[tuple[datetime, datetime]], list[Placed]],
) -> list[tuple[tuple[int, float, float], datetime]]:
    """Every legal start on this day, keyed by how good it is. Lower key sorts better."""
    tz, busy, placed = ctx
    duration = timedelta(minutes=rule.duration_min)
    travel = timedelta(minutes=rule.travel_min)
    gap = timedelta(minutes=rule.min_gap_min)
    w_start = datetime.combine(day, time.fromisoformat(win[0]), tzinfo=tz)
    w_end = datetime.combine(day, time.fromisoformat(win[1]), tzinfo=tz)

    if rule.max_per_day and rule.feed:
        today = sum(1 for p in placed if p.start.date() == day and p.feed == rule.feed)
        if today >= rule.max_per_day:
            return []

    out = []
    cursor = w_start
    while cursor <= w_end - duration:
        finish = cursor + duration
        blocked = rule.avoid_conflicts and _overlaps(
            cursor - travel - gap, finish + travel + gap, busy
        )
        if not blocked and _recovered(rule, cursor, placed):
            offset = (cursor - w_start if rule.prefer == "early" else w_end - finish)
            # hour buckets keep the time-of-day preference dominant; clearance breaks ties
            # inside an hour, which is what stops sessions stacking back to back
            key = (
                int(offset.total_seconds() // 3600),
                -_clearance(cursor, finish, busy),
                offset.total_seconds(),
            )
            out.append((key, cursor))
        cursor += _STEP
    return out


def _place_one(
    rule: Rule, day: date, win: tuple[str, str],
    ctx: tuple[ZoneInfo, list[tuple[datetime, datetime]], list[Placed], str],
) -> Slot | None:
    """Best legal slot for one day inside one window, or None."""
    tz, busy, placed, label = ctx
    options = _candidates(rule, day, win, (tz, busy, placed))
    if not options:
        return None
    _, start = min(options)
    finish = start + timedelta(minutes=rule.duration_min)
    travel = timedelta(minutes=rule.travel_min)
    busy.append((start - travel, finish + travel))
    placed.append(Placed(start, finish, rule.tags, rule.feed))
    return Slot(
        summary=rule.summary.replace("{rotate}", label),
        description=rule.description.replace("{rotate}", label),
        start=start,
        end=finish,
        location=rule.location,
    )


def _expand_recurring(
    rule: Rule, tz: ZoneInfo, busy: list[tuple[datetime, datetime]], placed: list[Placed]
) -> list[Slot]:
    since = date.fromisoformat(rule.since)
    until = date.fromisoformat(rule.until)

    slots: list[Slot] = []
    rotation = 0

    for monday in _weeks(since, until):
        days = [monday + timedelta(days=_WEEKDAYS[d]) for d in rule.days]
        days = [d for d in days if since <= d <= until]
        placed_this_week = 0

        # the preferred window gets every candidate day before the fallback is touched,
        # so "mornings where possible" does not collapse to "mornings on monday only"
        windows = [rule.window] + ([rule.fallback_window] if rule.fallback_window else [])
        for win in windows:
            for day in days:
                if placed_this_week >= rule.per_week:
                    break
                label = rule.rotate[rotation % len(rule.rotate)] if rule.rotate else ""
                slot = _place_one(rule, day, win, (tz, busy, placed, label))
                if slot is not None:
                    slots.append(slot)
                    rotation += 1
                    placed_this_week += 1
            if placed_this_week >= rule.per_week:
                break

        full_week = monday >= since and monday + timedelta(days=6) <= until
        if placed_this_week < rule.per_week and full_week:
            _log.warning(
                "%r: only placed %d/%d in week of %s",
                rule.summary, placed_this_week, rule.per_week, monday,
            )
    return slots


def _expand_fixed(rule: Rule, tz: ZoneInfo) -> list[Slot]:
    start = datetime.fromisoformat(rule.start)
    end = datetime.fromisoformat(rule.end)
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    if end.tzinfo is None:
        end = end.replace(tzinfo=tz)
    if end < start:
        raise ConfigError(f"{rule.summary!r}: end is before start")
    return [
        Slot(
            summary=rule.summary,
            description=rule.description,
            start=start,
            end=end,
            location=rule.location,
        )
    ]


def generate_feed(
    spec: FeedSpec,
    busy: list[tuple[datetime, datetime]],
    placed: list[Placed] | None = None,
) -> list[Slot]:
    """Expand one spec into slots. Appends to busy and placed so later feeds see them."""
    slots: list[Slot] = []
    placed = [] if placed is None else placed
    for rule in spec.rules:
        if rule.kind == "fixed":
            fixed = _expand_fixed(rule, spec.tz)
            slots.extend(fixed)
            travel = timedelta(minutes=rule.travel_min)
            busy.extend((s.start - travel, s.end + travel) for s in fixed)
            placed.extend(Placed(s.start, s.end, rule.tags, rule.feed) for s in fixed)
        else:
            slots.extend(_expand_recurring(rule, spec.tz, busy, placed))
    _log.info("Generated %d event(s) for feed %s.", len(slots), spec.feed)
    return slots
