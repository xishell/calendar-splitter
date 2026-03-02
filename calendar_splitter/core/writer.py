"""ICS output generation."""

from __future__ import annotations

from typing import Any

from icalendar import Calendar, Event, vText

from calendar_splitter.core.models import ClassifiedEvent


def clone_calendar_base(src_cal: Any, name: str) -> Any:
    """Clone calendar metadata without events."""
    dst: Any = Calendar()  # type: ignore[no-untyped-call]
    for key in ("PRODID", "VERSION", "CALSCALE", "METHOD", "X-WR-CALDESC", "X-PUBLISHED-TTL"):
        if key in src_cal:
            dst.add(key, src_cal.get(key))
    dst.add("X-WR-CALNAME", vText(name))
    return dst


def build_event(
    classified: ClassifiedEvent,
    new_summary: str,
    new_description: str,
) -> Any:
    """Build an icalendar Event with rewritten summary/description and passthrough properties."""
    ev: Any = Event()  # type: ignore[no-untyped-call]

    src = classified.event

    # Add core properties that were parsed into separate fields
    if src.uid:
        ev.add("UID", src.uid)
    if src.start is not None:
        ev.add("DTSTART", src.start)
    if src.end is not None:
        ev.add("DTEND", src.end)
    if src.location:
        ev.add("LOCATION", vText(src.location))

    # Add passthrough properties from original
    for key, value in src.properties.items():
        ev.add(key, value)

    ev.add("SUMMARY", vText(new_summary))
    ev.add("DESCRIPTION", vText(new_description or ""))

    return ev
