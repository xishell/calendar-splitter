from scripts.rules import CourseRules
from scripts.rewrite import rewrite_event, detect_course_code

# ===== Course Detection Tests =====

def test_detect_course_code_kth_style():
    """Test KTH-style course codes (2 letters + 4 digits)."""
    assert detect_course_code("Lecture 1 - IS1200", "") == "IS1200"
    assert detect_course_code("DD1351 - Algorithms", "") == "DD1351"
    assert detect_course_code("SF1922 Probability", "") == "SF1922"

def test_detect_course_code_parentheses():
    """Test course codes in parentheses."""
    assert detect_course_code("Lecture 1 (IS1200)", "") == "IS1200"
    assert detect_course_code("Something (DD1351HT) thing", "") == "DD1351HT"
    assert detect_course_code("(CS101) Introduction", "") == "CS101"

def test_detect_course_code_kth_style_priority():
    """Test KTH-style pattern has priority over parentheses."""
    # Should match IS1200 (KTH-style) not OTHER in parens
    assert detect_course_code("IS1200 Lecture (OTHER)", "") == "IS1200"

def test_detect_course_code_url_fallback():
    """Test URL pattern as fallback."""
    summary = "Lecture 1 - Introduction"
    desc = "https://www.kth.se/social/course/IS1200/event/123/"
    assert detect_course_code(summary, desc) == "IS1200"

def test_detect_course_code_false_positive_year():
    """Test that year numbers like (2024) are NOT matched."""
    assert detect_course_code("Meeting at (2024)", "") is None
    assert detect_course_code("(2025) Conference", "") is None

def test_detect_course_code_false_positive_short():
    """Test that short codes like (HTML), (PDF) are NOT matched."""
    assert detect_course_code("Download (PDF)", "") is None
    assert detect_course_code("(HTML) version", "") is None
    assert detect_course_code("(API) documentation", "") is None

def test_detect_course_code_false_positive_pure_numbers():
    """Test that pure numbers are NOT matched."""
    assert detect_course_code("Room (123)", "") is None
    assert detect_course_code("(456789)", "") is None

def test_detect_course_code_mixed_case():
    """Test case sensitivity (should only match uppercase)."""
    # Only uppercase should match
    assert detect_course_code("is1200 lecture", "") is None  # lowercase
    assert detect_course_code("Is1200 lecture", "") is None  # mixed case
    assert detect_course_code("IS1200 lecture", "") == "IS1200"  # uppercase

def test_detect_course_code_with_hyphen():
    """Test course codes with hyphens (less common but valid)."""
    summary = ""
    desc = "https://www.kth.se/social/course/IS-1200/event/123/"
    assert detect_course_code(summary, desc) == "IS-1200"

def test_detect_course_code_no_match():
    """Test returns None when no course code found."""
    assert detect_course_code("Just a meeting", "No course info") is None
    assert detect_course_code("", "") is None

def test_detect_course_code_boundary():
    """Test word boundary matching for KTH-style."""
    # Should match at word boundaries
    assert detect_course_code("IS1200:", "") == "IS1200"
    assert detect_course_code("IS1200.", "") == "IS1200"
    assert detect_course_code("IS1200!", "") == "IS1200"

    # Should NOT match in middle of alphanumeric string
    assert detect_course_code("XIS1200X", "") is None

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
