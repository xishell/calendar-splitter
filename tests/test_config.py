"""Tests for config loading and validation."""

import json

import pytest

from calendar_splitter.config import load_course_config, load_courses_from_dir
from calendar_splitter.core.models import StrategyType
from calendar_splitter.exceptions import ConfigError


class TestLoadCourseConfig:
    def test_full_config(self, sample_course_config_dict):
        config = load_course_config(sample_course_config_dict)
        assert config.course_code == "IS1200"
        assert config.course_name == "Computer Hardware Engineering"
        assert config.canvas_url == "https://canvas.kth.se/courses/56261"
        assert config.detection.require_code_in_summary is True
        assert config.detection.course_code_pattern is not None
        assert len(config.event_types) == 2

    def test_minimal_config(self):
        config = load_course_config({"course_code": "DD1351"})
        assert config.course_code == "DD1351"
        assert config.event_types == []

    def test_missing_course_code_raises(self):
        with pytest.raises(ConfigError, match="course_code"):
            load_course_config({})

    def test_invalid_pattern_raises(self):
        with pytest.raises(ConfigError, match="invalid pattern"):
            load_course_config({
                "course_code": "TEST",
                "event_types": [{
                    "type": "lecture",
                    "display_name": "Lecture",
                    "patterns": ["[invalid"],
                }],
            })

    def test_invalid_template_variable_raises(self):
        with pytest.raises(ConfigError, match="invalid variables"):
            load_course_config({
                "course_code": "TEST",
                "templates": {"summary": "{nonexistent}", "description": "{original}"},
            })

    def test_event_items_parsed(self, sample_course_config_dict):
        config = load_course_config(sample_course_config_dict)
        lecture_type = config.event_types[0]
        assert lecture_type.type == "lecture"
        assert 1 in lecture_type.items
        assert lecture_type.items[1].title == "Course Introduction"

    def test_match_strategies_parsed(self):
        config = load_course_config({
            "course_code": "TEST",
            "event_types": [{
                "type": "lecture",
                "display_name": "Lecture",
                "patterns": ["\\bLecture\\s*(\\d+)\\b"],
                "items": [{
                    "number": 1,
                    "title": "Intro",
                    "match": [{"strategy": "time", "priority": 1, "day": "monday"}],
                }],
            }],
        })
        item = config.event_types[0].items[1]
        assert len(item.match) == 1
        assert item.match[0].strategy == StrategyType.TIME

    def test_unknown_strategy_raises(self):
        with pytest.raises(ConfigError, match="Unknown strategy"):
            load_course_config({
                "course_code": "TEST",
                "event_types": [{
                    "type": "lecture",
                    "display_name": "Lecture",
                    "patterns": ["\\bLecture\\b"],
                    "items": [{
                        "number": 1,
                        "match": [{"strategy": "bogus"}],
                    }],
                }],
            })


class TestLoadCoursesFromDir:
    def test_loads_from_directory(self, tmp_courses_dir):
        configs = load_courses_from_dir(tmp_courses_dir)
        assert "IS1200" in configs
        assert configs["IS1200"].course_name == "Computer Hardware Engineering"

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        configs = load_courses_from_dir(empty)
        assert configs == {}

    def test_nonexistent_directory(self, tmp_path):
        configs = load_courses_from_dir(tmp_path / "nope")
        assert configs == {}

    def test_skips_invalid_json(self, tmp_path):
        courses_dir = tmp_path / "courses"
        courses_dir.mkdir()
        (courses_dir / "bad.json").write_text("not json", encoding="utf-8")
        (courses_dir / "good.json").write_text(
            json.dumps({"course_code": "OK"}), encoding="utf-8"
        )
        configs = load_courses_from_dir(courses_dir)
        assert "OK" in configs
        assert len(configs) == 1
