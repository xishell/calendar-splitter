from __future__ import annotations

import re
from typing import List, Optional, Tuple

from icalendar import Calendar, vText

from .rules import CourseRules

# Detect course by "(IS1200)" in summary or KTH course URL in description
RE_COURSE_IN_SUMMARY = re.compile(r"\(([A-Z0-9\-]{4,})\)")
RE_KTH_COURSE_URL = re.compile(r"/course/([A-Z0-9\-]{4,})/")

DEFAULT_SUMMARY_RE = re.compile(r"\bLecture\s*(\d+)\b", re.IGNORECASE)
RE_LAB = re.compile(r"\bLab\s+(\d+)\b", re.IGNORECASE)
RE_EXERCISE = re.compile(r"\bExercise\s+(\d+)\b", re.IGNORECASE)


def detect_course_code(summary: str, description: str) -> Optional[str]:
    m = RE_COURSE_IN_SUMMARY.search(summary or "")
    if m:
        return m.group(1)
    m = RE_KTH_COURSE_URL.search(description or "")
    if m:
        return m.group(1)
    return None


def extract_number_and_kind(summary: str, cr: Optional[CourseRules]) -> Tuple[Optional[int], Optional[str]]:
    s = summary or ""
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
    if not cr:
        return summary, description or ""

    # If required, ensure "(COURSE)" appears in summary
    if cr.require_course_in_summary and f"({course})" not in (summary or ""):
        return summary, description or ""

    n, kind = extract_number_and_kind(summary, cr)
    title = None
    module = None

    if n is not None:
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

    # SUMMARY
    new_summary = summary
    if title and n is not None:
        tpl = cr.title_template or "{kind} {n} - {title} - {course}"
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


def clone_calendar_base(src_cal: Calendar, name: str) -> Calendar:
    dst = Calendar()
    for key in ("PRODID", "VERSION", "CALSCALE", "METHOD", "X-WR-CALDESC", "X-PUBLISHED-TTL"):
        if key in src_cal:
            dst.add(key, src_cal.get(key))
    dst.add("X-WR-CALNAME", vText(name))
    return dst
