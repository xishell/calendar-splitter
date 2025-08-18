from scripts.log_sanitize import _redact

def test_redact_tokens_and_query_and_uuid():
    s = "GET https://cal.example/feeds/IS1200--5dd6187aabb24424.ics?v=2 uid=123e4567-e89b-12d3-a456-426614174000"
    r = _redact(s)
    assert "--***.ics" in r
    assert "?v=2" not in r
    assert "426614174000" not in r
