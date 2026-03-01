"""Tests for logging and redaction."""

from calendar_splitter.logging import get_logger, redact, setup_logging


class TestRedact:
    def test_removes_query_strings(self):
        assert redact("https://example.com/feed?token=secret") == "https://example.com/feed"

    def test_redacts_uuids(self):
        result = redact("Token: 550e8400-e29b-41d4-a716-446655440000")
        assert "550e8400" not in result
        assert "***" in result

    def test_redacts_long_hex(self):
        result = redact("Key: abcdef0123456789")
        assert "abcdef0123456789" not in result
        assert "***" in result

    def test_redacts_feed_paths(self):
        result = redact("/feeds/IS1200--abcdef01.ics")
        assert "abcdef01" not in result
        assert "/feeds/IS1200--***.ics" in result

    def test_preserves_normal_text(self):
        assert redact("Normal log message") == "Normal log message"


class TestSetupLogging:
    def test_setup_does_not_raise(self):
        setup_logging("DEBUG")
        setup_logging("INFO")
        setup_logging("WARNING")

    def test_invalid_level_defaults(self):
        # Should not raise, just default to INFO
        setup_logging("INVALID")


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test_module")
        assert logger.name == "test_module"
