"""Course configuration loading and validation."""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Any

from calendar_splitter.core.models import (
    CourseConfig,
    Detection,
    EventItem,
    EventType,
    MatchStrategy,
    StrategyType,
    Templates,
)
from calendar_splitter.exceptions import ConfigError
from calendar_splitter.logging import get_logger, redact

_log = get_logger(__name__)

_SUMMARY_VARS = {"kind", "n", "title", "course"}
_DESCRIPTION_VARS = {"module", "canvas", "original"}


def _validate_template(
    template: str, allowed: set[str], name: str, course: str
) -> None:
    """Validate template variables, raising ConfigError on invalid ones."""
    try:
        formatter = string.Formatter()
        used = {field_name for _, field_name, _, _ in formatter.parse(template) if field_name}
    except (ValueError, KeyError) as exc:
        msg = f"Course {course}: {name} has syntax error: {exc}"
        raise ConfigError(msg) from exc

    invalid = used - allowed
    if invalid:
        msg = (
            f"Course {course}: {name} uses invalid variables: "
            f"{sorted(invalid)} (allowed: {sorted(allowed)})"
        )
        raise ConfigError(msg)


def _parse_strategy(data: dict[str, Any]) -> MatchStrategy:
    """Parse a single match strategy dict."""
    raw_type = data.get("strategy", "")
    try:
        strategy_type = StrategyType(raw_type)
    except ValueError as exc:
        msg = f"Unknown strategy type: {raw_type}"
        raise ConfigError(msg) from exc

    priority = int(data.get("priority", 99))
    strategy_data = {k: v for k, v in data.items() if k not in ("strategy", "priority")}
    return MatchStrategy(strategy=strategy_type, priority=priority, data=strategy_data)


def _parse_item(data: dict[str, Any]) -> EventItem:
    """Parse a single event item dict."""
    number = data.get("number")
    if number is not None:
        try:
            number = int(number)
        except (ValueError, TypeError) as exc:
            msg = f"Invalid item number: {data.get('number')}"
            raise ConfigError(msg) from exc

    strategies = []
    match_data = data.get("match", [])
    if isinstance(match_data, dict):
        match_data = [match_data]
    for m in match_data:
        strategies.append(_parse_strategy(m))

    metadata = {
        k: v for k, v in data.items() if k not in ("number", "title", "module", "match")
    }

    return EventItem(
        number=number,
        title=str(data.get("title", "")),
        module=str(data.get("module", "")),
        metadata=metadata,
        match=strategies,
    )


def _parse_event_type(data: dict[str, Any], course: str) -> EventType:
    """Parse a single event type dict."""
    type_name = data.get("type", "unknown")
    display_name = data.get("display_name", type_name.capitalize())
    unnumbered = bool(data.get("unnumbered", False))

    patterns: list[re.Pattern[str]] = []
    raw_patterns = data.get("patterns", [])
    if isinstance(raw_patterns, str):
        raw_patterns = [raw_patterns]
    for p in raw_patterns:
        try:
            patterns.append(re.compile(p, re.IGNORECASE))
        except re.error as exc:
            msg = f"Course {course}: invalid pattern '{p}' in event type '{type_name}': {exc}"
            raise ConfigError(msg) from exc

    items: dict[int | None, EventItem] = {}
    for item_data in data.get("items", []):
        item = _parse_item(item_data)
        items[item.number] = item

    return EventType(
        type=type_name,
        display_name=display_name,
        patterns=patterns,
        unnumbered=unnumbered,
        items=items,
    )


def load_course_config(data: dict[str, Any]) -> CourseConfig:
    """Parse a course config dict into a CourseConfig dataclass."""
    course_code = str(data.get("course_code", "")).strip()
    if not course_code:
        msg = "Missing required field: course_code"
        raise ConfigError(msg)

    course_name = str(data.get("course_name", "")).strip()
    canvas_url = str(data.get("canvas_url", "")).strip()

    # Detection
    det_data = data.get("detection", {})
    detection_pattern = None
    raw_pattern = det_data.get("course_code_pattern")
    if raw_pattern:
        try:
            detection_pattern = re.compile(raw_pattern, re.IGNORECASE)
        except re.error as exc:
            msg = f"Course {course_code}: invalid course_code_pattern: {exc}"
            raise ConfigError(msg) from exc

    detection = Detection(
        require_code_in_summary=bool(det_data.get("require_code_in_summary", False)),
        course_code_pattern=detection_pattern,
    )

    # Templates
    tpl_data = data.get("templates", {})
    summary_tpl = str(tpl_data.get("summary", Templates.summary))
    desc_tpl = str(tpl_data.get("description", Templates.description))

    _validate_template(summary_tpl, _SUMMARY_VARS, "summary template", course_code)
    _validate_template(desc_tpl, _DESCRIPTION_VARS, "description template", course_code)

    templates = Templates(summary=summary_tpl, description=desc_tpl)

    # Event types
    event_types = []
    for et_data in data.get("event_types", []):
        event_types.append(_parse_event_type(et_data, course_code))

    return CourseConfig(
        course_code=course_code,
        course_name=course_name,
        canvas_url=canvas_url,
        detection=detection,
        templates=templates,
        event_types=event_types,
    )


def load_courses_from_dir(courses_dir: Path) -> dict[str, CourseConfig]:
    """Load all course configs from a directory of JSON files."""
    configs: dict[str, CourseConfig] = {}
    if not courses_dir.exists():
        _log.warning("Courses directory does not exist: %s", redact(str(courses_dir)))
        return configs

    for path in sorted(courses_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            config = load_course_config(raw)
            configs[config.course_code] = config
        except (json.JSONDecodeError, ConfigError) as exc:
            _log.warning("Ignoring %s: %s", path.name, exc)

    _log.info("Loaded configs for %d course(s).", len(configs))
    return configs
