from scripts.rules import CourseRules
from scripts.rewrite import rewrite_event, detect_course_code

def _rules_is1200():
    data = {
        "course": "IS1200",
        "canvas": "https://canvas.kth.se/courses/56261",
        "match": {"require_course_in_summary": True, "summary_regex": r"\bLecture\s*(\d+)\b"},
        "title_template": "Lecture {n} - {title} - {course}",
        "description_template": "{module}\nCanvas: {canvas}\n\n{old_desc}",
        "items": [{"number": 1, "title": "Course Introduction", "module": "Module 1"}],
    }
    return CourseRules.from_json(data)

def test_detect_course_code():
    s = "Lecture 1 - Something (IS1200)"
    d = "https://www.kth.se/social/course/IS1200/event/123/"
    assert detect_course_code(s, "") == "IS1200"
    assert detect_course_code("", d) == "IS1200"

def test_rewrite_summary_and_description():
    cr = _rules_is1200()
    orig_sum = "Lecture 1 - Placeholder (IS1200)"
    orig_desc = "Original details."
    new_sum, new_desc = rewrite_event(orig_sum, orig_desc, "IS1200", cr)
    assert new_sum == "Lecture 1 - Course Introduction - IS1200"
    assert "Module 1" in new_desc
    assert "Canvas:" in new_desc
    assert "Original details." in new_desc

def test_no_rewrite_when_course_missing_and_required():
    cr = _rules_is1200()
    orig_sum = "Lecture 1 - Placeholder"   # no (IS1200)
    new_sum, new_desc = rewrite_event(orig_sum, "", "IS1200", cr)
    assert new_sum == orig_sum  # unchanged

def test_lab_event_processing():
    # Test with Schema B format that includes labs
    data = {
        "course_code": "IS1200",
        "canvas_url": "https://canvas.kth.se/courses/56261",
        "labs": [{"number": 2, "title": "C Programming", "module": "Module 1"}],
        "lectures": []
    }
    cr = CourseRules.from_json(data)
    
    orig_sum = "Lab 2 - Test (IS1200)"
    orig_desc = "Lab details."
    new_sum, new_desc = rewrite_event(orig_sum, orig_desc, "IS1200", cr)
    
    assert "Lab 2 - C Programming - IS1200" == new_sum
    assert "Module 1" in new_desc
    assert "Canvas:" in new_desc
    assert "Lab details." in new_desc
