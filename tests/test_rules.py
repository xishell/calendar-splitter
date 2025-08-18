from scripts.rules import CourseRules

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
