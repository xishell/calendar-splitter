import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from scripts.fetch import fetch_upstream_if_changed, _sha256_bytes, _read_state, _write_state


# ===== SHA256 Hashing Tests =====

def test_sha256_bytes():
    """Test SHA256 hashing of bytes."""
    data = b"test data"
    hash1 = _sha256_bytes(data)
    hash2 = _sha256_bytes(data)
    assert hash1 == hash2  # Same input produces same hash
    assert len(hash1) == 64  # SHA256 produces 64 hex characters

    different_data = b"different data"
    hash3 = _sha256_bytes(different_data)
    assert hash1 != hash3  # Different input produces different hash


# ===== State Persistence Tests =====

def test_read_state_valid_json(tmp_path):
    """Test reading valid state from JSON file."""
    state_file = tmp_path / "state.json"
    state_data = {"mode": "local", "sha256": "abc123"}
    state_file.write_text(json.dumps(state_data))

    result = _read_state(state_file)
    assert result == state_data


def test_read_state_missing_file(tmp_path):
    """Test reading non-existent state file returns empty dict."""
    state_file = tmp_path / "nonexistent.json"
    result = _read_state(state_file)
    assert result == {}


def test_read_state_invalid_json(tmp_path):
    """Test reading invalid JSON returns empty dict."""
    state_file = tmp_path / "bad.json"
    state_file.write_text("not valid json{")
    result = _read_state(state_file)
    assert result == {}


def test_read_state_non_dict_json(tmp_path):
    """Test reading non-dict JSON (like array) returns empty dict."""
    state_file = tmp_path / "array.json"
    state_file.write_text("[1, 2, 3]")
    result = _read_state(state_file)
    assert result == {}


def test_write_state(tmp_path):
    """Test writing state to JSON file."""
    state_file = tmp_path / "subdir" / "state.json"
    state_data = {"mode": "http", "sha256": "def456"}

    _write_state(state_file, state_data)

    assert state_file.exists()
    loaded = json.loads(state_file.read_text())
    assert loaded == state_data


# ===== Local Mode Tests =====

def test_fetch_local_file_first_time(tmp_path):
    """Test fetching local file for the first time (no previous state)."""
    local_file = tmp_path / "calendar.ics"
    local_file.write_bytes(b"BEGIN:VCALENDAR\nEND:VCALENDAR")
    state_file = tmp_path / "state.json"

    result = fetch_upstream_if_changed(None, local_file, state_file)

    assert result == b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    assert state_file.exists()

    state = json.loads(state_file.read_text())
    assert state["mode"] == "local"
    assert "sha256" in state
    assert "updated_at" in state


def test_fetch_local_file_unchanged(tmp_path):
    """Test fetching local file that hasn't changed returns None."""
    local_file = tmp_path / "calendar.ics"
    content = b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    local_file.write_bytes(content)
    state_file = tmp_path / "state.json"

    # First fetch
    result1 = fetch_upstream_if_changed(None, local_file, state_file)
    assert result1 is not None

    # Second fetch (unchanged)
    result2 = fetch_upstream_if_changed(None, local_file, state_file)
    assert result2 is None  # No change detected


def test_fetch_local_file_changed(tmp_path):
    """Test fetching local file that has changed returns new content."""
    local_file = tmp_path / "calendar.ics"
    local_file.write_bytes(b"OLD CONTENT")
    state_file = tmp_path / "state.json"

    # First fetch
    result1 = fetch_upstream_if_changed(None, local_file, state_file)
    assert result1 == b"OLD CONTENT"

    # Change file
    local_file.write_bytes(b"NEW CONTENT")

    # Second fetch (changed)
    result2 = fetch_upstream_if_changed(None, local_file, state_file)
    assert result2 == b"NEW CONTENT"


def test_fetch_local_file_missing(tmp_path):
    """Test fetching non-existent local file returns None."""
    local_file = tmp_path / "nonexistent.ics"
    state_file = tmp_path / "state.json"

    result = fetch_upstream_if_changed(None, local_file, state_file)
    assert result is None


# ===== HTTP Mode Tests =====

@patch('scripts.fetch.requests.Session')
def test_fetch_http_first_time(mock_session_class, tmp_path):
    """Test HTTP fetch with no previous state."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {"ETag": '"etag123"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"}
    mock_session.head.return_value = mock_head

    # Mock GET request
    mock_get = Mock()
    mock_get.status_code = 200
    mock_get.content = b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    mock_get.headers = {"ETag": '"etag123"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"}
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"
    state_file = tmp_path / "state.json"

    result = fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    assert result == b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    assert state_file.exists()

    state = json.loads(state_file.read_text())
    assert state["mode"] == "http"
    assert state["etag"] == '"etag123"'
    assert state["last_modified"] == "Mon, 01 Jan 2024 00:00:00 GMT"


@patch('scripts.fetch.requests.Session')
def test_fetch_http_304_not_modified(mock_session_class, tmp_path):
    """Test HTTP 304 Not Modified response returns None."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Setup existing state
    state_file = tmp_path / "state.json"
    _write_state(state_file, {
        "mode": "http",
        "sha256": "abc123",
        "etag": '"etag123"',
        "updated_at": 1234567890
    })

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request returning 304
    mock_get = Mock()
    mock_get.status_code = 304
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"

    result = fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    assert result is None
    # State should remain unchanged
    state = json.loads(state_file.read_text())
    assert state["sha256"] == "abc123"


@patch('scripts.fetch.requests.Session')
def test_fetch_http_same_content_hash(mock_session_class, tmp_path):
    """Test HTTP fetch with same content hash returns None."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    content = b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    content_hash = _sha256_bytes(content)

    # Setup existing state with same hash
    state_file = tmp_path / "state.json"
    _write_state(state_file, {
        "mode": "http",
        "sha256": content_hash,
        "etag": '"etag123"',
        "updated_at": 1234567890
    })

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request returning same content
    mock_get = Mock()
    mock_get.status_code = 200
    mock_get.content = content
    mock_get.headers = {"ETag": '"etag456"'}
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"

    result = fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    assert result is None  # Content unchanged despite different ETag


@patch('scripts.fetch.requests.Session')
def test_fetch_http_with_etag_conditional(mock_session_class, tmp_path):
    """Test HTTP request uses If-None-Match with previous ETag."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Setup existing state with ETag
    state_file = tmp_path / "state.json"
    _write_state(state_file, {
        "mode": "http",
        "sha256": "oldsha",
        "etag": '"oldtag"',
        "updated_at": 1234567890
    })

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request
    mock_get = Mock()
    mock_get.status_code = 200
    mock_get.content = b"NEW CONTENT"
    mock_get.headers = {"ETag": '"newtag"'}
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"

    fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    # Verify If-None-Match header was sent
    call_args = mock_session.get.call_args
    assert call_args[1]["headers"]["If-None-Match"] == '"oldtag"'


@patch('scripts.fetch.requests.Session')
def test_fetch_http_with_last_modified_conditional(mock_session_class, tmp_path):
    """Test HTTP request uses If-Modified-Since with previous Last-Modified."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Setup existing state with Last-Modified (no ETag)
    state_file = tmp_path / "state.json"
    _write_state(state_file, {
        "mode": "http",
        "sha256": "oldsha",
        "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "updated_at": 1234567890
    })

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request
    mock_get = Mock()
    mock_get.status_code = 200
    mock_get.content = b"NEW CONTENT"
    mock_get.headers = {}
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"

    fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    # Verify If-Modified-Since header was sent
    call_args = mock_session.get.call_args
    assert call_args[1]["headers"]["If-Modified-Since"] == "Mon, 01 Jan 2024 00:00:00 GMT"


@patch('scripts.fetch.requests.Session')
def test_fetch_http_get_failure(mock_session_class, tmp_path):
    """Test HTTP GET failure returns None."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request that raises exception
    mock_session.get.side_effect = Exception("Network error")

    local_file = tmp_path / "fallback.ics"
    state_file = tmp_path / "state.json"

    result = fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    assert result is None


@patch('scripts.fetch.requests.Session')
def test_fetch_http_non_200_status(mock_session_class, tmp_path):
    """Test HTTP non-200 status returns None."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request with 404
    mock_get = Mock()
    mock_get.status_code = 404
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"
    state_file = tmp_path / "state.json"

    result = fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    assert result is None


@patch('scripts.fetch.requests.Session')
def test_fetch_http_empty_content(mock_session_class, tmp_path):
    """Test HTTP request with empty content returns None."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request with empty content
    mock_get = Mock()
    mock_get.status_code = 200
    mock_get.content = b""
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"
    state_file = tmp_path / "state.json"

    result = fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    assert result is None


@patch('scripts.fetch.requests.Session')
def test_fetch_http_head_failure_continues(mock_session_class, tmp_path):
    """Test HEAD failure doesn't stop GET request."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Mock HEAD request that fails
    mock_session.head.side_effect = Exception("HEAD failed")

    # Mock GET request that succeeds
    mock_get = Mock()
    mock_get.status_code = 200
    mock_get.content = b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    mock_get.headers = {}
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"
    state_file = tmp_path / "state.json"

    result = fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    assert result == b"BEGIN:VCALENDAR\nEND:VCALENDAR"


@patch('scripts.fetch.requests.Session')
def test_fetch_http_user_agent_header(mock_session_class, tmp_path):
    """Test HTTP request includes User-Agent header."""
    mock_session = Mock()
    mock_session_class.return_value = mock_session

    # Mock HEAD request
    mock_head = Mock()
    mock_head.headers = {}
    mock_session.head.return_value = mock_head

    # Mock GET request
    mock_get = Mock()
    mock_get.status_code = 200
    mock_get.content = b"content"
    mock_get.headers = {}
    mock_session.get.return_value = mock_get

    local_file = tmp_path / "fallback.ics"
    state_file = tmp_path / "state.json"

    fetch_upstream_if_changed("https://example.com/cal.ics", local_file, state_file)

    # Verify User-Agent was set
    mock_session.headers.update.assert_called_with({"User-Agent": "CalendarSplitter/1.0"})
