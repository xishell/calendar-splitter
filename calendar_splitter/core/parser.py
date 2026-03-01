"""ICS parsing and course code detection."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from icalendar import Calendar

from calendar_splitter.core.models import Event
from calendar_splitter.exceptions import ParseError

# Course code detection patterns (ordered by specificity)
_RE_KTH_STYLE = re.compile(r"\b([A-Z]{2}\d{4})\b")
_RE_PARENS = re.compile(r"\(([A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]*)\)")
_RE_URL = re.compile(r"/course/([A-Z0-9\-]{4,})/")


def detect_course_code(summary: str, description: str) -> str | None:
    """Detect course code from summary or description.

    Tries patterns in order of specificity:
    1. KTH-style (2 letters + 4 digits) in summary
    2. Parentheses pattern in summary
    3. Course URL pattern in description
    """
    m = _RE_KTH_STYLE.search(summary or "")
    if m:
        return m.group(1)

    m = _RE_PARENS.search(summary or "")
    if m:
        return m.group(1)

    m = _RE_URL.search(description or "")
    if m:
        return m.group(1)

    return None


def parse_calendar(data: bytes) -> list[Event]:
    """Parse ICS bytes into a list of Event dataclasses."""
    try:
        cal: Any = Calendar.from_ical(data.decode("utf-8"))
    except Exception as exc:
        msg = f"Failed to parse ICS data: {exc}"
        raise ParseError(msg) from exc

    events: list[Event] = []
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue

        uid = str(comp.get("UID", "") or "")
        summary = str(comp.get("SUMMARY", "") or "")
        description = str(comp.get("DESCRIPTION", "") or "")
        location = str(comp.get("LOCATION", "") or "")

        start_dt = _extract_datetime(comp.get("DTSTART"))
        end_dt = _extract_datetime(comp.get("DTEND"))

        # Collect all other properties for passthrough
        props: dict[str, Any] = {}
        skip = {"SUMMARY", "DESCRIPTION", "LOCATION", "UID", "DTSTART", "DTEND", "BEGIN", "END"}
        for key, value in comp.property_items():
            if key not in skip:
                props[key] = value

        events.append(Event(
            uid=uid,
            summary=summary,
            description=description,
            location=location,
            start=start_dt,
            end=end_dt,
            properties=props,
        ))

    return events


def parse_calendar_raw(data: bytes) -> Any:
    """Parse ICS bytes and return the raw icalendar Calendar object."""
    try:
        return Calendar.from_ical(data.decode("utf-8"))
    except Exception as exc:
        msg = f"Failed to parse ICS data: {exc}"
        raise ParseError(msg) from exc


def _extract_datetime(dt_prop: object) -> datetime | None:
    """Extract a datetime from an icalendar property."""
    if dt_prop is None:
        return None
    dt_value = dt_prop.dt if hasattr(dt_prop, "dt") else dt_prop
    if isinstance(dt_value, datetime):
        return dt_value
    return None
