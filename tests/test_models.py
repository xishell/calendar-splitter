"""Tests for core data models."""

import re
from datetime import datetime, timezone

from calendar_splitter.core.models import (
    ClassifiedEvent,
    CourseConfig,
    Detection,
    Event,
    EventItem,
    EventType,
    FeedResult,
    MatchStrategy,
    StrategyType,
    Templates,
)


class TestEvent:
    def test_basic_construction(self):
        ev = Event(
            uid="test-uid",
            summary="Lecture 1",
            description="Intro",
            location="Room A",
            start=datetime(2025, 1, 13, 13, 0, tzinfo=timezone.utc),
            end=datetime(2025, 1, 13, 15, 0, tzinfo=timezone.utc),
        )
        assert ev.uid == "test-uid"
        assert ev.summary == "Lecture 1"
        assert ev.properties == {}

    def test_with_properties(self):
        ev = Event(
            uid="u", summary="s", description="d", location="l",
            start=None, end=None,
            properties={"CATEGORIES": "test"},
        )
        assert ev.properties["CATEGORIES"] == "test"


class TestStrategyType:
    def test_values(self):
        assert StrategyType.TIME.value == "time"
        assert StrategyType.ALL.value == "all"
        assert StrategyType.ANY.value == "any"


class TestMatchStrategy:
    def test_default_priority(self):
        ms = MatchStrategy(strategy=StrategyType.TIME)
        assert ms.priority == 99
        assert ms.data == {}


class TestEventItem:
    def test_get_title(self):
        item = EventItem(number=1, title="Intro", module="Mod 1")
        assert item.get("title") == "Intro"
        assert item.get("module") == "Mod 1"

    def test_get_metadata(self):
        item = EventItem(metadata={"custom": "value"})
        assert item.get("custom") == "value"
        assert item.get("missing", "default") == "default"


class TestEventType:
    def test_construction(self):
        et = EventType(
            type="lecture",
            display_name="Lecture",
            patterns=[re.compile(r"\bLecture\s*(\d+)\b", re.IGNORECASE)],
        )
        assert et.type == "lecture"
        assert et.unnumbered is False


class TestTemplates:
    def test_defaults(self):
        t = Templates()
        assert "{kind}" in t.summary
        assert "{original}" in t.description


class TestDetection:
    def test_defaults(self):
        d = Detection()
        assert d.require_code_in_summary is False
        assert d.course_code_pattern is None


class TestCourseConfig:
    def test_minimal(self):
        cc = CourseConfig(course_code="IS1200")
        assert cc.course_code == "IS1200"
        assert cc.course_name == ""
        assert cc.event_types == []


class TestClassifiedEvent:
    def test_construction(self):
        ev = Event(uid="u", summary="s", description="d", location="l", start=None, end=None)
        ce = ClassifiedEvent(event=ev, course_code="IS1200", kind="lecture", number=1)
        assert ce.course_code == "IS1200"
        assert ce.kind == "lecture"


class TestFeedResult:
    def test_construction(self):
        fr = FeedResult(course_code="IS1200", path="/tmp/IS1200.ics", event_count=5)
        assert fr.event_count == 5
