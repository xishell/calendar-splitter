"""Tests for ICS output generation."""

from datetime import UTC, datetime

from icalendar import Calendar

from calendar_splitter.core.models import ClassifiedEvent, Event
from calendar_splitter.core.writer import build_event, clone_calendar_base, new_calendar


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


class TestGeneratedCalendar:
    def test_no_colour_properties_when_unset(self):
        ical = new_calendar("Plain").to_ical().decode()
        assert "X-APPLE-CALENDAR-COLOR" not in ical

    def test_colour_written_for_both_client_families(self):
        ical = new_calendar("Study", color="#444a95").to_ical().decode()
        assert "X-APPLE-CALENDAR-COLOR:#444a95" in ical
        assert "X-OUTLOOK-COLOR:#444a95" in ical


class TestAllDayRoundTrip:
    def _ical(self, *, all_day):
        ev = Event(uid="u", summary="S", description="", location="",
                   start=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
                   end=datetime(2026, 9, 11, 0, 0, tzinfo=UTC), all_day=all_day)
        built = build_event(ClassifiedEvent(event=ev, course_code="IS1200"), "S", "")
        return built.to_ical().decode()

    def test_all_day_is_written_as_value_date(self):
        out = self._ical(all_day=True)
        assert "DTSTART;VALUE=DATE:20260910" in out
        assert "DTEND;VALUE=DATE:20260911" in out

    def test_timed_event_keeps_its_time(self):
        out = self._ical(all_day=False)
        assert "VALUE=DATE" not in out
        assert "20260910T000000" in out
