"""Tests for the new flexible event system (EventType, EventItem, MatchStrategy)."""
from datetime import datetime

from scripts.rewrite import matches_item, matches_strategy
from scripts.rules import CourseRules, EventItem, EventType, MatchStrategy


# ===== MatchStrategy Tests =====


def test_match_strategy_from_dict_basic():
    """Test basic MatchStrategy.from_dict() parsing."""
    data = {"strategy": "time", "priority": 1, "timeslot": {"day": "monday"}}
    ms = MatchStrategy.from_dict(data)
    assert ms.strategy == "time"
    assert ms.priority == 1
    assert ms.data == {"timeslot": {"day": "monday"}}


def test_match_strategy_from_dict_default_priority():
    """Test MatchStrategy with default priority."""
    data = {"strategy": "description", "pattern": "Group A"}
    ms = MatchStrategy.from_dict(data)
    assert ms.strategy == "description"
    assert ms.priority == 99  # Default
    assert ms.data == {"pattern": "Group A"}


def test_match_strategy_from_dict_excludes_reserved_fields():
    """Test that strategy and priority are not included in data."""
    data = {"strategy": "location", "priority": 5, "location": "Room 101"}
    ms = MatchStrategy.from_dict(data)
    assert "strategy" not in ms.data
    assert "priority" not in ms.data
    assert ms.data == {"location": "Room 101"}


# ===== EventItem Tests =====


def test_event_item_from_dict_basic():
    """Test basic EventItem.from_dict() parsing."""
    data = {"number": 1, "title": "Introduction", "module": "Module 1"}
    item = EventItem.from_dict(data)
    assert item.number == 1
    assert item.metadata == {"title": "Introduction", "module": "Module 1"}
    assert item.match_strategies == []


def test_event_item_from_dict_with_match_priority():
    """Test EventItem with match_priority array."""
    data = {
        "number": 2,
        "title": "Advanced Topics",
        "match_priority": [
            {"strategy": "time", "priority": 1, "timeslot": {"day": "tuesday"}},
            {"strategy": "description", "priority": 2, "pattern": "Group B"},
        ],
    }
    item = EventItem.from_dict(data)
    assert item.number == 2
    assert len(item.match_strategies) == 2
    assert item.match_strategies[0].strategy == "time"
    assert item.match_strategies[1].strategy == "description"


def test_event_item_from_dict_with_single_match():
    """Test EventItem with single match field."""
    data = {
        "number": 3,
        "title": "Lab Session",
        "match": {"strategy": "location", "location": "Lab A"},
    }
    item = EventItem.from_dict(data)
    assert len(item.match_strategies) == 1
    assert item.match_strategies[0].strategy == "location"


def test_event_item_from_dict_with_legacy_timeslot():
    """Test EventItem with legacy timeslot field."""
    data = {"number": 4, "title": "Lecture", "timeslot": {"day": "wednesday"}}
    item = EventItem.from_dict(data)
    assert len(item.match_strategies) == 1
    assert item.match_strategies[0].strategy == "time"
    assert item.match_strategies[0].data == {"timeslot": {"day": "wednesday"}}


def test_event_item_from_dict_with_group_shorthand():
    """Test EventItem with group shorthand."""
    data = {"number": 5, "title": "Seminar", "group": "Group A"}
    item = EventItem.from_dict(data)
    assert len(item.match_strategies) == 1
    assert item.match_strategies[0].strategy == "description"
    assert item.match_strategies[0].data == {"pattern": "Group A"}


def test_event_item_from_dict_invalid_number():
    """Test EventItem with invalid number returns None."""
    data = {"number": "not_a_number", "title": "Test"}
    item = EventItem.from_dict(data)
    assert item.number is None


def test_event_item_get_method():
    """Test EventItem.get() method."""
    data = {"number": 1, "title": "Test", "module": "M1", "custom_field": "value"}
    item = EventItem.from_dict(data)
    assert item.get("title") == "Test"
    assert item.get("module") == "M1"
    assert item.get("custom_field") == "value"
    assert item.get("missing") == ""
    assert item.get("missing", "default") == "default"


# ===== EventType Tests =====


def test_event_type_from_dict_basic():
    """Test basic EventType.from_dict() parsing."""
    data = {
        "type": "lecture",
        "display_name": "Lecture",
        "patterns": [r"\bLecture\s*(\d+)\b"],
        "items": [{"number": 1, "title": "Intro"}],
    }
    et = EventType.from_dict(data, "IS1200")
    assert et.type == "lecture"
    assert et.display_name == "Lecture"
    assert len(et.patterns) == 1
    assert len(et.items) == 1
    assert 1 in et.items


def test_event_type_from_dict_multiple_patterns():
    """Test EventType with multiple regex patterns."""
    data = {
        "type": "seminar",
        "display_name": "Seminarium",
        "patterns": [r"Seminarium\s*(\d+)", r"Seminar\s*(\d+)"],
        "items": [],
    }
    et = EventType.from_dict(data, "IS1200")
    assert len(et.patterns) == 2


def test_event_type_from_dict_string_pattern():
    """Test EventType with single pattern as string (not array)."""
    data = {
        "type": "lab",
        "display_name": "Lab",
        "patterns": r"\bLab\s*(\d+)\b",
        "items": [],
    }
    et = EventType.from_dict(data, "IS1200")
    assert len(et.patterns) == 1


def test_event_type_from_dict_unnumbered():
    """Test EventType with unnumbered flag."""
    data = {
        "type": "guest_lecture",
        "display_name": "Guest Lecture",
        "patterns": [r"Guest Lecture"],
        "unnumbered": True,
        "items": [{"title": "Special Event"}],
    }
    et = EventType.from_dict(data, "IS1200")
    assert et.unnumbered is True
    assert None in et.items  # Unnumbered items stored with None key


def test_event_type_from_dict_invalid_pattern():
    """Test EventType with invalid regex pattern (should skip it)."""
    data = {
        "type": "test",
        "display_name": "Test",
        "patterns": [r"\bValid\s*(\d+)\b", r"[invalid(regex"],
        "items": [],
    }
    et = EventType.from_dict(data, "IS1200")
    assert len(et.patterns) == 1  # Only valid pattern kept


def test_event_type_from_dict_default_display_name():
    """Test EventType uses capitalized type as default display_name."""
    data = {"type": "workshop", "patterns": [r"Workshop"], "items": []}
    et = EventType.from_dict(data, "IS1200")
    assert et.display_name == "Workshop"


# ===== Matching Strategy Tests =====


def test_matches_strategy_time_day_only():
    """Test time-based matching with day of week."""
    strategy = MatchStrategy(
        strategy="time", data={"timeslot": {"day": "monday"}}, priority=1
    )
    # Monday is day 0
    monday_dt = datetime(2025, 11, 3, 10, 0)  # A Monday
    tuesday_dt = datetime(2025, 11, 4, 10, 0)  # A Tuesday

    assert matches_strategy(strategy, "", "", "", monday_dt) is True
    assert matches_strategy(strategy, "", "", "", tuesday_dt) is False


def test_matches_strategy_time_day_string():
    """Test time-based matching with day as string."""
    strategy = MatchStrategy(
        strategy="time", data={"timeslot": {"day": "wednesday"}}, priority=1
    )
    wednesday_dt = datetime(2025, 11, 5, 14, 0)  # A Wednesday
    thursday_dt = datetime(2025, 11, 6, 14, 0)  # A Thursday

    assert matches_strategy(strategy, "", "", "", wednesday_dt) is True
    assert matches_strategy(strategy, "", "", "", thursday_dt) is False


def test_matches_strategy_time_with_range():
    """Test time-based matching with time range."""
    strategy = MatchStrategy(
        strategy="time",
        data={"timeslot": {"day": "friday", "start_time": "13:00", "end_time": "15:00"}},
        priority=1,
    )
    friday_1pm = datetime(2025, 11, 7, 13, 0)  # Friday 13:00
    friday_2pm = datetime(2025, 11, 7, 14, 0)  # Friday 14:00
    friday_3pm = datetime(2025, 11, 7, 15, 0)  # Friday 15:00 (exclusive)
    friday_12pm = datetime(2025, 11, 7, 12, 0)  # Friday 12:00

    assert matches_strategy(strategy, "", "", "", friday_1pm) is True
    assert matches_strategy(strategy, "", "", "", friday_2pm) is True
    assert matches_strategy(strategy, "", "", "", friday_3pm) is False  # Exclusive end
    assert matches_strategy(strategy, "", "", "", friday_12pm) is False


def test_matches_strategy_time_hhmm_format():
    """Test time-based matching with HHMM format (no colon)."""
    strategy = MatchStrategy(
        strategy="time",
        data={"timeslot": {"start_time": "0800", "end_time": "1000"}},
        priority=1,
    )
    dt_8am = datetime(2025, 11, 3, 8, 0)
    dt_9am = datetime(2025, 11, 3, 9, 0)
    dt_10am = datetime(2025, 11, 3, 10, 0)

    assert matches_strategy(strategy, "", "", "", dt_8am) is True
    assert matches_strategy(strategy, "", "", "", dt_9am) is True
    assert matches_strategy(strategy, "", "", "", dt_10am) is False


def test_matches_strategy_time_no_datetime():
    """Test time-based matching returns False when no datetime provided."""
    strategy = MatchStrategy(
        strategy="time", data={"timeslot": {"day": "monday"}}, priority=1
    )
    assert matches_strategy(strategy, "", "", "", None) is False


def test_matches_strategy_time_legacy_string_timeslot():
    """Test time-based matching with legacy string timeslot (can't match)."""
    strategy = MatchStrategy(
        strategy="time", data={"timeslot": "Monday 13:00-15:00"}, priority=1
    )
    monday_dt = datetime(2025, 11, 3, 14, 0)
    assert matches_strategy(strategy, "", "", "", monday_dt) is False


def test_matches_strategy_description_pattern():
    """Test description pattern matching."""
    strategy = MatchStrategy(
        strategy="description", data={"pattern": r"Group [AB]"}, priority=1
    )
    assert matches_strategy(strategy, "Seminar (Group A)", "", "", None) is True
    assert matches_strategy(strategy, "", "Details for Group B", "", None) is True
    assert matches_strategy(strategy, "Seminar (Group C)", "", "", None) is False


def test_matches_strategy_description_case_insensitive():
    """Test description pattern matching is case-insensitive."""
    strategy = MatchStrategy(
        strategy="description", data={"pattern": r"group a"}, priority=1
    )
    assert matches_strategy(strategy, "Seminar (GROUP A)", "", "", None) is True
    assert matches_strategy(strategy, "Seminar (Group A)", "", "", None) is True


def test_matches_strategy_description_invalid_pattern():
    """Test description matching with invalid regex returns False."""
    strategy = MatchStrategy(
        strategy="description", data={"pattern": r"[invalid(regex"}, priority=1
    )
    assert matches_strategy(strategy, "Any text", "", "", None) is False


def test_matches_strategy_description_no_pattern():
    """Test description matching with missing pattern returns False."""
    strategy = MatchStrategy(strategy="description", data={}, priority=1)
    assert matches_strategy(strategy, "Any text", "", "", None) is False


def test_matches_strategy_location():
    """Test location matching."""
    strategy = MatchStrategy(strategy="location", data={"location": "Q17"}, priority=1)
    assert matches_strategy(strategy, "", "", "Room Q17", None) is True
    assert matches_strategy(strategy, "", "", "q17", None) is True  # Case insensitive
    assert matches_strategy(strategy, "", "", "Room Q18", None) is False


def test_matches_strategy_location_no_location():
    """Test location matching with missing location returns False."""
    strategy = MatchStrategy(strategy="location", data={}, priority=1)
    assert matches_strategy(strategy, "", "", "Any location", None) is False


def test_matches_strategy_url():
    """Test URL pattern matching in description."""
    strategy = MatchStrategy(
        strategy="url", data={"pattern": r"zoom\.us/j/12345"}, priority=1
    )
    desc_with_zoom = "Join at https://zoom.us/j/12345"
    desc_without_zoom = "Join at https://teams.microsoft.com/..."
    assert matches_strategy(strategy, "", desc_with_zoom, "", None) is True
    assert matches_strategy(strategy, "", desc_without_zoom, "", None) is False


def test_matches_strategy_all_composite():
    """Test 'all' composite strategy (all must match)."""
    strategy = MatchStrategy(
        strategy="all",
        data={
            "strategies": [
                {"strategy": "description", "pattern": "Group A"},
                {"strategy": "location", "location": "Q17"},
            ]
        },
        priority=1,
    )
    # Both match
    assert (
        matches_strategy(strategy, "Seminar (Group A)", "", "Room Q17", None) is True
    )
    # Only description matches
    assert (
        matches_strategy(strategy, "Seminar (Group A)", "", "Room Q18", None) is False
    )
    # Only location matches
    assert (
        matches_strategy(strategy, "Seminar (Group B)", "", "Room Q17", None) is False
    )
    # Neither matches
    assert (
        matches_strategy(strategy, "Seminar (Group B)", "", "Room Q18", None) is False
    )


def test_matches_strategy_any_composite():
    """Test 'any' composite strategy (at least one must match)."""
    strategy = MatchStrategy(
        strategy="any",
        data={
            "strategies": [
                {"strategy": "description", "pattern": "Group A"},
                {"strategy": "location", "location": "Q17"},
            ]
        },
        priority=1,
    )
    # Both match
    assert (
        matches_strategy(strategy, "Seminar (Group A)", "", "Room Q17", None) is True
    )
    # Only description matches
    assert (
        matches_strategy(strategy, "Seminar (Group A)", "", "Room Q18", None) is True
    )
    # Only location matches
    assert (
        matches_strategy(strategy, "Seminar (Group B)", "", "Room Q17", None) is True
    )
    # Neither matches
    assert (
        matches_strategy(strategy, "Seminar (Group B)", "", "Room Q18", None) is False
    )


def test_matches_strategy_unknown_strategy():
    """Test unknown strategy type returns False."""
    strategy = MatchStrategy(strategy="unknown_type", data={}, priority=1)
    assert matches_strategy(strategy, "", "", "", None) is False


# ===== matches_item Tests =====


def test_matches_item_no_strategies():
    """Test matches_item returns True when no strategies defined."""
    item = EventItem(number=1, metadata={"title": "Test"}, match_strategies=[])
    assert matches_item(item, "", "", "", None) is True


def test_matches_item_single_strategy_match():
    """Test matches_item with single strategy that matches."""
    item = EventItem(
        number=1,
        metadata={"title": "Test"},
        match_strategies=[
            MatchStrategy(strategy="description", data={"pattern": "Group A"})
        ],
    )
    assert matches_item(item, "Seminar (Group A)", "", "", None) is True
    assert matches_item(item, "Seminar (Group B)", "", "", None) is False


def test_matches_item_multiple_strategies_priority():
    """Test matches_item tries strategies in priority order."""
    # Higher priority (lower number) should be tried first
    item = EventItem(
        number=1,
        metadata={"title": "Test"},
        match_strategies=[
            MatchStrategy(
                strategy="description", data={"pattern": "Priority 2"}, priority=2
            ),
            MatchStrategy(
                strategy="description", data={"pattern": "Priority 1"}, priority=1
            ),
            MatchStrategy(
                strategy="description", data={"pattern": "Priority 3"}, priority=3
            ),
        ],
    )
    # Should match on priority 1
    assert matches_item(item, "Test Priority 1", "", "", None) is True
    # Should match on priority 2
    assert matches_item(item, "Test Priority 2", "", "", None) is True
    # Should match on priority 3
    assert matches_item(item, "Test Priority 3", "", "", None) is True
    # Should not match any
    assert matches_item(item, "No match", "", "", None) is False


def test_matches_item_stops_on_first_match():
    """Test matches_item returns True on first matching strategy."""
    item = EventItem(
        number=1,
        metadata={"title": "Test"},
        match_strategies=[
            MatchStrategy(
                strategy="description", data={"pattern": "Match"}, priority=1
            ),
            MatchStrategy(
                strategy="location", data={"location": "Q17"}, priority=2
            ),
        ],
    )
    # First strategy matches, should return True immediately
    assert matches_item(item, "Test Match", "", "Wrong Location", None) is True


# ===== Integration Tests =====


def test_course_rules_with_event_types_schema_b():
    """Test full CourseRules parsing with event_types (Schema B)."""
    data = {
        "schema_version": "B",
        "course_code": "IS1200",
        "event_types": [
            {
                "type": "lecture",
                "display_name": "Föreläsning",
                "patterns": [r"Föreläsning\s*(\d+)", r"Lecture\s*(\d+)"],
                "items": [{"number": 1, "title": "Intro", "module": "M1"}],
            },
            {
                "type": "seminar",
                "display_name": "Seminarium",
                "patterns": [r"Seminarium\s*(\d+)"],
                "items": [
                    {
                        "number": 1,
                        "title": "Discussion",
                        "module": "M2",
                        "match": {
                            "strategy": "time",
                            "timeslot": {"day": "wednesday", "start_time": "13:00"},
                        },
                    }
                ],
            },
        ],
    }
    cr = CourseRules.from_json(data)
    assert cr.course == "IS1200"
    assert len(cr.event_types) == 2
    assert cr.event_types[0].type == "lecture"
    assert cr.event_types[0].display_name == "Föreläsning"
    assert cr.event_types[1].type == "seminar"
    assert 1 in cr.event_types[0].items
    assert 1 in cr.event_types[1].items
    assert len(cr.event_types[1].items[1].match_strategies) == 1


def test_course_rules_legacy_auto_migration_schema_a():
    """Test automatic migration from legacy Schema A to event_types."""
    data = {
        "schema_version": "A",
        "course": "IS1200",
        "items": [
            {"number": 1, "title": "Intro", "module": "M1"},
            {"number": 2, "title": "Advanced", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    # Should auto-create event_types from legacy items
    assert len(cr.event_types) == 1
    assert cr.event_types[0].type == "lecture"
    assert cr.event_types[0].display_name == "Lecture"
    assert 1 in cr.event_types[0].items
    assert 2 in cr.event_types[0].items
    assert cr.event_types[0].items[1].get("title") == "Intro"


def test_course_rules_legacy_auto_migration_schema_b():
    """Test automatic migration from legacy Schema B to event_types."""
    data = {
        "schema_version": "B",
        "course_code": "IS1200",
        "lectures": [{"number": 1, "title": "L1", "module": "M1"}],
        "labs": [{"number": 1, "title": "Lab1", "module": "M1"}],
        "exercises": [{"number": 1, "title": "Ex1", "module": "M1"}],
    }
    cr = CourseRules.from_json(data)
    # Should auto-create 3 event_types
    assert len(cr.event_types) == 3
    types = {et.type for et in cr.event_types}
    assert types == {"lecture", "lab", "exercise"}


def test_course_rules_event_types_overrides_legacy():
    """Test that event_types takes precedence over legacy fields."""
    data = {
        "schema_version": "B",
        "course_code": "IS1200",
        "lectures": [{"number": 1, "title": "Legacy", "module": "M1"}],
        "event_types": [
            {
                "type": "lecture",
                "display_name": "Modern",
                "patterns": [r"Lecture\s*(\d+)"],
                "items": [{"number": 1, "title": "New", "module": "M1"}],
            }
        ],
    }
    cr = CourseRules.from_json(data)
    # Should use event_types, not legacy
    assert len(cr.event_types) == 1
    assert cr.event_types[0].display_name == "Modern"
    assert cr.event_types[0].items[1].get("title") == "New"
