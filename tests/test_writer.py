"""Tests for ICS output generation."""

from icalendar import Calendar

from calendar_splitter.core.models import ClassifiedEvent, Event, EventType
from calendar_splitter.core.writer import build_event, clone_calendar_base


class TestCloneCalendarBase:
    def test_clones_metadata(self):
        src = Calendar()
        src.add("PRODID", "-//Test//EN")
        src.add("VERSION", "2.0")
        src.add("CALSCALE", "GREGORIAN")

        dst = clone_calendar_base(src, "IS1200")
        assert str(dst.get("PRODID")) == "-//Test//EN"
        assert str(dst.get("X-WR-CALNAME")) == "IS1200"

    def test_skips_missing_keys(self):
        src = Calendar()
        src.add("VERSION", "2.0")
        dst = clone_calendar_base(src, "TEST")
        assert dst.get("PRODID") is None
        assert str(dst.get("X-WR-CALNAME")) == "TEST"


class TestBuildEvent:
    def test_builds_with_rewritten_fields(self):
        ev = Event(
            uid="u", summary="Old", description="Old desc",
            location="Room", start=None, end=None,
            properties={"CATEGORIES": "test"},
        )
        classified = ClassifiedEvent(event=ev, course_code="TEST")
        ical_ev = build_event(classified, "New Summary", "New Desc")
        assert str(ical_ev.get("SUMMARY")) == "New Summary"
        assert str(ical_ev.get("DESCRIPTION")) == "New Desc"

    def test_passthrough_properties(self):
        ev = Event(
            uid="u", summary="S", description="D",
            location="L", start=None, end=None,
            properties={"X-CUSTOM": "value"},
        )
        classified = ClassifiedEvent(event=ev, course_code="TEST")
        ical_ev = build_event(classified, "S", "D")
        assert ical_ev.get("X-CUSTOM") is not None

    def test_empty_description(self):
        ev = Event(uid="u", summary="S", description="", location="", start=None, end=None)
        classified = ClassifiedEvent(event=ev, course_code="TEST")
        ical_ev = build_event(classified, "S", "")
        assert str(ical_ev.get("DESCRIPTION")) == ""
