"""Upstream calendar fetching with caching."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from calendar_splitter.exceptions import FetchError
from calendar_splitter.logging import get_logger, redact

_log = get_logger(__name__)

_HTTP_OK = 200
_HTTP_NOT_MODIFIED = 304


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_state(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_upstream(
    source_url: str | None,
    local_fallback: Path,
    state_path: Path,
    timeout: int = 30,
) -> bytes | None:
    """Fetch upstream ICS data, returning bytes only if content changed.

    Returns None when upstream is unchanged since last run.
    """
    state = _read_state(state_path)
    source_url = (source_url or "").strip()

    if not source_url:
        return _fetch_local(local_fallback, state_path, state)
    return _fetch_http(source_url, state_path, state, timeout)


def _fetch_local(
    path: Path, state_path: Path, state: dict[str, Any]
) -> bytes | None:
    if not path.exists():
        msg = f"Local upstream file not found: {path}"
        raise FetchError(msg)

    data = path.read_bytes()
    new_hash = _sha256(data)

    if state.get("mode") == "local" and state.get("sha256") == new_hash:
        _log.info("Upstream (local) unchanged; skipping.")
        return None

    _write_state(state_path, {"mode": "local", "sha256": new_hash, "updated_at": int(time.time())})
    _log.info("Detected change in local upstream.")
    return data


def _fetch_http(
    url: str, state_path: Path, state: dict[str, Any], timeout: int
) -> bytes | None:
    session = requests.Session()
    session.headers.update({"User-Agent": "CalendarSplitter/3.0"})

    # Probe for caching headers
    etag_curr = None
    lm_curr = None
    try:
        head = session.head(url, allow_redirects=True, timeout=timeout)
        etag_curr = head.headers.get("ETag")
        lm_curr = head.headers.get("Last-Modified")
    except requests.RequestException as exc:
        _log.warning("HEAD failed, will GET with conditionals: %s", redact(str(exc)))

    # Conditional GET
    headers: dict[str, str] = {}
    etag_prev = state.get("etag")
    lm_prev = state.get("last_modified")
    if etag_prev:
        headers["If-None-Match"] = etag_prev
    elif lm_prev:
        headers["If-Modified-Since"] = lm_prev

    try:
        res = session.get(url, allow_redirects=True, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        msg = f"GET failed: {exc}"
        raise FetchError(msg) from exc

    if res.status_code == _HTTP_NOT_MODIFIED:
        _log.info("Upstream returned 304 Not Modified; skipping.")
        return None
    if res.status_code != _HTTP_OK or not res.content:
        msg = f"Unexpected upstream status: {res.status_code}"
        raise FetchError(msg)

    data = res.content
    new_hash = _sha256(data)

    if state.get("mode") == "http" and state.get("sha256") == new_hash:
        _log.info("Upstream content hash unchanged; skipping.")
        return None

    etag_used = etag_curr or res.headers.get("ETag")
    lm_used = lm_curr or res.headers.get("Last-Modified")

    new_state: dict[str, Any] = {"mode": "http", "sha256": new_hash, "updated_at": int(time.time())}
    if etag_used:
        new_state["etag"] = etag_used
    if lm_used:
        new_state["last_modified"] = lm_used

    _write_state(state_path, new_state)
    _log.info(
        "Detected upstream change (ETag=%s, Last-Modified=%s).",
        redact(etag_used or "—"),
        lm_used or "—",
    )
    return data
