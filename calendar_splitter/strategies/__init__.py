"""Strategy evaluation engine for matching events to configured items."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from calendar_splitter.core.models import (
    ClassifiedEvent,
    CourseConfig,
    Event,
    EventItem,
    EventType,
    MatchStrategy,
    StrategyType,
)
from calendar_splitter.logging import get_logger

_log = get_logger(__name__)


def _match_time(
    data: dict[str, Any], start_dt: datetime | None
) -> bool:
    """Match based on day of week and time range."""
    if not start_dt:
        return False

    if "day" in data:
        day_str = data["day"]
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        expected = day_map.get(day_str.lower(), -1) if isinstance(day_str, str) else day_str
        if start_dt.weekday() != expected:
            return False

    if "start_time" in data and "end_time" in data:
        tz_name = data.get("timezone", "Europe/Stockholm")
        local_dt = start_dt
        if start_dt.tzinfo is not None:
            local_dt = start_dt.astimezone(ZoneInfo(tz_name))

        def _parse_hhmm(t: str) -> int:
            t = t.replace(":", "")
            return int(t[:2]) * 60 + int(t[2:4])

        start_min = _parse_hhmm(data["start_time"])
        end_min = _parse_hhmm(data["end_time"])
        event_min = local_dt.hour * 60 + local_dt.minute

        if not (start_min <= event_min < end_min):
            return False

    return True


def _match_description(
    data: dict[str, Any], summary: str, description: str
) -> bool:
    """Match regex pattern in summary+description."""
    pattern_str = data.get("pattern", "")
    if not pattern_str:
        return False
    try:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        return bool(pattern.search(f"{summary} {description}"))
    except re.error:
        return False


def _match_location(data: dict[str, Any], location: str) -> bool:
    """Match a location string."""
    expected = data.get("location", "")
    if not expected:
        return False
    return expected.lower() in location.lower()


def _match_url(data: dict[str, Any], description: str) -> bool:
    """Match URL pattern in description."""
    pattern_str = data.get("pattern", "")
    if not pattern_str:
        return False
    try:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        return bool(pattern.search(description))
    except re.error:
        return False


def evaluate_strategy(
    strategy: MatchStrategy,
    summary: str,
    description: str,
    location: str,
    start_dt: datetime | None,
) -> bool:
    """Evaluate a single match strategy against event data."""
    dispatch = {
        StrategyType.TIME: lambda: _match_time(strategy.data, start_dt),
        StrategyType.DESCRIPTION: lambda: _match_description(strategy.data, summary, description),
        StrategyType.LOCATION: lambda: _match_location(strategy.data, location),
        StrategyType.URL: lambda: _match_url(strategy.data, description),
        StrategyType.ALL: lambda: all(
            evaluate_strategy(
                MatchStrategy(
                    strategy=StrategyType(s.get("strategy", "")),
                    priority=s.get("priority", 99),
                    data={k: v for k, v in s.items() if k not in ("strategy", "priority")},
                ),
                summary, description, location, start_dt,
            )
            for s in strategy.data.get("strategies", [])
        ),
        StrategyType.ANY: lambda: any(
            evaluate_strategy(
                MatchStrategy(
                    strategy=StrategyType(s.get("strategy", "")),
                    priority=s.get("priority", 99),
                    data={k: v for k, v in s.items() if k not in ("strategy", "priority")},
                ),
                summary, description, location, start_dt,
            )
            for s in strategy.data.get("strategies", [])
        ),
    }
    handler = dispatch.get(strategy.strategy)
    if handler is None:
        return False
    return handler()


def evaluate_item(
    item: EventItem,
    summary: str,
    description: str,
    location: str,
    start_dt: datetime | None,
) -> bool:
    """Check if an event matches any of the item's strategies."""
    if not item.match:
        return True

    sorted_strategies = sorted(item.match, key=lambda s: s.priority)
    return any(
        evaluate_strategy(s, summary, description, location, start_dt)
        for s in sorted_strategies
    )


def _extract_number_and_kind(
    summary: str, config: CourseConfig
) -> tuple[int | None, str | None, EventType | None]:
    """Extract event number, kind, and matched EventType from summary."""
    for event_type in config.event_types:
        for pattern in event_type.patterns:
            m = pattern.search(summary)
            if m:
                if event_type.unnumbered:
                    return None, event_type.type, event_type
                try:
                    if m.groups():
                        return int(m.group(1)), event_type.type, event_type
                    return None, event_type.type, event_type
                except (ValueError, IndexError):
                    continue
    return None, None, None


def classify_event(
    event: Event,
    course_code: str,
    config: CourseConfig,
) -> ClassifiedEvent | None:
    """Classify an event against a course config.

    Returns a ClassifiedEvent if the event matches, or None if it should be
    filtered out by match strategies.
    """
    if config.detection.require_code_in_summary and f"({course_code})" not in event.summary:
        return None

    n, kind, event_type = _extract_number_and_kind(event.summary, config)

    ev = event
    matched_item: EventItem | None = None
    if event_type and event_type.items:
        if n is not None:
            item = event_type.items.get(n)
            if item and item.match:
                if not evaluate_item(
                    item, ev.summary, ev.description, ev.location, ev.start
                ):
                    return None
                matched_item = item
            elif item:
                matched_item = item
        else:
            # Unnumbered: try matching against all items
            for item_num, item in event_type.items.items():
                if item.match and evaluate_item(
                    item, ev.summary, ev.description, ev.location, ev.start
                ):
                    matched_item = item
                    n = item_num
                    break

            if matched_item is None and any(it.match for it in event_type.items.values()):
                return None

    return ClassifiedEvent(
        event=event,
        course_code=course_code,
        event_type=event_type,
        item=matched_item,
        kind=kind,
        number=n,
    )
