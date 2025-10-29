from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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
class MatchStrategy:
    """Defines how to match/filter events for a specific item."""
    strategy: str  # "time", "description", "location", "url", "all", "any", etc.
    data: Dict[str, Any] = field(default_factory=dict)  # Strategy-specific data
    priority: int = 99  # Lower = higher priority

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "MatchStrategy":
        """Create MatchStrategy from dict."""
        strategy = data.get("strategy", "")
        priority = data.get("priority", 99)
        # Copy all data except 'strategy' and 'priority'
        strategy_data = {k: v for k, v in data.items() if k not in ("strategy", "priority")}
        return MatchStrategy(strategy=strategy, data=strategy_data, priority=priority)


@dataclass
class EventItem:
    """Represents a single event occurrence with metadata and optional matching rules."""
    number: Optional[int] = None  # Event number (or None for unnumbered)
    metadata: Dict[str, Any] = field(default_factory=dict)  # All custom fields (title, module, etc.)
    match_strategies: List[MatchStrategy] = field(default_factory=list)  # How to identify this event

    def get(self, key: str, default: Any = "") -> Any:
        """Get metadata value with default."""
        return self.metadata.get(key, default)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "EventItem":
        """Create EventItem from dict."""
        number = data.get("number")
        if number is not None:
            try:
                number = int(number)
            except (ValueError, TypeError):
                number = None

        # Extract match strategies
        strategies = []

        # Check for match_priority array
        if "match_priority" in data:
            for match_def in data["match_priority"]:
                strategies.append(MatchStrategy.from_dict(match_def))
        # Check for single match definition
        elif "match" in data:
            strategies.append(MatchStrategy.from_dict(data["match"]))
        # Check for legacy timeslot field
        elif "timeslot" in data:
            strategies.append(MatchStrategy(
                strategy="time",
                data={"timeslot": data["timeslot"]}
            ))
        # Check for group shorthand
        elif "group" in data:
            strategies.append(MatchStrategy(
                strategy="description",
                data={"pattern": data["group"]}
            ))

        # All other fields go into metadata
        metadata = {k: v for k, v in data.items()
                   if k not in ("number", "match", "match_priority", "timeslot", "group")}

        return EventItem(number=number, metadata=metadata, match_strategies=strategies)


@dataclass
class EventType:
    """Defines a configurable event type (lecture, lab, seminar, etc.)."""
    type: str  # Internal type identifier ("lecture", "seminar", etc.)
    display_name: str  # Display name ("Lecture", "Seminar", etc.)
    patterns: List[re.Pattern]  # Regex patterns to match this event type
    items: Dict[Optional[int], EventItem] = field(default_factory=dict)  # Number -> EventItem
    unnumbered: bool = False  # True if events don't have numbers

    @staticmethod
    def from_dict(data: Dict[str, Any], course: str) -> "EventType":
        """Create EventType from dict."""
        type_name = data.get("type", "unknown")
        display_name = data.get("display_name", type_name.capitalize())
        unnumbered = data.get("unnumbered", False)

        # Compile patterns
        patterns = []
        pattern_list = data.get("patterns", [])
        if isinstance(pattern_list, str):
            pattern_list = [pattern_list]

        for pattern_str in pattern_list:
            try:
                patterns.append(re.compile(pattern_str, re.IGNORECASE))
            except re.error as e:
                safe_warn("Course %s: Invalid pattern '%s' in event type '%s': %s",
                         course, pattern_str, type_name, e)

        # Parse items
        items = {}
        for item_data in data.get("items", []):
            item = EventItem.from_dict(item_data)
            items[item.number] = item

        return EventType(
            type=type_name,
            display_name=display_name,
            patterns=patterns,
            items=items,
            unnumbered=unnumbered
        )


def validate_template(template: str, allowed_vars: set[str], template_name: str, course: str) -> bool:
    """Validate that template only uses allowed variables.

    Returns True if valid, False if invalid (with warning logged).
    """
    try:
        # Extract all variables from the template
        formatter = string.Formatter()
        parsed = formatter.parse(template)
        used_vars = {field_name for _, field_name, _, _ in parsed if field_name}

        invalid_vars = used_vars - allowed_vars
        if invalid_vars:
            safe_warn(
                "Course %s: %s uses invalid variables: %s (allowed: %s)",
                course,
                template_name,
                sorted(invalid_vars),
                sorted(allowed_vars)
            )
            return False
        return True
    except Exception as e:
        safe_warn("Course %s: %s has syntax error: %s", course, template_name, e)
        return False


@dataclass
class CourseRules:
    course: str
    canvas: Optional[str] = None
    require_course_in_summary: bool = False
    summary_regex: Optional[re.Pattern] = None
    title_template: str = "{kind} {n} - {title} - {course}"
    description_template: str = "{module}\nCanvas: {canvas}\n\n{old_desc}"
    # New: Flexible event types system
    event_types: List[EventType] = field(default_factory=list)
    # Legacy: Keep for backward compatibility
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
                tpl = str(data["title_template"])
                allowed = {"kind", "n", "title", "course"}
                if validate_template(tpl, allowed, "title_template", course):
                    cr.title_template = tpl
                else:
                    safe_warn("Course %s: reverting to default title_template", course)

            if "description_template" in data:
                tpl = str(data["description_template"])
                allowed = {"module", "canvas", "old_desc"}
                if validate_template(tpl, allowed, "description_template", course):
                    cr.description_template = tpl
                else:
                    safe_warn("Course %s: reverting to default description_template", course)

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

            # Parse event_types (Schema A)
            if "event_types" in data:
                for event_type_data in data["event_types"]:
                    if not isinstance(event_type_data, dict):
                        safe_warn("Course %s: event_types contains non-dict, skipping", course)
                        continue
                    try:
                        event_type = EventType.from_dict(event_type_data, course)
                        cr.event_types.append(event_type)
                    except Exception as e:
                        safe_warn("Course %s: failed to parse event_type: %s", course, e)
            else:
                # Automatic migration: Convert legacy lectures to EventType
                if cr.lectures:
                    items: Dict[Optional[int], EventItem] = {}
                    for num, info in cr.lectures.items():
                        items[num] = EventItem(
                            number=num,
                            metadata={"title": info.get("title", ""), "module": info.get("module", "")},
                            match_strategies=[]
                        )
                    lecture_type = EventType(
                        type="lecture",
                        display_name="Lecture",
                        patterns=[DEFAULT_SUMMARY_RE],
                        items=items,
                        unnumbered=False
                    )
                    cr.event_types.append(lecture_type)

            return cr
        else:
            course = str(data.get("course_code", "")).strip()
            if not course:
                raise ValueError("Missing course_code")
            cr = CourseRules(course)
            cr.canvas = (data.get("canvas_url") or "").strip() or None

            # Schema B now supports same customization as Schema A
            match = data.get("match") or {}
            cr.require_course_in_summary = bool(
                match.get("require_course_in_summary", False)
            )
            srx = match.get("summary_regex")
            if srx:
                try:
                    cr.summary_regex = re.compile(srx, re.IGNORECASE)
                except re.error:
                    safe_warn("Course %s: invalid summary_regex, using default", course)
                    cr.summary_regex = DEFAULT_SUMMARY_RE

            if "title_template" in data:
                tpl = str(data["title_template"])
                allowed = {"kind", "n", "title", "course"}
                if validate_template(tpl, allowed, "title_template", course):
                    cr.title_template = tpl
                else:
                    safe_warn("Course %s: reverting to default title_template", course)

            if "description_template" in data:
                tpl = str(data["description_template"])
                allowed = {"module", "canvas", "old_desc"}
                if validate_template(tpl, allowed, "description_template", course):
                    cr.description_template = tpl
                else:
                    safe_warn("Course %s: reverting to default description_template", course)

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

            # Parse event_types (Schema B)
            if "event_types" in data:
                for event_type_data in data["event_types"]:
                    if not isinstance(event_type_data, dict):
                        safe_warn("Course %s: event_types contains non-dict, skipping", course)
                        continue
                    try:
                        event_type = EventType.from_dict(event_type_data, course)
                        cr.event_types.append(event_type)
                    except Exception as e:
                        safe_warn("Course %s: failed to parse event_type: %s", course, e)
            else:
                # Automatic migration: Convert legacy fields to EventType objects
                if cr.lectures:
                    items_lec: Dict[Optional[int], EventItem] = {}
                    for num, info in cr.lectures.items():
                        items_lec[num] = EventItem(
                            number=num,
                            metadata={"title": info.get("title", ""), "module": info.get("module", "")},
                            match_strategies=[]
                        )
                    lecture_type = EventType(
                        type="lecture",
                        display_name="Lecture",
                        patterns=[DEFAULT_SUMMARY_RE],
                        items=items_lec,
                        unnumbered=False
                    )
                    cr.event_types.append(lecture_type)

                if cr.labs:
                    items_lab: Dict[Optional[int], EventItem] = {}
                    for num, info in cr.labs.items():
                        items_lab[num] = EventItem(
                            number=num,
                            metadata={"title": info.get("title", ""), "module": info.get("module", "")},
                            match_strategies=[]
                        )
                    from .rewrite import RE_LAB
                    lab_type = EventType(
                        type="lab",
                        display_name="Lab",
                        patterns=[RE_LAB],
                        items=items_lab,
                        unnumbered=False
                    )
                    cr.event_types.append(lab_type)

                if cr.exercises:
                    items_ex: Dict[Optional[int], EventItem] = {}
                    for num, info in cr.exercises.items():
                        items_ex[num] = EventItem(
                            number=num,
                            metadata={"title": info.get("title", ""), "module": info.get("module", "")},
                            match_strategies=[]
                        )
                    from .rewrite import RE_EXERCISE
                    exercise_type = EventType(
                        type="exercise",
                        display_name="Exercise",
                        patterns=[RE_EXERCISE],
                        items=items_ex,
                        unnumbered=False
                    )
                    cr.event_types.append(exercise_type)

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
