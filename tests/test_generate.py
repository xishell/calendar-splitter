"""Tests for spec-driven event generation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from calendar_splitter.core.parser import parse_calendar
from calendar_splitter.exceptions import ConfigError
from calendar_splitter.generate import FeedSpec, _overlaps, generate_feed, load_specs

TZ = ZoneInfo("Europe/Stockholm")


def _spec(tmp_path, payload):
    (tmp_path / "f.json").write_text(json.dumps(payload), encoding="utf-8")
    return load_specs(tmp_path)


def _at(day, hh, mm=0):
    return datetime(2026, 9, day, hh, mm, tzinfo=TZ)


# ── loading ─────────────────────────────────────────────


def test_missing_dir_is_not_an_error(tmp_path):
    assert load_specs(tmp_path / "nope") == []


def test_loads_feed_metadata(tmp_path):
    specs = _spec(tmp_path, {"feed": "GYM", "name": "Training", "rules": []})
    assert specs[0].feed == "GYM"
    assert specs[0].name == "Training"
    assert specs[0].timezone == "Europe/Stockholm"


def test_rejects_missing_feed(tmp_path):
    with pytest.raises(ConfigError, match="missing 'feed'"):
        _spec(tmp_path, {"name": "x"})


def test_rejects_bad_kind(tmp_path):
    with pytest.raises(ConfigError, match=r"fixed.*recurring"):
        _spec(tmp_path, {"feed": "X", "rules": [{"kind": "wat", "summary": "s"}]})


def test_rejects_unknown_weekday(tmp_path):
    with pytest.raises(ConfigError, match="unknown weekday"):
        _spec(tmp_path, {"feed": "X", "rules": [
            {"kind": "recurring", "summary": "s", "from": "2026-09-01",
             "until": "2026-09-07", "days": ["funday"]}]})


def test_rejects_per_week_over_available_days(tmp_path):
    with pytest.raises(ConfigError, match="exceeds"):
        _spec(tmp_path, {"feed": "X", "rules": [
            {"kind": "recurring", "summary": "s", "from": "2026-09-01",
             "until": "2026-09-07", "days": ["mon", "tue"], "per_week": 3}]})


def test_rejects_fixed_without_times(tmp_path):
    with pytest.raises(ConfigError, match="needs start and end"):
        _spec(tmp_path, {"feed": "X", "rules": [{"kind": "fixed", "summary": "s"}]})


# ── fixed ───────────────────────────────────────────────


def test_fixed_event_uses_spec_timezone(tmp_path):
    spec = _spec(tmp_path, {"feed": "EXAM", "rules": [
        {"kind": "fixed", "summary": "1MA462", "start": "2026-10-17T12:00",
         "end": "2026-10-17T17:00"}]})[0]
    slots = generate_feed(spec, [])
    assert len(slots) == 1
    assert slots[0].start.tzinfo is not None
    assert slots[0].start.hour == 12
    assert slots[0].end - slots[0].start == timedelta(hours=5)


def test_fixed_rejects_reversed_range(tmp_path):
    spec = _spec(tmp_path, {"feed": "X", "rules": [
        {"kind": "fixed", "summary": "s", "start": "2026-10-17T17:00",
         "end": "2026-10-17T12:00"}]})[0]
    with pytest.raises(ConfigError, match="end is before start"):
        generate_feed(spec, [])


# ── recurring placement ─────────────────────────────────


def _gym(**over):
    rule = {"kind": "recurring", "summary": "Gym", "from": "2026-09-07",
            "until": "2026-09-13", "days": ["mon", "tue", "wed", "thu", "fri"],
            "window": ["17:00", "20:00"], "duration_min": 90, "per_week": 3}
    rule.update(over)
    return FeedSpec(feed="GYM", rules=[]), rule


def test_places_requested_count_per_week(tmp_path):
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [_gym()[1]]})[0]
    slots = generate_feed(spec, [])
    assert len(slots) == 3
    assert all(s.start.hour == 17 for s in slots)


def test_takes_earliest_days_in_order(tmp_path):
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [_gym()[1]]})[0]
    slots = generate_feed(spec, [])
    # mon, tue, wed of the week beginning 2026-09-07
    assert [s.start.day for s in slots] == [7, 8, 9]


def test_avoids_busy_intervals(tmp_path):
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [_gym()[1]]})[0]
    # block 17:00-18:30 on the Monday, so it should shift later that day
    busy = [(_at(7, 17), _at(7, 18, 30))]
    slots = generate_feed(spec, busy)
    monday = next(s for s in slots if s.start.day == 7)
    assert monday.start >= _at(7, 18, 30)


def test_skips_a_day_with_no_room_and_uses_the_next(tmp_path):
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [_gym()[1]]})[0]
    busy = [(_at(7, 16), _at(7, 21))]  # monday fully blocked
    slots = generate_feed(spec, busy)
    assert 7 not in [s.start.day for s in slots]
    assert len(slots) == 3


def test_avoid_conflicts_false_ignores_busy(tmp_path):
    rule = _gym(avoid_conflicts=False)[1]
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    slots = generate_feed(spec, [(_at(7, 17), _at(7, 21))])
    assert [s.start.day for s in slots] == [7, 8, 9]


def test_generated_events_become_busy_for_later_rules(tmp_path):
    spec = _spec(tmp_path, {"feed": "X", "rules": [
        {"kind": "recurring", "summary": "A", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["17:00", "20:00"], "duration_min": 60, "per_week": 1},
        {"kind": "recurring", "summary": "B", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["17:00", "20:00"], "duration_min": 60, "per_week": 1},
    ]})[0]
    slots = generate_feed(spec, [])
    assert len(slots) == 2
    assert slots[0].end <= slots[1].start


def test_rotate_cycles_labels(tmp_path):
    rule = _gym(rotate=["Day A", "Day B"])[1]
    rule["summary"] = "Gym — {rotate}"
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    slots = generate_feed(spec, [])
    assert [s.summary for s in slots] == ["Gym — Day A", "Gym — Day B", "Gym — Day A"]


def test_spans_multiple_weeks(tmp_path):
    rule = _gym(**{"from": "2026-09-07", "until": "2026-09-20"})[1]
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    slots = generate_feed(spec, [])
    assert len(slots) == 6


def test_does_not_place_outside_the_range(tmp_path):
    # range starts midweek: the Mon/Tue before it must not be used
    rule = _gym(**{"from": "2026-09-09", "until": "2026-09-13", "per_week": 2})[1]
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    slots = generate_feed(spec, [])
    assert all(s.start.day >= 9 for s in slots)


def test_duration_never_exceeds_window(tmp_path):
    rule = _gym(duration_min=200)[1]  # 200min will not fit 17:00-20:00
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    assert generate_feed(spec, []) == []


def test_priority_orders_specs_lower_first(tmp_path):
    (tmp_path / "z.json").write_text(json.dumps(
        {"feed": "Z", "priority": 10, "rules": []}), encoding="utf-8")
    (tmp_path / "a.json").write_text(json.dumps(
        {"feed": "A", "priority": 90, "rules": []}), encoding="utf-8")
    assert [s.feed for s in load_specs(tmp_path)] == ["Z", "A"]


def test_priority_defaults_to_50(tmp_path):
    assert _spec(tmp_path, {"feed": "X", "rules": []})[0].priority == 50


def test_partial_week_does_not_warn(tmp_path, caplog):
    # range covers only wed-fri, so a 3/week rule can never fill the flanking weeks
    rule = _gym(**{"from": "2026-09-09", "until": "2026-09-11"})[1]
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    with caplog.at_level("WARNING"):
        generate_feed(spec, [])
    assert "only placed" not in caplog.text


def test_full_week_that_cannot_fill_does_warn(tmp_path, caplog):
    rule = _gym()[1]
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    with caplog.at_level("WARNING"):
        generate_feed(spec, [(_at(d, 16), _at(d, 21)) for d in (7, 8, 9, 10, 11)])
    assert "only placed 0/3" in caplog.text


def test_color_is_optional_and_defaults_empty(tmp_path):
    assert _spec(tmp_path, {"feed": "X", "rules": []})[0].color == ""


def test_color_is_read_from_spec(tmp_path):
    assert _spec(tmp_path, {"feed": "X", "color": "#112233", "rules": []})[0].color == "#112233"


def test_parsed_all_day_and_floating_events_are_comparable():
    """Regression: these used to be dropped from the busy set or crash on comparison."""
    ics = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//t//EN
BEGIN:VEVENT
UID:allday@x
SUMMARY:Field trip
DTSTART;VALUE=DATE:20260910
DTEND;VALUE=DATE:20260911
END:VEVENT
BEGIN:VEVENT
UID:floating@x
SUMMARY:Floating
DTSTART:20260910T090000
DTEND:20260910T100000
END:VEVENT
END:VCALENDAR
"""
    busy = [(e.start, e.end) for e in parse_calendar(ics) if e.start and e.end]
    assert len(busy) == 2
    probe_s = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
    probe_e = datetime(2026, 9, 10, 10, 30, tzinfo=TZ)
    assert _overlaps(probe_s, probe_e, busy) is True


def test_travel_pads_the_busy_interval_not_the_event(tmp_path):
    rule = _gym(travel_min=30, per_week=1, days=["mon"])[1]
    spec = _spec(tmp_path, {"feed": "GYM", "rules": [rule]})[0]
    busy = []
    slots = generate_feed(spec, busy)
    # the event is the session itself
    assert slots[0].end - slots[0].start == timedelta(minutes=90)
    # but half an hour either side is reserved
    assert busy[0][0] == slots[0].start - timedelta(minutes=30)
    assert busy[0][1] == slots[0].end + timedelta(minutes=30)


def test_travel_keeps_a_later_session_clear_of_the_journey(tmp_path):
    spec = _spec(tmp_path, {"feed": "X", "rules": [
        {"kind": "recurring", "summary": "Sailing", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["17:00", "20:00"], "duration_min": 180,
         "per_week": 1, "travel_min": 40},
        {"kind": "recurring", "summary": "Lift", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["16:00", "23:00"], "duration_min": 60, "per_week": 1},
    ]})[0]
    slots = generate_feed(spec, [])
    sail, lift = slots[0], slots[1]
    assert sail.start.hour == 17 and sail.end.hour == 20
    # 40 min home from sailing, so the lift cannot start before 20:40
    assert lift.start >= sail.end + timedelta(minutes=40)


def test_travel_defaults_to_zero(tmp_path):
    spec = _spec(tmp_path, {"feed": "X", "rules": [_gym(per_week=1, days=["mon"])[1]]})[0]
    busy = []
    slots = generate_feed(spec, busy)
    assert busy[0] == (slots[0].start, slots[0].end)


def _fb(**over):
    rule = {"kind": "recurring", "summary": "Lift", "from": "2026-09-07", "until": "2026-09-11",
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "window": ["07:00", "11:00"], "fallback_window": ["16:00", "21:00"],
            "duration_min": 75, "per_week": 4}
    rule.update(over)
    return rule


def test_fallback_is_untouched_while_the_preferred_window_fits(tmp_path):
    spec = _spec(tmp_path, {"feed": "G", "rules": [_fb()]})[0]
    slots = generate_feed(spec, [])
    assert len(slots) == 4
    assert all(s.start.hour < 12 for s in slots)


def test_fallback_catches_sessions_the_preferred_window_cannot_fit(tmp_path):
    spec = _spec(tmp_path, {"feed": "G", "rules": [_fb()]})[0]
    busy = [(_at(d, 6), _at(d, 12)) for d in (7, 8, 9, 10, 11)]
    slots = generate_feed(spec, busy)
    assert len(slots) == 4
    assert all(s.start.hour >= 16 for s in slots)


def test_preferred_window_is_exhausted_across_all_days_before_the_fallback(tmp_path):
    """Two blocked mornings must not push the whole week to evenings."""
    spec = _spec(tmp_path, {"feed": "G", "rules": [_fb()]})[0]
    busy = [(_at(d, 6), _at(d, 12)) for d in (7, 8)]
    slots = generate_feed(spec, busy)
    assert len(slots) == 4
    assert sum(1 for s in slots if s.start.hour < 12) == 3   # wed, thu, fri mornings
    assert sum(1 for s in slots if s.start.hour >= 16) == 1  # only the shortfall


def test_without_a_fallback_a_blocked_window_drops_the_session(tmp_path):
    spec = _spec(tmp_path, {"feed": "G", "rules": [_fb(fallback_window=None)]})[0]
    busy = [(_at(d, 6), _at(d, 12)) for d in (7, 8, 9, 10, 11)]
    assert generate_feed(spec, busy) == []


# ── scored placement ────────────────────────────────────


def test_prefer_late_packs_toward_the_end_of_the_window(tmp_path):
    rule = _gym(prefer="late", per_week=1, days=["mon"])[1]
    spec = _spec(tmp_path, {"feed": "G", "rules": [rule]})[0]
    slot = generate_feed(spec, [])[0]
    assert slot.end == _at(7, 20)


def test_min_gap_stops_sessions_running_back_to_back(tmp_path):
    spec = _spec(tmp_path, {"feed": "G", "rules": [
        {"kind": "recurring", "summary": "Lift", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["16:00", "22:00"], "duration_min": 60, "per_week": 1},
        {"kind": "recurring", "summary": "Run", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["16:00", "22:00"], "duration_min": 30, "per_week": 1,
         "min_gap_min": 45},
    ]})[0]
    lift, run = generate_feed(spec, [])
    assert (run.start - lift.end) >= timedelta(minutes=45)


def test_clearance_breaks_ties_within_the_preferred_hour(tmp_path):
    """Two starts in the same hour: take the one with more room around it."""
    rule = _gym(per_week=1, days=["mon"], duration_min=30)[1]
    rule["window"] = ["17:00", "18:00"]
    spec = _spec(tmp_path, {"feed": "G", "rules": [rule]})[0]
    # something ends at 17:00, so starting at 17:00 has zero clearance
    slot = generate_feed(spec, [(_at(7, 16), _at(7, 17))])[0]
    assert slot.start > _at(7, 17)


# ── recovery ────────────────────────────────────────────


def test_recovery_keeps_intervals_clear_of_a_lower_day(tmp_path):
    spec = _spec(tmp_path, {"feed": "G", "rules": [
        {"kind": "recurring", "summary": "Lower", "from": "2026-09-07", "until": "2026-09-11",
         "days": ["mon"], "window": ["07:00", "12:00"], "duration_min": 60, "per_week": 1,
         "tags": ["lower"]},
        {"kind": "recurring", "summary": "Intervals", "from": "2026-09-07", "until": "2026-09-11",
         "days": ["mon", "tue", "wed", "thu", "fri"],
         "window": ["07:00", "12:00"], "duration_min": 45, "per_week": 1,
         "min_hours_after": {"lower": 36}},
    ]})[0]
    lower, intervals = generate_feed(spec, [])
    assert lower.start.day == 7
    assert (intervals.start - lower.end) >= timedelta(hours=36)


def test_untagged_sessions_are_unaffected_by_recovery(tmp_path):
    spec = _spec(tmp_path, {"feed": "G", "rules": [
        {"kind": "recurring", "summary": "Lower", "from": "2026-09-07", "until": "2026-09-08",
         "days": ["mon"], "window": ["07:00", "12:00"], "duration_min": 60, "per_week": 1,
         "tags": ["lower"]},
        {"kind": "recurring", "summary": "Study", "from": "2026-09-07", "until": "2026-09-08",
         "days": ["mon"], "window": ["07:00", "12:00"], "duration_min": 60, "per_week": 1},
    ]})[0]
    assert len(generate_feed(spec, [])) == 2


def test_max_per_day_caps_sessions_across_rules(tmp_path):
    """A rule is already one-per-day, so the cap only bites when rules stack on a day."""
    rules = [
        {"kind": "recurring", "summary": f"S{i}", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["07:00", "22:00"], "duration_min": 30, "per_week": 1,
         "max_per_day": 2}
        for i in range(3)
    ]
    spec = _spec(tmp_path, {"feed": "G", "rules": rules})[0]
    assert len(generate_feed(spec, [])) == 2


def test_rejects_a_bad_prefer_value(tmp_path):
    with pytest.raises(ConfigError, match="prefer must be"):
        _spec(tmp_path, {"feed": "X", "rules": [_gym(prefer="whenever")[1]]})
