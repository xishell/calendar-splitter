from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .log_sanitize import safe_error, safe_log, safe_warn


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _read_state(path: Path) -> Dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _write_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_upstream_if_changed(
    source_url: str | None,
    local_fallback: Path,
    state_path: Path,
    timeout: int = 30,
) -> Optional[bytes]:
    """
    Returns upstream ICS bytes only if content changed since last run; else returns None.
    Tracks ETag/Last-Modified/sha256 in state_path.
    """
    state = _read_state(state_path)
    source_url = (source_url or "").strip()

    # Local mode
    if not source_url:
        if not local_fallback.exists():
            safe_error("Local upstream file not found: %s", str(local_fallback))
            return None
        data = local_fallback.read_bytes()
        new_hash = _sha256_bytes(data)
        if state.get("mode") == "local" and state.get("sha256") == new_hash:
            safe_log("Upstream (local) unchanged; skipping regeneration.")
            return None
        _write_state(state_path, {"mode": "local", "sha256": new_hash, "updated_at": int(time.time())})
        safe_log("Detected change in local upstream; proceeding.")
        return data

    # HTTP mode
    session = requests.Session()
    session.headers.update({"User-Agent": "CalendarSplitter/1.0"})

    etag_prev = state.get("etag")
    lm_prev = state.get("last_modified")

    etag_curr = None
    lm_curr = None
    try:
        head = session.head(source_url, allow_redirects=True, timeout=timeout)
        etag_curr = head.headers.get("ETag")
        lm_curr = head.headers.get("Last-Modified")
    except Exception as e:
        safe_warn("HEAD failed; will GET with conditionals. (%s)", str(e))

    headers: Dict[str, str] = {}
    if etag_prev:
        headers["If-None-Match"] = etag_prev
    elif lm_prev:
        headers["If-Modified-Since"] = lm_prev

    try:
        res = session.get(source_url, allow_redirects=True, headers=headers, timeout=timeout)
    except Exception as e:
        safe_error("GET failed: %s", str(e))
        return None

    if res.status_code == 304:
        safe_log("Upstream returned 304 Not Modified; skipping regeneration.")
        return None
    if res.status_code != 200 or not res.content:
        safe_error("Unexpected upstream status: %s", res.status_code)
        return None

    data = res.content
    new_hash = _sha256_bytes(data)

    if state.get("mode") == "http" and state.get("sha256") == new_hash:
        safe_log("Upstream content hash unchanged; skipping regeneration.")
        return None

    etag_used = etag_curr or res.headers.get("ETag")
    lm_used = lm_curr or res.headers.get("Last-Modified")

    new_state: Dict[str, Any] = {"mode": "http", "sha256": new_hash, "updated_at": int(time.time())}
    if etag_used:
        new_state["etag"] = etag_used
    if lm_used:
        new_state["last_modified"] = lm_used

    _write_state(state_path, new_state)
    safe_log("Detected upstream change; proceeding (ETag=%s, Last-Modified=%s).", etag_used or "—", lm_used or "—")
    return data
