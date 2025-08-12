from icalendar import Calendar, Event, vText
from pathlib import Path
from scripts.split import split_and_write
from scripts.rules import CourseRules

def _make_ics_event(summary: str, description: str) -> bytes:
    cal = Calendar()
    cal.add("PRODID", "-//Test//")
    cal.add("VERSION", "2.0")
    ev = Event()
    ev.add("UID", "u1@test")
    ev.add("SUMMARY", vText(summary))
    ev.add("DESCRIPTION", vText(description))
    ev.add("DTSTART", "20250901T100000Z")
    ev.add("DTEND", "20250901T110000Z")
    cal.add_component(ev)
    return cal.to_ical()

def test_split_and_write(tmp_path: Path):
    # single event for IS1200 Lecture 1
    upstream = _make_ics_event("Lecture 1 - Placeholder (IS1200)", "desc")
    # minimal rules
    cr = CourseRules.from_json({
        "course": "IS1200",
        "items": [{"number": 1, "title": "Intro", "module": "M1"}],
        "match": {"require_course_in_summary": True}
    })
    rules = {"IS1200": cr}
    token_map = {}
    outdir = tmp_path / "feeds"
    written = split_and_write(upstream, rules, outdir, token_map)
    assert written == 1
    # token map got a token
    assert "IS1200" in token_map
    # file exists
    out_files = list(outdir.glob("IS1200--*.ics"))
    assert len(out_files) == 1
    # sanity-check content
    ics = out_files[0].read_text()
    assert "X-WR-CALNAME:IS1200" in ics
    assert "SUMMARY:Lecture 1 - Intro - IS1200" in ics
