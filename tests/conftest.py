"""Shared test fixtures."""

import json
import textwrap
from pathlib import Path

import pytest


SAMPLE_ICS = textwrap.dedent("""\
    BEGIN:VCALENDAR
    PRODID:-//Test//Test//EN
    VERSION:2.0
    CALSCALE:GREGORIAN
    BEGIN:VEVENT
    UID:event-1@test
    SUMMARY:Lecture 1 (IS1200) Introduction
    DESCRIPTION:Course page: https://canvas.kth.se/courses/56261
    DTSTART:20250113T130000Z
    DTEND:20250113T150000Z
    LOCATION:Room Q1
    END:VEVENT
    BEGIN:VEVENT
    UID:event-2@test
    SUMMARY:Lecture 2 (IS1200) Assembly
    DESCRIPTION:See course page
    DTSTART:20250115T130000Z
    DTEND:20250115T150000Z
    LOCATION:Room Q1
    END:VEVENT
    BEGIN:VEVENT
    UID:event-3@test
    SUMMARY:Lab 1 (IS1200) C programming
    DESCRIPTION:Lab instructions on Canvas
    DTSTART:20250116T100000Z
    DTEND:20250116T120000Z
    LOCATION:Lab room
    END:VEVENT
    BEGIN:VEVENT
    UID:event-4@test
    SUMMARY:Meeting with supervisor
    DESCRIPTION:Personal meeting
    DTSTART:20250117T090000Z
    DTEND:20250117T100000Z
    END:VEVENT
    END:VCALENDAR
""")

SAMPLE_ICS_BYTES = SAMPLE_ICS.encode("utf-8")


SAMPLE_COURSE_CONFIG = {
    "course_code": "IS1200",
    "course_name": "Computer Hardware Engineering",
    "canvas_url": "https://canvas.kth.se/courses/56261",
    "detection": {
        "require_code_in_summary": True,
        "course_code_pattern": "\\bIS1200\\b",
    },
    "templates": {
        "summary": "{kind} {n} - {title} - {course}",
        "description": "{module}\nCanvas: {canvas}\n\n{original}",
    },
    "event_types": [
        {
            "type": "lecture",
            "display_name": "Lecture",
            "patterns": ["\\bLecture\\s*(\\d+)\\b"],
            "unnumbered": False,
            "items": [
                {
                    "number": 1,
                    "title": "Course Introduction",
                    "module": "Module 1",
                },
                {
                    "number": 2,
                    "title": "Assembly Language",
                    "module": "Module 2",
                },
            ],
        },
        {
            "type": "lab",
            "display_name": "Lab",
            "patterns": ["\\bLab\\s*(\\d+)\\b"],
            "unnumbered": False,
            "items": [
                {
                    "number": 1,
                    "title": "C Programming",
                    "module": "Module 1",
                },
            ],
        },
    ],
}


@pytest.fixture
def sample_ics_bytes():
    return SAMPLE_ICS_BYTES


@pytest.fixture
def sample_course_config_dict():
    return SAMPLE_COURSE_CONFIG.copy()


@pytest.fixture
def tmp_courses_dir(tmp_path, sample_course_config_dict):
    courses_dir = tmp_path / "courses"
    courses_dir.mkdir()
    config_path = courses_dir / "IS1200.json"
    config_path.write_text(json.dumps(sample_course_config_dict), encoding="utf-8")
    return courses_dir


@pytest.fixture
def tmp_feeds_dir(tmp_path):
    feeds_dir = tmp_path / "feeds"
    feeds_dir.mkdir()
    return feeds_dir
