"""Tests for upstream fetching."""

import json
from unittest.mock import MagicMock, patch

import pytest

from calendar_splitter.exceptions import FetchError
from calendar_splitter.fetch import fetch_upstream


class TestFetchLocal:
    def test_reads_local_file(self, tmp_path):
        ics_file = tmp_path / "cal.ics"
        ics_file.write_bytes(b"BEGIN:VCALENDAR\nEND:VCALENDAR")
        state_path = tmp_path / "state.json"

        result = fetch_upstream(None, ics_file, state_path)
        assert result == b"BEGIN:VCALENDAR\nEND:VCALENDAR"

    def test_returns_none_if_unchanged(self, tmp_path):
        ics_file = tmp_path / "cal.ics"
        ics_file.write_bytes(b"BEGIN:VCALENDAR\nEND:VCALENDAR")
        state_path = tmp_path / "state.json"

        # First fetch
        fetch_upstream(None, ics_file, state_path)
        # Second fetch - unchanged
        result = fetch_upstream(None, ics_file, state_path)
        assert result is None

    def test_detects_change(self, tmp_path):
        ics_file = tmp_path / "cal.ics"
        state_path = tmp_path / "state.json"

        ics_file.write_bytes(b"version1")
        fetch_upstream(None, ics_file, state_path)

        ics_file.write_bytes(b"version2")
        result = fetch_upstream(None, ics_file, state_path)
        assert result == b"version2"

    def test_missing_file_raises(self, tmp_path):
        state_path = tmp_path / "state.json"
        with pytest.raises(FetchError, match="not found"):
            fetch_upstream(None, tmp_path / "nope.ics", state_path)

    def test_empty_url_treated_as_local(self, tmp_path):
        ics_file = tmp_path / "cal.ics"
        ics_file.write_bytes(b"data")
        state_path = tmp_path / "state.json"
        result = fetch_upstream("", ics_file, state_path)
        assert result == b"data"


class TestFetchHTTP:
    @patch("calendar_splitter.fetch.requests.get")
    def test_successful_fetch(self, mock_get, tmp_path):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"calendar data"
        resp.headers = {"ETag": '"abc"', "Last-Modified": "Mon, 01 Jan 2025"}
        mock_get.return_value = resp

        state_path = tmp_path / "state.json"
        result = fetch_upstream("https://example.com/cal.ics", tmp_path / "f.ics", state_path)
        assert result == b"calendar data"

    @patch("calendar_splitter.fetch.requests.get")
    def test_304_returns_none(self, mock_get, tmp_path):
        resp = MagicMock()
        resp.status_code = 304
        mock_get.return_value = resp

        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"etag": '"old"'}), encoding="utf-8")
        result = fetch_upstream("https://example.com/cal.ics", tmp_path / "f.ics", state_path)
        assert result is None

    @patch("calendar_splitter.fetch.requests.get")
    def test_error_status_raises(self, mock_get, tmp_path):
        resp = MagicMock()
        resp.status_code = 500
        resp.content = b""
        mock_get.return_value = resp

        state_path = tmp_path / "state.json"
        with pytest.raises(FetchError, match="500"):
            fetch_upstream("https://example.com/cal.ics", tmp_path / "f.ics", state_path)

    @patch("calendar_splitter.fetch.requests.get")
    def test_sends_etag_conditional(self, mock_get, tmp_path):
        resp = MagicMock()
        resp.status_code = 304
        mock_get.return_value = resp

        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"etag": '"xyz"'}), encoding="utf-8")
        fetch_upstream("https://example.com/cal.ics", tmp_path / "f.ics", state_path)

        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["If-None-Match"] == '"xyz"'

    @patch("calendar_splitter.fetch.requests.get")
    def test_sha256_dedup(self, mock_get, tmp_path):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"same content"
        resp.headers = {}
        mock_get.return_value = resp

        state_path = tmp_path / "state.json"
        # First fetch
        result1 = fetch_upstream("https://example.com/cal.ics", tmp_path / "f.ics", state_path)
        assert result1 == b"same content"
        # Second fetch — same hash
        result2 = fetch_upstream("https://example.com/cal.ics", tmp_path / "f.ics", state_path)
        assert result2 is None
