"""Tests for ICS parsing and course code detection."""

import pytest

from calendar_splitter.core.parser import detect_course_code, parse_calendar
from calendar_splitter.exceptions import ParseError


class TestDetectCourseCode:
    def test_kth_style_in_summary(self):
        assert detect_course_code("Lecture 1 IS1200 Intro", "") == "IS1200"

    def test_parens_style(self):
        assert detect_course_code("Lecture 1 (IS1200HT)", "") == "IS1200HT"

    def test_url_in_description(self):
        assert detect_course_code("Lecture", "/course/DD1351/page") == "DD1351"

    def test_no_match(self):
        assert detect_course_code("Meeting", "personal") is None

    def test_ignores_year_in_parens(self):
        assert detect_course_code("Meeting (2024)", "") is None

    def test_ignores_html_in_parens(self):
        assert detect_course_code("Meeting (HTML)", "") is None

    def test_kth_priority_over_parens(self):
        assert detect_course_code("IS1200 (DD1351)", "") == "IS1200"


class TestParseCalendar:
    def test_parses_events(self, sample_ics_bytes):
        events = parse_calendar(sample_ics_bytes)
        assert len(events) == 4

    def test_event_fields(self, sample_ics_bytes):
        events = parse_calendar(sample_ics_bytes)
        ev = events[0]
        assert "Lecture 1" in ev.summary
        assert ev.uid == "event-1@test"
        assert ev.location == "Room Q1"
        assert ev.start is not None

    def test_event_without_location(self, sample_ics_bytes):
        events = parse_calendar(sample_ics_bytes)
        meeting = events[3]
        assert meeting.location == ""

    def test_invalid_ics_raises(self):
        with pytest.raises(ParseError):
            parse_calendar(b"not valid ics data at all")

    def test_empty_calendar(self):
        ics = b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"
        events = parse_calendar(ics)
        assert events == []

    def test_properties_passthrough(self, sample_ics_bytes):
        events = parse_calendar(sample_ics_bytes)
        # DTSTART/DTEND/UID/SUMMARY/DESCRIPTION/LOCATION are extracted,
        # everything else goes into properties
        ev = events[0]
        assert "SUMMARY" not in ev.properties
        assert "DESCRIPTION" not in ev.properties
