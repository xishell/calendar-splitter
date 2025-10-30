from dataclasses import dataclass
from datetime import datetime
from typing import Any, Enum


@dataclass
class Event:
    """A single calendar event from an ICS file"""

    uid: str
    summary: str
    description: str
    start: datetime
    end: datetime
    location: str | None
    categories: list[str]

    course_code: str | None
    event_kind: str | None
    event_number: int | None


class StrategyType(Enum):
    """Types of matching strategies"""

    REGEX = "regex"
    TIME_RANGE = "time_range"
    WEEKDAY = "weekday"
    LOCATION = "location"
    CATEGORY = "category"


@dataclass
class MatchStrategy:
    type: StrategyType
    priority: int
    config: dict[str, Any]

    name: str | None


@dataclass
class CourseConfig:
    """Configuration for how to split and rewrite events for a course"""

    code: str
    name: str
    token: str
    match_strategies: list[MatchStrategy]
    default_template: str | None
