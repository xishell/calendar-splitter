from __future__ import annotations

from pathlib import Path
from typing import Dict, cast

from icalendar import Calendar, Event, vText

from .log_sanitize import safe_log, safe_warn
from .rewrite import clone_calendar_base, detect_course_code, rewrite_event
from .rules import CourseRules
from .tokens import ensure_token


def split_and_write(
    upstream_bytes: bytes,
    rules_by_course: Dict[str, CourseRules],
    feeds_dir: Path,
    token_map: Dict[str, str],
) -> int:
    cal = cast(Calendar, Calendar.from_ical(upstream_bytes.decode('utf-8')))

    buckets: Dict[str, Calendar] = {}
    total = 0
    kept = 0

    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        total += 1

        summary = str(comp.get("SUMMARY", "") or "")
        description = str(comp.get("DESCRIPTION", "") or "")
        course = detect_course_code(summary, description)
        if not course:
            continue

        if course not in buckets:
            buckets[course] = clone_calendar_base(cal, name=course)

        new_ev = Event()
        for k, v in comp.property_items():
            if k in ("SUMMARY", "DESCRIPTION"):
                continue
            new_ev.add(k, v)

        cr = rules_by_course.get(course)
        new_sum, new_desc = rewrite_event(summary, description, course, cr)
        new_ev.add("SUMMARY", vText(new_sum))
        new_ev.add("DESCRIPTION", vText(new_desc or ""))

        buckets[course].add_component(new_ev)
        kept += 1

    safe_log("Parsed %d events; kept %d across %d courses.", total, kept, len(buckets))

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
