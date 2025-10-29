from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from icalendar import Calendar, vText

from .rules import CourseRules, EventItem, MatchStrategy

# Detect course codes with improved patterns to reduce false positives

# KTH-style: 2 letters + 4 digits (IS1200, DD1351, SF1922)
# More specific - avoids matching pure numbers like "(2024)"
RE_COURSE_KTH_STYLE = re.compile(r"\b([A-Z]{2}\d{4})\b")

# Generic: in parentheses, starts with 2+ letters, contains at least 1 digit
# Filters out "(2024)", "(HTML)", "(PDF)" but matches "(IS1200HT)", "(CS101)"
RE_COURSE_PARENS = re.compile(r"\(([A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]*)\)")

# URL pattern unchanged
RE_KTH_COURSE_URL = re.compile(r"/course/([A-Z0-9\-]{4,})/")

DEFAULT_SUMMARY_RE = re.compile(r"\bLecture\s*(\d+)\b", re.IGNORECASE)
RE_LAB = re.compile(r"\bLab\s+(\d+)\b", re.IGNORECASE)
RE_EXERCISE = re.compile(r"\bExercise\s+(\d+)\b", re.IGNORECASE)


def detect_course_code(summary: str, description: str) -> Optional[str]:
    """Detect course code from summary or description.

    Tries patterns in order of specificity to avoid false positives:
    1. KTH-style (2 letters + 4 digits) anywhere in summary
    2. Parentheses pattern (starts with 2+ letters)
    3. Course URL pattern in description
    """
    # Try KTH-style first (most specific, highest confidence)
    m = RE_COURSE_KTH_STYLE.search(summary or "")
    if m:
        return m.group(1)

    # Try parentheses pattern (medium specificity)
    m = RE_COURSE_PARENS.search(summary or "")
    if m:
        return m.group(1)

    # Try URL pattern in description (fallback)
    m = RE_KTH_COURSE_URL.search(description or "")
    if m:
        return m.group(1)

    return None


def extract_number_and_kind(summary: str, cr: Optional[CourseRules]) -> Tuple[Optional[int], Optional[str]]:
    """Extract event number and type from summary.

    If CourseRules has event_types defined, use those patterns.
    Otherwise fall back to legacy hardcoded patterns.

    Args:
        summary: Event summary text
        cr: Course rules (optional)

    Returns:
        Tuple of (number, event_type) or (None, None) if no match
    """
    s = summary or ""

    # Try new flexible event_types system first
    if cr and cr.event_types:
        for event_type in cr.event_types:
            for pattern in event_type.patterns:
                m = pattern.search(s)
                if m:
                    # If unnumbered event, return None for number
                    if event_type.unnumbered:
                        return None, event_type.type

                    # Otherwise extract number from first capturing group
                    try:
                        if m.groups():
                            return int(m.group(1)), event_type.type
                        else:
                            # Pattern has no capturing group, can't extract number
                            return None, event_type.type
                    except (ValueError, IndexError):
                        # Failed to parse number, skip this pattern
                        continue
        # No event_types matched, fall through to legacy logic

    # Legacy logic for backward compatibility
    if cr and cr.summary_regex:
        m = cr.summary_regex.search(s)
        if m:
            try:
                return int(m.group(1)), "lecture"
            except Exception:
                pass
    m = DEFAULT_SUMMARY_RE.search(s)
    if m:
        try:
            return int(m.group(1)), "lecture"
        except Exception:
            pass
    m = RE_LAB.search(s)
    if m:
        try:
            return int(m.group(1)), "lab"
        except Exception:
            pass
    m = RE_EXERCISE.search(s)
    if m:
        try:
            return int(m.group(1)), "exercise"
        except Exception:
            pass
    return None, None


def rewrite_event(summary: str, description: str, course: str, cr: Optional[CourseRules]) -> Tuple[str, str]:
    """Rewrite event summary and description based on course rules.

    Supports both new EventType system and legacy lecture/lab/exercise dictionaries.

    Args:
        summary: Original event summary
        description: Original event description
        course: Course code
        cr: Course rules (optional)

    Returns:
        Tuple of (new_summary, new_description)
    """
    if not cr:
        return summary, description or ""

    # If required, ensure "(COURSE)" appears in summary
    if cr.require_course_in_summary and f"({course})" not in (summary or ""):
        return summary, description or ""

    n, kind = extract_number_and_kind(summary, cr)
    title = None
    module = None
    metadata: Dict[str, Any] = {}

    # Try new EventType system first
    if cr.event_types and kind:
        # Find the matching EventType
        event_type = None
        for et in cr.event_types:
            if et.type == kind:
                event_type = et
                break

        if event_type:
            # Find the matching EventItem
            item = event_type.items.get(n)
            if item:
                # Get all metadata
                metadata = item.metadata.copy()
                title = item.get("title")
                module = item.get("module")

    # Fall back to legacy system if no metadata found
    if not metadata and n is not None:
        info = None
        if kind == "lecture":
            info = cr.lectures.get(n)
        elif kind == "lab":
            info = cr.labs.get(n)
        elif kind == "exercise":
            info = cr.exercises.get(n)

        if info:
            t = (info.get("title") or "").strip()
            m = (info.get("module") or "").strip()
            title = t or None
            module = m or None
            metadata = {"title": title or "", "module": module or ""}

    # SUMMARY
    new_summary = summary
    if title and n is not None:
        tpl = cr.title_template or "{kind} {n} - {title} - {course}"
        # Get display name from EventType or use default
        if kind and cr.event_types:
            for et in cr.event_types:
                if et.type == kind:
                    prefix = et.display_name
                    break
            else:
                prefix = kind.capitalize()
        else:
            prefix = "Lecture" if kind == "lecture" else ("Lab" if kind == "lab" else "Exercise")

        new_summary = tpl.format(kind=prefix, n=n, title=title, course=course)

    # DESCRIPTION
    if (description or "").strip():
        tpld = cr.description_template or "{module}\nCanvas: {canvas}\n\n{old_desc}"
        new_desc = tpld.format(
            module=(module or "").strip(),
            canvas=(cr.canvas or "").strip(),
            old_desc=(description or "").strip(),
        ).strip()
        return new_summary, new_desc

    parts: List[str] = []
    if module:
        parts.append(module)
    if cr.canvas:
        parts.append(f"Canvas: {cr.canvas}")
    if (description or "").strip():
        parts.append(description.strip())
    return new_summary, ("\n\n".join(parts)).strip()


def matches_strategy(
    strategy: MatchStrategy,
    summary: str,
    description: str,
    location: str,
    start_dt: Optional[datetime],
) -> bool:
    """Check if an event matches a given strategy.

    Args:
        strategy: The matching strategy to evaluate
        summary: Event summary/title
        description: Event description
        location: Event location
        start_dt: Event start datetime

    Returns:
        True if the event matches the strategy
    """
    if strategy.strategy == "time":
        # Match based on day of week and time range
        if not start_dt:
            return False

        timeslot = strategy.data.get("timeslot", {})
        if isinstance(timeslot, str):
            # Legacy format: just a string description, can't match
            return False

        # Check day of week (0=Monday, 6=Sunday)
        if "day" in timeslot:
            day = timeslot["day"]
            if isinstance(day, str):
                day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                          "friday": 4, "saturday": 5, "sunday": 6}
                day = day_map.get(day.lower(), -1)
            if start_dt.weekday() != day:
                return False

        # Check time range
        if "start_time" in timeslot and "end_time" in timeslot:
            start_time = timeslot["start_time"]  # Format: "HH:MM" or "HHMM"
            end_time = timeslot["end_time"]

            # Parse time strings
            def parse_time(t: str) -> tuple[int, int]:
                t = t.replace(":", "")
                return int(t[:2]), int(t[2:4])

            start_h, start_m = parse_time(start_time)
            end_h, end_m = parse_time(end_time)

            event_h = start_dt.hour
            event_m = start_dt.minute

            # Check if event time is in range
            event_minutes = event_h * 60 + event_m
            range_start = start_h * 60 + start_m
            range_end = end_h * 60 + end_m

            if not (range_start <= event_minutes < range_end):
                return False

        return True

    elif strategy.strategy == "description":
        # Match regex pattern in description or summary
        pattern_str = strategy.data.get("pattern", "")
        if not pattern_str:
            return False

        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            text = f"{summary or ''} {description or ''}"
            return bool(pattern.search(text))
        except re.error:
            return False

    elif strategy.strategy == "location":
        # Match specific location
        expected_location = strategy.data.get("location", "")
        if not expected_location:
            return False
        return expected_location.lower() in (location or "").lower()

    elif strategy.strategy == "url":
        # Match URL pattern in description
        pattern_str = strategy.data.get("pattern", "")
        if not pattern_str:
            return False

        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            return bool(pattern.search(description or ""))
        except re.error:
            return False

    elif strategy.strategy == "all":
        # All sub-strategies must match
        sub_strategies = strategy.data.get("strategies", [])
        for sub_data in sub_strategies:
            sub_strategy = MatchStrategy.from_dict(sub_data)
            if not matches_strategy(sub_strategy, summary, description, location, start_dt):
                return False
        return True

    elif strategy.strategy == "any":
        # Any sub-strategy matches
        sub_strategies = strategy.data.get("strategies", [])
        for sub_data in sub_strategies:
            sub_strategy = MatchStrategy.from_dict(sub_data)
            if matches_strategy(sub_strategy, summary, description, location, start_dt):
                return True
        return False

    # Unknown strategy - don't match
    return False


def matches_item(
    item: EventItem,
    summary: str,
    description: str,
    location: str,
    start_dt: Optional[datetime],
) -> bool:
    """Check if an event matches any of the item's strategies.

    Args:
        item: The EventItem with matching strategies
        summary: Event summary/title
        description: Event description
        location: Event location
        start_dt: Event start datetime

    Returns:
        True if the event matches any strategy (or if no strategies defined)
    """
    if not item.match_strategies:
        return True  # No strategies = match all

    # Sort by priority (lower = higher priority)
    sorted_strategies = sorted(item.match_strategies, key=lambda s: s.priority)

    # Try each strategy in priority order
    for strategy in sorted_strategies:
        if matches_strategy(strategy, summary, description, location, start_dt):
            return True

    return False


def clone_calendar_base(src_cal: Calendar, name: str) -> Calendar:
    dst = Calendar()
    for key in ("PRODID", "VERSION", "CALSCALE", "METHOD", "X-WR-CALDESC", "X-PUBLISHED-TTL"):
        if key in src_cal:
            dst.add(key, src_cal.get(key))
    dst.add("X-WR-CALNAME", vText(name))
    return dst
