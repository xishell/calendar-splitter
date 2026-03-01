from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, cast

from icalendar import Calendar, Event, vText

from .log_sanitize import safe_log, safe_warn
from .rewrite import (clone_calendar_base, detect_course_code,
                      extract_number_and_kind, matches_item, rewrite_event)
from .rules import CourseRules
from .tokens import ensure_token


def split_and_write(
    upstream_bytes: bytes,
    rules_by_course: Dict[str, CourseRules],
    feeds_dir: Path,
    token_map: Dict[str, str],
) -> int:
    cal = cast(Calendar, Calendar.from_ical(upstream_bytes.decode("utf-8")))

    buckets: Dict[str, Calendar] = {}
    total = 0
    kept = 0
    filtered = 0

    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        total += 1

        summary = str(comp.get("SUMMARY", "") or "")
        description = str(comp.get("DESCRIPTION", "") or "")
        location = str(comp.get("LOCATION", "") or "")
        start_dt_raw = comp.get("DTSTART")
        start_dt = None
        if start_dt_raw:
            dt_value = start_dt_raw.dt if hasattr(start_dt_raw, "dt") else start_dt_raw
            if isinstance(dt_value, datetime):
                start_dt = dt_value
        course = detect_course_code(summary, description)
        if not course:
            continue

        if course not in buckets:
            buckets[course] = clone_calendar_base(cal, name=course)

        new_ev = Event()
        for k, v in comp.property_items():
            if k in ("SUMMARY", "DESCRIPTION", "BEGIN", "END"):
                continue
            new_ev.add(k, v)

        cr = rules_by_course.get(course)

        # Apply event filtering based on match strategies
        should_skip = False
        matched_item = None
        n = None
        kind = None
        if cr and cr.event_types:
            n, kind = extract_number_and_kind(summary, cr)

            # Find the matching EventType
            event_type = None
            if kind:
                for et in cr.event_types:
                    if et.type == kind:
                        event_type = et
                        break

            if event_type and event_type.items:
                if n is not None:
                    # Numbered event - direct lookup
                    item = event_type.items.get(n)
                    if item and item.match_strategies:
                        # Check if event matches the configured strategies
                        if not matches_item(item, summary, description, location, start_dt):
                            should_skip = True
                        else:
                            matched_item = item
                else:
                    # Unnumbered event - try matching against all items
                    # Find the first item that matches
                    for item_num, item in event_type.items.items():
                        if item.match_strategies:
                            if matches_item(item, summary, description, location, start_dt):
                                matched_item = item
                                n = item_num  # Assign the matched item's number
                                break

                    # If we have items with match strategies but no match, skip this event
                    if matched_item is None and any(item.match_strategies for item in event_type.items.values()):
                        should_skip = True

        # Skip events that don't match their filtering criteria
        if should_skip:
            filtered += 1
            continue

        # For unnumbered events, pass the matched number and kind for proper rewriting
        new_sum, new_desc = rewrite_event(summary, description, course, cr, n, kind)
        new_ev.add("SUMMARY", vText(new_sum))
        new_ev.add("DESCRIPTION", vText(new_desc or ""))

        buckets[course].add_component(new_ev)
        kept += 1

    safe_log(
        "Parsed %d events; kept %d, filtered %d across %d courses.",
        total,
        kept,
        filtered,
        len(buckets),
    )

    feeds_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for course, ccal in sorted(buckets.items()):
        tok = ensure_token(token_map, course)
        out = feeds_dir / f"{course}--{tok}.ics"
        try:
            out.write_bytes(ccal.to_ical())
            written += 1
        except Exception as e:
            safe_warn("Failed writing %s: %s", out.name, str(e))

    return written
