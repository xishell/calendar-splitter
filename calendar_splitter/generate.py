"""Generate calendar events from declarative specs.

The splitter reshapes events that already exist upstream. Study blocks, workouts
and meal prep have no upstream event, so they are authored here from JSON specs
and fed into the same write path.
"""

from __future__ import annotations

import json
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
    duration_min: int = 60
    per_week: int = 1
    rotate: list[str] = field(default_factory=list)
    avoid_conflicts: bool = True
    # minutes each way; the event shows the session, the busy interval covers the journey
    travel_min: int = 0


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
        duration_min=int(raw.get("duration_min", 60)),
        per_week=int(raw.get("per_week", 1)),
        rotate=list(raw.get("rotate", [])),
        avoid_conflicts=bool(raw.get("avoid_conflicts", True)),
        travel_min=int(raw.get("travel_min", 0)),
    )

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
                color=raw.get("color", ""),
                rules=[
                    _parse_rule(r, f"{path.name}[{i}]")
                    for i, r in enumerate(raw.get("rules", []))
                ],
            )
        )
    specs.sort(key=lambda s: (s.priority, s.feed))
    _log.info("Loaded %d generated feed spec(s).", len(specs))
    return specs


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


def _expand_recurring(
    rule: Rule, tz: ZoneInfo, busy: list[tuple[datetime, datetime]]
) -> list[Slot]:
    since = date.fromisoformat(rule.since)
    until = date.fromisoformat(rule.until)
    w_start = time.fromisoformat(rule.window[0])
    w_end = time.fromisoformat(rule.window[1])
    duration = timedelta(minutes=rule.duration_min)

    slots: list[Slot] = []
    rotation = 0

    for monday in _weeks(since, until):
        placed = 0
        for day_name in rule.days:
            if placed >= rule.per_week:
                break
            day = monday + timedelta(days=_WEEKDAYS[day_name])
            if day < since or day > until:
                continue

            latest = datetime.combine(day, w_end, tzinfo=tz) - duration
            cursor = datetime.combine(day, w_start, tzinfo=tz)
            travel = timedelta(minutes=rule.travel_min)
            while cursor <= latest:
                finish = cursor + duration
                if not (rule.avoid_conflicts and _overlaps(cursor - travel, finish + travel, busy)):
                    label = rule.rotate[rotation % len(rule.rotate)] if rule.rotate else ""
                    slots.append(
                        Slot(
                            summary=rule.summary.replace("{rotate}", label),
                            description=rule.description.replace("{rotate}", label),
                            start=cursor,
                            end=finish,
                            location=rule.location,
                        )
                    )
                    busy.append((cursor - travel, finish + travel))
                    rotation += 1
                    placed += 1
                    break
                cursor += _STEP
            else:
                _log.debug("No free slot for %r on %s", rule.summary, day)

        # a partial week at either end of the range cannot fill, so that is not worth warning about
        full_week = monday >= since and monday + timedelta(days=6) <= until
        if placed < rule.per_week and full_week:
            _log.warning(
                "%r: only placed %d/%d in week of %s",
                rule.summary, placed, rule.per_week, monday,
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


def generate_feed(spec: FeedSpec, busy: list[tuple[datetime, datetime]]) -> list[Slot]:
    """Expand one spec into slots. Appends placements to busy so feeds don't collide."""
    slots: list[Slot] = []
    for rule in spec.rules:
        if rule.kind == "fixed":
            fixed = _expand_fixed(rule, spec.tz)
            slots.extend(fixed)
            travel = timedelta(minutes=rule.travel_min)
            busy.extend((s.start - travel, s.end + travel) for s in fixed)
        else:
            slots.extend(_expand_recurring(rule, spec.tz, busy))
    _log.info("Generated %d event(s) for feed %s.", len(slots), spec.feed)
    return slots
