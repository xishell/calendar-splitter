"""Integration tests for the full pipeline."""

import json

import pytest

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
