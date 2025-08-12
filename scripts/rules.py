from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List

from .log_sanitize import safe_log, safe_warn


DEFAULT_SUMMARY_RE = re.compile(r"\bLecture\s*(\d+)\b", re.IGNORECASE)


@dataclass
class CourseRules:
    course: str
    canvas: Optional[str] = None
    require_course_in_summary: bool = False
    summary_regex: Optional[re.Pattern] = None
    title_template: str = "{kind} {n} - {title} - {course}"
    description_template: str = "{module}\nCanvas: {canvas}\n\n{old_desc}"
    lectures: Dict[int, Dict[str, str]] = field(default_factory=dict)
    labs: Dict[int, Dict[str, str]] = field(default_factory=dict)
    exercises: Dict[int, Dict[str, str]] = field(default_factory=dict)

    @staticmethod
    def from_json(data: Dict[str, Any]) -> "CourseRules":
        # Schema A (e.g., your IS1200_lectures.json)
        if "course" in data:
            course = str(data["course"]).strip()
            cr = CourseRules(course)
            cr.canvas = (data.get("canvas") or "").strip() or None

            match = data.get("match") or {}
            cr.require_course_in_summary = bool(match.get("require_course_in_summary", False))
            srx = match.get("summary_regex")
            if srx:
                try:
                    cr.summary_regex = re.compile(srx, re.IGNORECASE)
                except re.error:
                    cr.summary_regex = DEFAULT_SUMMARY_RE

            if "title_template" in data:
                cr.title_template = str(data["title_template"])
            if "description_template" in data:
                cr.description_template = str(data["description_template"])

            for item in (data.get("items") or []):
                try:
                    n = int(item.get("number"))
                except Exception:
                    continue
                cr.lectures[n] = {
                    "title": str(item.get("title", "")).strip(),
                    "module": str(item.get("module", "")).strip(),
                }
            return cr

        # Schema B (earlier style)
        course = str(data.get("course_code", "")).strip()
        if not course:
            raise ValueError("Missing course/course_code")
        cr = CourseRules(course)
        cr.canvas = (data.get("canvas_url") or "").strip() or None

        def ingest(arr, dest):
            for item in (arr or []):
                try:
                    n = int(item.get("number"))
                except Exception:
                    continue
                dest[n] = {
                    "title": str(item.get("title", "")).strip(),
                    "module": str(item.get("module", "")).strip(),
                }

        ingest(data.get("lectures"), cr.lectures)
        ingest(data.get("labs"), cr.labs)
        ingest(data.get("exercises"), cr.exercises)
        return cr


def load_course_rules_dir(events_dir: Path) -> Dict[str, CourseRules]:
    rules: Dict[str, CourseRules] = {}
    if not events_dir.exists():
        safe_warn("EVENTS_DIR does not exist: %s (no rewriting will be applied).", str(events_dir))
        return rules
    for p in sorted(events_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            cr = CourseRules.from_json(data)
            rules[cr.course] = cr
        except Exception as e:
            safe_warn("Ignoring %s: %s", p.name, str(e))
    safe_log("Loaded rules for %d course(s).", len(rules))
    return rules
