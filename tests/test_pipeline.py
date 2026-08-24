"""Integration tests for the full pipeline."""

import json

import pytest
from icalendar import Calendar

from calendar_splitter.pipeline import PipelineConfig, run_pipeline

from .conftest import SAMPLE_ICS_BYTES


@pytest.mark.integration
class TestPipeline:
    def test_full_pipeline(self, tmp_path, sample_course_config_dict):
        # Setup
        ics_file = tmp_path / "upstream.ics"
        ics_file.write_bytes(SAMPLE_ICS_BYTES)

        courses_dir = tmp_path / "courses"
        courses_dir.mkdir()
        (courses_dir / "IS1200.json").write_text(
            json.dumps(sample_course_config_dict), encoding="utf-8"
        )

        feeds_dir = tmp_path / "feeds"
        state_path = tmp_path / "state.json"
        token_path = tmp_path / "tokens.json"

        config = PipelineConfig(
            source_url="",
            local_fallback=ics_file,
            state_path=state_path,
            courses_dir=courses_dir,
            feeds_dir=feeds_dir,
            token_map_path=token_path,
        )

        result = run_pipeline(config)
        assert not result.skipped
        assert result.total_events == 4
        assert result.kept_events > 0
        assert len(result.feeds) > 0

        # Verify files were written
        feed_files = list(feeds_dir.glob("*.ics"))
        assert len(feed_files) > 0

        # Verify tokens were saved
        assert token_path.exists()
        tokens = json.loads(token_path.read_text(encoding="utf-8"))
        assert "IS1200" in tokens

    def test_pipeline_skips_unchanged(self, tmp_path, sample_course_config_dict):
        ics_file = tmp_path / "upstream.ics"
        ics_file.write_bytes(SAMPLE_ICS_BYTES)

        courses_dir = tmp_path / "courses"
        courses_dir.mkdir()
        (courses_dir / "IS1200.json").write_text(
            json.dumps(sample_course_config_dict), encoding="utf-8"
        )

        config = PipelineConfig(
            source_url="",
            local_fallback=ics_file,
            state_path=tmp_path / "state.json",
            courses_dir=courses_dir,
            feeds_dir=tmp_path / "feeds",
            token_map_path=tmp_path / "tokens.json",
        )

        # First run
        run_pipeline(config)
        # Second run — should skip
        result = run_pipeline(config)
        assert result.skipped is True

    def test_pipeline_without_configs(self, tmp_path):
        ics_file = tmp_path / "upstream.ics"
        ics_file.write_bytes(SAMPLE_ICS_BYTES)

        config = PipelineConfig(
            source_url="",
            local_fallback=ics_file,
            state_path=tmp_path / "state.json",
            courses_dir=tmp_path / "empty_courses",
            feeds_dir=tmp_path / "feeds",
            token_map_path=tmp_path / "tokens.json",
        )

        result = run_pipeline(config)
        assert not result.skipped
        # Should still detect courses from event summaries
        assert result.kept_events > 0


class TestDroppedDiagnostics:
    """A vanishing event is the failure mode hardest to notice, so it must be named."""

    def test_records_events_with_no_course_code(self, tmp_path):
        ics = tmp_path / "up.ics"
        ics.write_bytes(b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//t//EN
BEGIN:VEVENT
UID:x@x
SUMMARY:Dentist appointment
DTSTART:20260910T090000Z
DTEND:20260910T100000Z
END:VEVENT
END:VCALENDAR
""")
        result = run_pipeline(PipelineConfig(
            local_fallback=ics,
            state_path=tmp_path / "state.json",
            courses_dir=tmp_path / "courses",
            feeds_dir=tmp_path / "feeds",
            token_map_path=tmp_path / "tok.json",
            specs_dir=tmp_path / "specs",
        ))
        assert ("Dentist appointment", "no course code detected") in result.dropped


def test_campus_travel_pads_upstream_events(tmp_path):
    """A lecture reserves the journey either side, so nothing is scheduled on top of it."""
    ics = tmp_path / "up.ics"
    ics.write_bytes(b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//t//EN
BEGIN:VEVENT
UID:lec@x
SUMMARY:IS1200 Lecture 1
DTSTART:20260907T080000Z
DTEND:20260907T100000Z
END:VEVENT
END:VCALENDAR
""")
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "s.json").write_text(json.dumps({"feed": "S", "rules": [
        {"kind": "recurring", "summary": "Study", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["06:00", "18:00"], "duration_min": 60, "per_week": 1}]}))

    def run(travel):
        return run_pipeline(PipelineConfig(
            local_fallback=ics, state_path=tmp_path / f"st{travel}.json",
            courses_dir=tmp_path / "c", feeds_dir=tmp_path / f"f{travel}",
            token_map_path=tmp_path / f"t{travel}.json", specs_dir=specs,
            campus_travel_min=travel))

    assert run(0).generated_events == 1
    assert run(45).generated_events == 1  # still placed, just pushed clear of the journey


def _ics(*events):
    body = "".join(
        f"BEGIN:VEVENT\nUID:{u}@x\nSUMMARY:{s}\nDTSTART:{a}\nDTEND:{b}\nEND:VEVENT\n"
        for u, s, a, b in events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//t//EN\n{body}END:VCALENDAR\n".encode()


def _cfg(tmp_path, tag, **kw):
    return PipelineConfig(
        local_fallback=tmp_path / "up.ics", state_path=tmp_path / f"s{tag}.json",
        courses_dir=tmp_path / "c", feeds_dir=tmp_path / f"f{tag}",
        token_map_path=tmp_path / f"t{tag}.json", specs_dir=tmp_path / "specs", **kw)


def _study_spec(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "s.json").write_text(json.dumps({"feed": "S", "rules": [
        {"kind": "recurring", "summary": "Study", "from": "2026-09-07", "until": "2026-09-07",
         "days": ["mon"], "window": ["08:00", "18:00"], "duration_min": 120, "per_week": 1}]}))
    return specs


class TestBusyExclude:
    def test_excluded_course_does_not_reserve_time(self, tmp_path):
        (tmp_path / "up.ics").write_bytes(_ics(
            ("a", "IS1200 Lecture", "20260907T060000Z", "20260907T120000Z")))
        _study_spec(tmp_path)

        kept = run_pipeline(_cfg(tmp_path, "1"))
        excluded = run_pipeline(_cfg(tmp_path, "2", busy_exclude=("IS1200",)))
        assert kept.generated_events == 1
        assert excluded.generated_events == 1
        # with IS1200 blocking 08:00-16:00 the block is pushed late; excluded, it starts at 08:00
        assert self._start(tmp_path, "f2") < self._start(tmp_path, "f1")

    @staticmethod
    def _start(tmp_path, d):
        p = next((tmp_path / d).glob("S--*.ics"))
        ev = next(c for c in Calendar.from_ical(p.read_bytes()).walk() if c.name == "VEVENT")
        return ev.decoded("DTSTART")


class TestStableUids:
    def test_uid_survives_the_block_moving_within_its_day(self, tmp_path):
        _study_spec(tmp_path)
        (tmp_path / "up.ics").write_bytes(_ics())
        first = self._uid(tmp_path, "a", ())
        # a lecture appears and pushes the block later the same day
        (tmp_path / "up.ics").write_bytes(_ics(
            ("a", "IS1200 Lecture", "20260907T060000Z", "20260907T080000Z")))
        second = self._uid(tmp_path, "b", ())
        assert first == second

    def _uid(self, tmp_path, tag, exclude):
        run_pipeline(_cfg(tmp_path, tag, busy_exclude=exclude))
        p = next((tmp_path / f"f{tag}").glob("S--*.ics"))
        ev = next(c for c in Calendar.from_ical(p.read_bytes()).walk() if c.name == "VEVENT")
        return str(ev.get("UID"))


class TestConfigChangeForcesRebuild:
    """A spec edit used to be ignored until the upstream ICS also moved."""

    def _run(self, tmp_path, **kw):
        return run_pipeline(PipelineConfig(
            local_fallback=tmp_path / "up.ics", state_path=tmp_path / "state.json",
            courses_dir=tmp_path / "c", feeds_dir=tmp_path / "feeds",
            token_map_path=tmp_path / "tok.json", specs_dir=tmp_path / "specs", **kw))

    def _setup(self, tmp_path, summary):
        (tmp_path / "up.ics").write_bytes(_ics(
            ("a", "IS1200 Lecture", "20260907T060000Z", "20260907T070000Z")))
        specs = tmp_path / "specs"
        specs.mkdir(exist_ok=True)
        (specs / "s.json").write_text(json.dumps({"feed": "S", "rules": [
            {"kind": "recurring", "summary": summary, "from": "2026-09-07",
             "until": "2026-09-07", "days": ["mon"], "window": ["08:00", "18:00"],
             "duration_min": 60, "per_week": 1}]}))

    def test_unchanged_everything_still_skips(self, tmp_path):
        self._setup(tmp_path, "Study")
        assert self._run(tmp_path).skipped is False
        assert self._run(tmp_path).skipped is True

    def test_editing_a_spec_rebuilds(self, tmp_path):
        self._setup(tmp_path, "Study")
        self._run(tmp_path)
        assert self._run(tmp_path).skipped is True
        self._setup(tmp_path, "Study, renamed")
        assert self._run(tmp_path).skipped is False
        out = next((tmp_path / "feeds").glob("S--*.ics")).read_text()
        assert "Study\\, renamed" in out or "Study, renamed" in out

    def test_force_rebuilds_without_any_change(self, tmp_path):
        self._setup(tmp_path, "Study")
        self._run(tmp_path)
        assert self._run(tmp_path).skipped is True
        assert self._run(tmp_path, force=True).skipped is False
