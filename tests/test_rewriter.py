"""Tests for template-based event rewriting."""

from calendar_splitter.config import load_course_config
from calendar_splitter.core.models import (
    ClassifiedEvent,
    CourseConfig,
    Event,
    EventItem,
    EventType,
    Templates,
)
from calendar_splitter.core.rewriter import rewrite_event


def _make_event(**kwargs):
    defaults = {
        "uid": "test", "summary": "", "description": "", "location": "",
        "start": None, "end": None,
    }
    defaults.update(kwargs)
    return Event(**defaults)


class TestRewriteEvent:
    def test_numbered_with_title(self, sample_course_config_dict):
        config = load_course_config(sample_course_config_dict)
        ev = _make_event(
            summary="Lecture 1 (IS1200) Introduction",
            description="Original description",
        )
        et = config.event_types[0]
        item = et.items[1]
        classified = ClassifiedEvent(
            event=ev, course_code="IS1200",
            event_type=et, item=item, kind="lecture", number=1,
        )
        summary, desc = rewrite_event(classified, config)
        assert summary == "Lecture 1 - Course Introduction - IS1200"
        assert "Module 1" in desc
        assert "canvas.kth.se" in desc
        assert "Original description" in desc

    def test_no_kind_passthrough(self):
        config = CourseConfig(course_code="TEST")
        ev = _make_event(summary="Random event", description="Desc")
        classified = ClassifiedEvent(event=ev, course_code="TEST")
        summary, desc = rewrite_event(classified, config)
        assert summary == "Random event"

    def test_no_description_builds_parts(self):
        config = CourseConfig(
            course_code="TEST",
            canvas_url="https://example.com",
        )
        et = EventType(type="lecture", display_name="Lecture")
        item = EventItem(number=1, title="Intro", module="Module 1")
        ev = _make_event(summary="Lecture 1")
        classified = ClassifiedEvent(
            event=ev, course_code="TEST",
            event_type=et, item=item, kind="lecture", number=1,
        )
        _, desc = rewrite_event(classified, config)
        assert "Module 1" in desc
        assert "Canvas: https://example.com" in desc

    def test_custom_templates(self):
        config = CourseConfig(
            course_code="TEST",
            templates=Templates(
                summary="{kind} {n} ({course})",
                description="{original}",
            ),
        )
        et = EventType(type="lecture", display_name="Lecture")
        item = EventItem(number=1, title="Intro")
        ev = _make_event(summary="Lecture 1", description="Old desc")
        classified = ClassifiedEvent(
            event=ev, course_code="TEST",
            event_type=et, item=item, kind="lecture", number=1,
        )
        summary, desc = rewrite_event(classified, config)
        assert summary == "Lecture 1 (TEST)"
        assert desc == "Old desc"

    def test_unnumbered_event(self):
        config = CourseConfig(course_code="TEST")
        et = EventType(type="seminar", display_name="Seminar")
        ev = _make_event(summary="Seminar")
        classified = ClassifiedEvent(
            event=ev, course_code="TEST",
            event_type=et, kind="seminar",
        )
        summary, _ = rewrite_event(classified, config)
        assert "Seminar" in summary
        assert "TEST" in summary
