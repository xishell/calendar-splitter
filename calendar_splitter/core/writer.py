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


def new_calendar(name: str, color: str = "") -> Any:
    """Fresh calendar for generated feeds, which have no upstream to clone from."""
    cal: Any = Calendar()  # type: ignore[no-untyped-call]
    cal.add("PRODID", "-//calendar-splitter//generated//EN")
    cal.add("VERSION", "2.0")
    cal.add("X-WR-CALNAME", vText(name))
    if color:
        # apple reads the first, google and thunderbird the second
        cal.add("X-APPLE-CALENDAR-COLOR", vText(color))
        cal.add("X-OUTLOOK-COLOR", vText(color))
    return cal


def build_generated_event(uid: str, slot: Any) -> Any:
    """Build an ICS event from a generated slot (duck-typed to avoid importing generate)."""
    ev: Any = Event()  # type: ignore[no-untyped-call]
    ev.add("UID", uid)
    ev.add("DTSTART", slot.start)
    ev.add("DTEND", slot.end)
    ev.add("SUMMARY", vText(slot.summary))
    ev.add("DESCRIPTION", vText(slot.description or ""))
    if slot.location:
        ev.add("LOCATION", vText(slot.location))
    return ev
