from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .log_sanitize import safe_log, safe_warn

DEFAULT_SUMMARY_RE = re.compile(r"\bLecture\s*(\d+)\b", re.IGNORECASE)


def detect_schema(data: dict[str, Any]) -> str:
    """Detect which schema version is used. Returns 'A' or 'B'."""
    if "schema_version" in data:
        version = data["schema_version"]
        if version in ("A", "a", "1"):
            return "A"
        elif version in ("B", "b", "2"):
            return "B"
        else:
            safe_warn("Unknown schema_version '%s', attempting auto-detect", version)
    has_course = "course" in data
    has_course_code = "course_code" in data
    has_items = "items" in data
    has_lectures = "lectures" in data or "labs" in data or "exercises" in data
    if has_course and not has_course_code:
        return "A"
    elif has_course_code and not has_course:
        return "B"
    elif has_course and has_course_code:
        safe_warn("Found both 'course' and 'course_code', treating as Schema A")
        return "A"
    else:
        raise ValueError("Cannot determine schema: missing 'course' or 'course_code'")


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
        schema = detect_schema(data)
        # Schema A
        if schema == "A":
            course = str(data["course"]).strip()
            cr = CourseRules(course)
            cr.canvas = (data.get("canvas") or "").strip() or None

            match = data.get("match") or {}
            cr.require_course_in_summary = bool(
                match.get("require_course_in_summary", False)
            )
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

            for idx, item in enumerate(data.get("items") or []):
                if not isinstance(item, dict):
                    safe_warn(
                        "Course %s: items[%d] is not a dict, skipping", course, idx
                    )
                    continue
                try:
                    n = int(item.get("number"))  # type: ignore[arg-type]
                except (ValueError, TypeError):
                    safe_warn(
                        "Course %s: items[%d] has invalid 'number' field (%s), skipping",
                        course,
                        idx,
                        item.get("number"),
                    )
                    continue
                if n <= 0:
                    safe_warn(
                        "Course %s: items[%d] has non-positive number (%d), skipping",
                        course,
                        idx,
                        n,
                    )
                    continue
                if n in cr.lectures:
                    safe_warn(
                        "Course %s: duplicate number %d found, overwriting", course, n
                    )

                cr.lectures[n] = {
                    "title": str(item.get("title", "")).strip(),
                    "module": str(item.get("module", "")).strip(),
                }
            return cr
        else:
            course = str(data.get("course_code", "")).strip()
            if not course:
                raise ValueError("Missing course_code")
            cr = CourseRules(course)
            cr.canvas = (data.get("canvas_url") or "").strip() or None

            def ingest(arr: Optional[list], dest: Dict[int, Dict[str, str]]) -> None:
                for idx, item in enumerate(arr or []):
                    if not isinstance(item, dict):
                        safe_warn(
                            "Course %s: items[%d] is not a dict, skipping", course, idx
                        )
                        continue

                    try:
                        n = int(item.get("number"))  # type: ignore[arg-type]
                    except (ValueError, TypeError):
                        safe_warn(
                            "Course %s: items[%d] has invalid 'number' field (%s), skipping",
                            course,
                            idx,
                            item.get("number"),
                        )
                        continue
                    if n <= 0:
                        safe_warn(
                            "Course %s: items[%d] has non-positive number (%d), skipping",
                            course,
                            idx,
                            n,
                        )
                        continue
                    if n in dest:
                        safe_warn(
                            "Course %s: duplicate number %d found, overwriting",
                            course,
                            n,
                        )

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
        safe_warn(
            "EVENTS_DIR does not exist: %s (no rewriting will be applied).",
            str(events_dir),
        )
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
