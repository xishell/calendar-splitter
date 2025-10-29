import pytest
from scripts.rules import CourseRules, detect_schema

# ===== Schema Detection Tests =====

def test_schema_detection_explicit_version_a():
    """Test explicit schema_version 'A' detection."""
    data = {"schema_version": "A", "course": "IS1200"}
    assert detect_schema(data) == "A"

def test_schema_detection_explicit_version_b():
    """Test explicit schema_version 'B' detection."""
    data = {"schema_version": "B", "course_code": "IS1200"}
    assert detect_schema(data) == "B"

def test_schema_detection_explicit_version_lowercase():
    """Test case-insensitive schema version."""
    assert detect_schema({"schema_version": "a", "course": "IS1200"}) == "A"
    assert detect_schema({"schema_version": "b", "course_code": "IS1200"}) == "B"

def test_schema_detection_explicit_version_numeric():
    """Test numeric schema version (1=A, 2=B)."""
    assert detect_schema({"schema_version": "1", "course": "IS1200"}) == "A"
    assert detect_schema({"schema_version": "2", "course_code": "IS1200"}) == "B"

def test_schema_detection_auto_detect_a():
    """Test auto-detection of Schema A (has 'course' only)."""
    data = {"course": "IS1200"}
    assert detect_schema(data) == "A"

def test_schema_detection_auto_detect_b():
    """Test auto-detection of Schema B (has 'course_code' only)."""
    data = {"course_code": "IS1200"}
    assert detect_schema(data) == "B"

def test_schema_detection_ambiguous_both_fields():
    """Test ambiguous case with both 'course' and 'course_code' - should default to A."""
    data = {"course": "IS1200", "course_code": "IS1200"}
    assert detect_schema(data) == "A"

def test_schema_detection_missing_both_fields():
    """Test error when neither 'course' nor 'course_code' present."""
    data = {"items": []}
    with pytest.raises(ValueError, match="Cannot determine schema"):
        detect_schema(data)

# ===== Schema A Parsing Tests =====

def test_schema_a_parsing():
    data = {
        "course": "IS1200",
        "canvas": "https://canvas.kth.se/courses/56261",
        "match": {
            "require_course_in_summary": True,
            "summary_regex": r"\bLecture\s*(\d+)\b",
        },
        "title_template": "Lecture {n} - {title} - {course}",
        "description_template": "{module}\nCanvas: {canvas}\n\n{old_desc}",
        "items": [
            {"number": 1, "title": "Intro", "module": "Module 1"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert cr.course == "IS1200"
    assert cr.canvas.endswith("/56261")
    assert cr.require_course_in_summary is True
    assert cr.summary_regex.pattern == r"\bLecture\s*(\d+)\b"
    assert cr.lectures[1]["title"] == "Intro"
    assert "Module 1" in cr.lectures[1]["module"]

def test_schema_a_invalid_number_string():
    """Test Schema A skips item with non-numeric number field."""
    data = {
        "course": "IS1200",
        "items": [
            {"number": "not_a_number", "title": "Bad", "module": "M1"},
            {"number": 2, "title": "Good", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 2 in cr.lectures
    assert cr.lectures[2]["title"] == "Good"
    # Invalid item should be skipped
    assert "not_a_number" not in cr.lectures

def test_schema_a_negative_number():
    """Test Schema A skips item with negative number."""
    data = {
        "course": "IS1200",
        "items": [
            {"number": -5, "title": "Negative", "module": "M1"},
            {"number": 1, "title": "Positive", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 1 in cr.lectures
    assert -5 not in cr.lectures

def test_schema_a_zero_number():
    """Test Schema A skips item with zero number."""
    data = {
        "course": "IS1200",
        "items": [
            {"number": 0, "title": "Zero", "module": "M1"},
            {"number": 1, "title": "One", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 1 in cr.lectures
    assert 0 not in cr.lectures

def test_schema_a_duplicate_number():
    """Test Schema A overwrites duplicate numbers (last one wins)."""
    data = {
        "course": "IS1200",
        "items": [
            {"number": 1, "title": "First", "module": "M1"},
            {"number": 1, "title": "Second", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert cr.lectures[1]["title"] == "Second"  # Last one wins

def test_schema_a_non_dict_item():
    """Test Schema A skips non-dict items."""
    data = {
        "course": "IS1200",
        "items": [
            "not a dict",
            {"number": 1, "title": "Valid", "module": "M1"},
            None,
            {"number": 2, "title": "Also Valid", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 1 in cr.lectures
    assert 2 in cr.lectures
    assert len(cr.lectures) == 2

def test_schema_a_missing_number_field():
    """Test Schema A skips item without 'number' field."""
    data = {
        "course": "IS1200",
        "items": [
            {"title": "No Number", "module": "M1"},
            {"number": 1, "title": "Has Number", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 1 in cr.lectures
    assert len(cr.lectures) == 1

# ===== Schema B Parsing Tests =====

def test_schema_b_parsing():
    data = {
        "course_code": "IX1303",
        "canvas_url": "https://canvas/kth/ix",
        "lectures": [{"number": 2, "title": "L2", "module": "M"}],
        "labs": [{"number": 1, "title": "Lab 1", "module": "Lab M"}],
    }
    cr = CourseRules.from_json(data)
    assert cr.course == "IX1303"
    assert cr.canvas.endswith("ix")
    assert cr.lectures[2]["title"] == "L2"
    assert cr.labs[1]["title"] == "Lab 1"

def test_schema_b_exercises():
    """Test Schema B with exercises array."""
    data = {
        "course_code": "IS1200",
        "lectures": [],
        "labs": [],
        "exercises": [
            {"number": 1, "title": "Ex 1", "module": "M1"},
            {"number": 2, "title": "Ex 2", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 1 in cr.exercises
    assert 2 in cr.exercises
    assert cr.exercises[1]["title"] == "Ex 1"

def test_schema_b_invalid_number():
    """Test Schema B skips item with invalid number."""
    data = {
        "course_code": "IS1200",
        "lectures": [
            {"number": "invalid", "title": "Bad", "module": "M1"},
            {"number": 1, "title": "Good", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 1 in cr.lectures
    assert len(cr.lectures) == 1

def test_schema_b_negative_number():
    """Test Schema B skips item with negative number."""
    data = {
        "course_code": "IS1200",
        "labs": [
            {"number": -1, "title": "Negative", "module": "M1"},
            {"number": 1, "title": "Positive", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert 1 in cr.labs
    assert -1 not in cr.labs

def test_schema_b_duplicate_number():
    """Test Schema B overwrites duplicate numbers."""
    data = {
        "course_code": "IS1200",
        "lectures": [
            {"number": 5, "title": "First", "module": "M1"},
            {"number": 5, "title": "Second", "module": "M2"},
        ],
    }
    cr = CourseRules.from_json(data)
    assert cr.lectures[5]["title"] == "Second"

def test_schema_b_missing_course_code():
    """Test Schema B raises error when course_code is missing."""
    data = {
        "lectures": [{"number": 1, "title": "L1", "module": "M"}],
    }
    with pytest.raises(ValueError, match="Cannot determine schema"):
        CourseRules.from_json(data)

def test_schema_b_empty_course_code():
    """Test Schema B raises error when course_code is empty string."""
    data = {
        "course_code": "",
        "lectures": [],
    }
    with pytest.raises(ValueError, match="Missing course_code"):
        CourseRules.from_json(data)
