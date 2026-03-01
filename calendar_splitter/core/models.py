"""Core data models for calendar-splitter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class StrategyType(Enum):
    """Types of matching strategies."""

    TIME = "time"
    DESCRIPTION = "description"
    LOCATION = "location"
    URL = "url"
    ALL = "all"
    ANY = "any"


@dataclass
class MatchStrategy:
    """A single matching strategy for identifying events."""

    strategy: StrategyType
    priority: int = 99
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class EventItem:
    """A single event occurrence with metadata and optional matching rules."""

    number: int | None = None
    title: str = ""
    module: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    match: list[MatchStrategy] = field(default_factory=list)

    def get(self, key: str, default: str = "") -> str:
        """Get a metadata value, falling back to dataclass fields."""
        if key == "title":
            return self.title or default
        if key == "module":
            return self.module or default
        return str(self.metadata.get(key, default))


@dataclass
class EventType:
    """Defines a configurable event type (lecture, lab, seminar, etc.)."""

    type: str
    display_name: str
    patterns: list[re.Pattern[str]] = field(default_factory=list)
    unnumbered: bool = False
    items: dict[int | None, EventItem] = field(default_factory=dict)


@dataclass
class Templates:
    """Summary and description templates for event rewriting."""

    summary: str = "{kind} {n} - {title} - {course}"
    description: str = "{module}\nCanvas: {canvas}\n\n{original}"


@dataclass
class Detection:
    """Course detection settings."""

    require_code_in_summary: bool = False
    course_code_pattern: re.Pattern[str] | None = None


@dataclass
class CourseConfig:
    """Full configuration for a single course."""

    course_code: str
    course_name: str = ""
    canvas_url: str = ""
    detection: Detection = field(default_factory=Detection)
    templates: Templates = field(default_factory=Templates)
    event_types: list[EventType] = field(default_factory=list)


@dataclass
class Event:
    """A raw calendar event parsed from ICS."""

    uid: str
    summary: str
    description: str
    location: str
    start: datetime | None
    end: datetime | None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassifiedEvent:
    """An event that has been matched to a course and event type."""

    event: Event
    course_code: str
    event_type: EventType | None = None
    item: EventItem | None = None
    kind: str | None = None
    number: int | None = None


@dataclass
class FeedResult:
    """Result of writing a single course feed."""

    course_code: str
    path: str
    event_count: int
