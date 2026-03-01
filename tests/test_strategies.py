"""Tests for strategy evaluation and event classification."""

import re
from datetime import datetime, timezone

from calendar_splitter.config import load_course_config
from calendar_splitter.core.models import (
    CourseConfig,
    Detection,
    Event,
    EventItem,
    EventType,
    MatchStrategy,
    StrategyType,
    Templates,
)
from calendar_splitter.strategies import classify_event, evaluate_item, evaluate_strategy


def _make_event(**kwargs):
    defaults = {
        "uid": "test", "summary": "", "description": "", "location": "",
        "start": None, "end": None,
    }
    defaults.update(kwargs)
    return Event(**defaults)


class TestEvaluateStrategyTime:
    def test_matching_day(self):
        s = MatchStrategy(strategy=StrategyType.TIME, data={"day": "monday"})
        dt = datetime(2025, 1, 13, 13, 0, tzinfo=timezone.utc)  # Monday
        assert evaluate_strategy(s, "", "", "", dt) is True

    def test_wrong_day(self):
        s = MatchStrategy(strategy=StrategyType.TIME, data={"day": "tuesday"})
        dt = datetime(2025, 1, 13, 13, 0, tzinfo=timezone.utc)  # Monday
        assert evaluate_strategy(s, "", "", "", dt) is False

    def test_time_range(self):
        s = MatchStrategy(
            strategy=StrategyType.TIME,
            data={"start_time": "13:00", "end_time": "15:00", "timezone": "UTC"},
        )
        dt = datetime(2025, 1, 13, 13, 30, tzinfo=timezone.utc)
        assert evaluate_strategy(s, "", "", "", dt) is True

    def test_outside_time_range(self):
        s = MatchStrategy(
            strategy=StrategyType.TIME,
            data={"start_time": "13:00", "end_time": "15:00", "timezone": "UTC"},
        )
        dt = datetime(2025, 1, 13, 16, 0, tzinfo=timezone.utc)
        assert evaluate_strategy(s, "", "", "", dt) is False

    def test_no_datetime_returns_false(self):
        s = MatchStrategy(strategy=StrategyType.TIME, data={"day": "monday"})
        assert evaluate_strategy(s, "", "", "", None) is False


class TestEvaluateStrategyDescription:
    def test_matches_pattern(self):
        s = MatchStrategy(strategy=StrategyType.DESCRIPTION, data={"pattern": r"Group\s+A"})
        assert evaluate_strategy(s, "Event", "Group A students", "", None) is True

    def test_no_match(self):
        s = MatchStrategy(strategy=StrategyType.DESCRIPTION, data={"pattern": r"Group\s+B"})
        assert evaluate_strategy(s, "Event", "Group A students", "", None) is False


class TestEvaluateStrategyLocation:
    def test_matches(self):
        s = MatchStrategy(strategy=StrategyType.LOCATION, data={"location": "Room Q1"})
        assert evaluate_strategy(s, "", "", "Room Q1", None) is True

    def test_case_insensitive(self):
        s = MatchStrategy(strategy=StrategyType.LOCATION, data={"location": "room q1"})
        assert evaluate_strategy(s, "", "", "Room Q1", None) is True


class TestEvaluateStrategyURL:
    def test_matches(self):
        s = MatchStrategy(strategy=StrategyType.URL, data={"pattern": r"canvas\.kth\.se"})
        assert evaluate_strategy(s, "", "https://canvas.kth.se/course/123", "", None) is True


class TestEvaluateStrategyComposite:
    def test_all_requires_all(self):
        s = MatchStrategy(
            strategy=StrategyType.ALL,
            data={"strategies": [
                {"strategy": "description", "pattern": r"Group A"},
                {"strategy": "location", "location": "Room Q1"},
            ]},
        )
        assert evaluate_strategy(s, "Event", "Group A", "Room Q1", None) is True
        assert evaluate_strategy(s, "Event", "Group A", "Room Q2", None) is False

    def test_any_requires_one(self):
        s = MatchStrategy(
            strategy=StrategyType.ANY,
            data={"strategies": [
                {"strategy": "location", "location": "Room Q1"},
                {"strategy": "location", "location": "Room Q2"},
            ]},
        )
        assert evaluate_strategy(s, "", "", "Room Q2", None) is True
        assert evaluate_strategy(s, "", "", "Room Q3", None) is False


class TestEvaluateItem:
    def test_no_strategies_matches(self):
        item = EventItem(number=1, title="Intro")
        assert evaluate_item(item, "", "", "", None) is True

    def test_with_matching_strategy(self):
        item = EventItem(
            number=1,
            match=[MatchStrategy(strategy=StrategyType.LOCATION, data={"location": "Q1"})],
        )
        assert evaluate_item(item, "", "", "Room Q1", None) is True
        assert evaluate_item(item, "", "", "Room Q2", None) is False


class TestClassifyEvent:
    def test_classifies_lecture(self, sample_course_config_dict):
        config = load_course_config(sample_course_config_dict)
        ev = _make_event(summary="Lecture 1 (IS1200) Introduction")
        result = classify_event(ev, "IS1200", config)
        assert result is not None
        assert result.kind == "lecture"
        assert result.number == 1

    def test_filters_missing_course_code(self, sample_course_config_dict):
        config = load_course_config(sample_course_config_dict)
        ev = _make_event(summary="Lecture 1 Introduction")
        result = classify_event(ev, "IS1200", config)
        assert result is None  # require_code_in_summary is True

    def test_no_event_types_match(self):
        config = CourseConfig(course_code="TEST")
        ev = _make_event(summary="Random event (TEST)")
        result = classify_event(ev, "TEST", config)
        assert result is not None
        assert result.kind is None

    def test_unnumbered_event_type(self):
        config = CourseConfig(
            course_code="TEST",
            event_types=[EventType(
                type="seminar",
                display_name="Seminar",
                patterns=[re.compile(r"\bSeminar\b", re.IGNORECASE)],
                unnumbered=True,
            )],
        )
        ev = _make_event(summary="Seminar (TEST)")
        result = classify_event(ev, "TEST", config)
        assert result is not None
        assert result.kind == "seminar"
        assert result.number is None
