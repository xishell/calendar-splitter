#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Split a personal/program ICS into per-course feeds with optional rewriting from JSON rules.
Safe for public CI logs (redacts sensitive bits). Skips work when upstream hasn't changed.

ENV:
  SOURCE_ICS_URL        (optional) upstream ICS URL; if empty -> fallback to LOCAL_UPSTREAM_ICS
  LOCAL_UPSTREAM_ICS    (default: "personal.ics") local file fallback
  EVENTS_DIR            (default: "events") directory with course rule JSON files
  FEEDS_DIR             (required) output dir for per-course .ics files (e.g., "_feeds/docs/feeds")
  TOKEN_MAP_PATH        (required) path to token_map.json in the private repo root
  UPSTREAM_STATE_PATH   (default: "_feeds/upstream_state.json") persistence for ETag/Last-Modified/hash
  LOG_LEVEL             (default: "INFO")

JSON rule schema (example: IS1200_lectures.json):
{
  "course_code": "IS1200",
  "canvas_url": "https://canvas.kth.se/courses/12345",
  "lectures": [
    {"number": 1, "title": "Course Introduction", "module": "Module 1: C and Assembly Programming"},
    {"number": 2, "title": "Assembly Languages", "module": "Module 1: C and Assembly Programming"},
    ...
  ],
  "labs": [...],
  "exercises": [...]
}

Rewriting rules (examples):
- VEVENT with SUMMARY like "Lecture 1 - ... (IS1200)" becomes:
  SUMMARY: "Lecture 1 - Course Introduction - IS1200"
  DESCRIPTION: "<module text>\n\nCanvas: <canvas_url>\n\n<original description>"
- Labs/Exercises: same pattern if present in JSON.

Course detection:
- Extract course code from SUMMARY "(IS1200)" or DESCRIPTION URLs containing e.g. "/course/IS1200/".
"""

from __future__ import annotations

import os
import re
import sys
import json
import uuid
import glob
import time
import hashlib
import pathlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from email.utils import parsedate_to_datetime

import requests
from icalendar import Calendar, Event, vText

# -----------------------------
# Logging with redaction
# -----------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("splitter")

RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{16,}\b|"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[089abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
RE_QS = re.compile(r"(\?.*)$")
RE_FEED_PATH = re.compile(r"(/feeds/[A-Z0-9\-_.]+)--([0-9a-fA-F]{8,})\.ics\b")

SENSITIVE_KEYS = {"SOURCE_ICS_URL", "BASE_URL", "FEEDS_REPO_TOKEN", "FEEDS_REPO", "PAGES_CNAME"}

def redact_text(s: str) -> str:
    s = RE_QS.sub("", s)
    s = RE_FEED_PATH.sub(r"\1--***.ics", s)
    s = RE_UUID.sub("***", s)
    return s

def safe_log(msg: str, *args):
    out = msg % args if args else msg
    log.info(redact_text(out))

def safe_warn(msg: str, *args):
    out = msg % args if args else msg
    log.warning(redact_text(out))

def safe_error(msg: str, *args):
    out = msg % args if args else msg
    log.error(redact_text(out))

# -----------------------------
# Env & paths
# -----------------------------
SOURCE_ICS_URL = os.environ.get("SOURCE_ICS_URL", "").strip()
LOCAL_UPSTREAM_ICS = pathlib.Path(os.environ.get("LOCAL_UPSTREAM_ICS", "personal.ics"))
EVENTS_DIR = pathlib.Path(os.environ.get("EVENTS_DIR", "events"))
FEEDS_DIR = pathlib.Path(os.environ.get("FEEDS_DIR", "")).resolve()
TOKEN_MAP_PATH = pathlib.Path(os.environ.get("TOKEN_MAP_PATH", "")).resolve()
STATE_PATH = pathlib.Path(os.environ.get("UPSTREAM_STATE_PATH", "_feeds/upstream_state.json")).resolve()

if not FEEDS_DIR:
    safe_error("FEEDS_DIR is required.")
    sys.exit(2)
if not TOKEN_MAP_PATH:
    safe_error("TOKEN_MAP_PATH is required.")
    sys.exit(2)

# -----------------------------
# Upstream change detection
# -----------------------------
def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def _read_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_upstream_if_changed(timeout: int = 30) -> Optional[bytes]:
    """
    Returns upstream ICS bytes only if content changed since last run; else returns None.
    Persists etag/last_modified/hash in STATE_PATH.
    """
    state = _read_state()

    # Local fallback mode
    if not SOURCE_ICS_URL:
        if not LOCAL_UPSTREAM_ICS.exists():
            safe_error("Local upstream file not found: %s", str(LOCAL_UPSTREAM_ICS))
            return None
        data = LOCAL_UPSTREAM_ICS.read_bytes()
        new_hash = _sha256_bytes(data)
        if state.get("mode") == "local" and state.get("sha256") == new_hash:
            safe_log("Upstream (local) unchanged; skipping regeneration.")
            return None
        _write_state({"mode": "local", "sha256": new_hash, "updated_at": int(time.time())})
        safe_log("Detected change in local upstream; proceeding.")
        return data

    # HTTP mode
    session = requests.Session()
    session.headers.update({"User-Agent": "CalendarSplitter/1.0"})

    etag_prev = state.get("etag")
    lm_prev = state.get("last_modified")

    # Try HEAD
    etag_curr = None
    lm_curr = None
    try:
        head = session.head(SOURCE_ICS_URL, allow_redirects=True, timeout=timeout)
        etag_curr = head.headers.get("ETag")
        lm_curr = head.headers.get("Last-Modified")
    except Exception as e:
        safe_warn("HEAD failed; will GET with conditionals. (%s)", str(e))

    headers = {}
    if etag_prev:
        headers["If-None-Match"] = etag_prev
    elif lm_prev:
        headers["If-Modified-Since"] = lm_prev

    try:
        res = session.get(SOURCE_ICS_URL, allow_redirects=True, headers=headers, timeout=timeout)
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

    new_state = {"mode": "http", "sha256": new_hash, "updated_at": int(time.time())}
    if etag_used:
        new_state["etag"] = etag_used
    if lm_used:
        new_state["last_modified"] = lm_used
    _write_state(new_state)

    safe_log("Detected upstream change; proceeding (ETag=%s, Last-Modified=%s).",
             etag_used or "—", lm_used or "—")
    return data

# -----------------------------
# JSON rules
# -----------------------------
def load_course_rules(events_dir: pathlib.Path) -> Dict[str, Dict[str, Any]]:
    """
    Load all *.json in EVENTS_DIR into a dict keyed by course_code.
    """
    rules: Dict[str, Dict[str, Any]] = {}
    if not events_dir.exists():
        safe_warn("EVENTS_DIR does not exist: %s (no rewriting will be applied).", str(events_dir))
        return rules

    for p in sorted(events_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            course = data.get("course_code")
            if not course:
                safe_warn("Ignoring %s (missing course_code).", p.name)
                continue
            rules[course] = data
        except Exception as e:
            safe_warn("Failed to parse %s: %s", p.name, str(e))
    safe_log("Loaded rules for %d course(s).", len(rules))
    return rules

# -----------------------------
# ICS helpers
# -----------------------------
RE_COURSE_IN_SUMMARY = re.compile(r"\(([A-Z0-9\-]{4,})\)")  # e.g. "Lecture 1 - ... (IS1200)"
RE_KTH_COURSE_URL = re.compile(r"/course/([A-Z0-9\-]{4,})/")

RE_LECTURE = re.compile(r"\bLecture\s+(\d+)\b", re.IGNORECASE)
RE_LAB = re.compile(r"\bLab\s+(\d+)\b", re.IGNORECASE)
RE_EXERCISE = re.compile(r"\bExercise\s+(\d+)\b", re.IGNORECASE)

def extract_course_code(summary: str, description: str) -> Optional[str]:
    m = RE_COURSE_IN_SUMMARY.search(summary or "")
    if m:
        return m.group(1)
    m = RE_KTH_COURSE_URL.search(description or "")
    if m:
        return m.group(1)
    return None

def apply_rewrite(summary: str, description: str, course: str, rules: Dict[str, Any]) -> Tuple[str, str]:
    """
    Apply JSON rule to build a nicer title and description.
    """
    if not rules:
        return summary, description or ""

    def find_title_and_module(kind: str, number: int) -> Tuple[Optional[str], Optional[str]]:
        arr = rules.get(kind) or []
        for item in arr:
            if int(item.get("number", -1)) == number:
                return item.get("title"), item.get("module")
        return None, None

    new_summary = summary
    new_desc_parts: List[str] = []

    # Try Lecture/Lab/Exercise numbering in SUMMARY
    number = None
    kind_detected = None
    for rx, kind in [(RE_LECTURE, "lectures"), (RE_LAB, "labs"), (RE_EXERCISE, "exercises")]:
        m = rx.search(summary or "")
        if m:
            try:
                number = int(m.group(1))
                kind_detected = kind
                break
            except Exception:
                pass

    if kind_detected and number is not None:
        title, module = find_title_and_module(kind_detected, number)
        if title:
            # Format: "Lecture x - {title} - COURSE"
            prefix = "Lecture" if kind_detected == "lectures" else ("Lab" if kind_detected == "labs" else "Exercise")
            new_summary = f"{prefix} {number} - {title} - {course}"
        if module:
            new_desc_parts.append(module)

    # Canvas link
    canvas = rules.get("canvas_url")
    if canvas:
        new_desc_parts.append(f"Canvas: {canvas}")

    # Original description last
    if (description or "").strip():
        new_desc_parts.append(description.strip())

    new_description = "\n\n".join(new_desc_parts).strip()
    return new_summary, new_description

def clone_calendar_base(src_cal: Calendar, name: str) -> Calendar:
    dst = Calendar()
    # Preserve common headers if present
    for key in ("PRODID", "VERSION", "CALSCALE", "METHOD", "X-WR-CALDESC"):
        if key in src_cal:
            dst.add(key, src_cal.get(key))
    dst.add("X-WR-CALNAME", vText(name))
    # TTL if present
    if "X-PUBLISHED-TTL" in src_cal:
        dst.add("X-PUBLISHED-TTL", src_cal.get("X-PUBLISHED-TTL"))
    return dst

# -----------------------------
# Token map persistence
# -----------------------------
def load_token_map(path: pathlib.Path) -> Dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_token_map(path: pathlib.Path, mapping: Dict[str, str]) -> None:
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_token(token_map: Dict[str, str], course: str) -> str:
    if course in token_map and token_map[course]:
        return token_map[course]
    # 16 hex chars (64 bits) is fine; you can increase if you want
    new_tok = uuid.uuid4().hex[:16]
    token_map[course] = new_tok
    return new_tok

# -----------------------------
# Main
# -----------------------------
def main():
    upstream = fetch_upstream_if_changed()
    if upstream is None:
        # Nothing to do; succeed quietly
        return 0

    # Parse ICS
    try:
        cal = Calendar.from_ical(upstream)
    except Exception as e:
        safe_error("Failed to parse upstream ICS: %s", str(e))
        return 3

    rules_by_course = load_course_rules(EVENTS_DIR)

    # Bucket events per course
    buckets: Dict[str, Calendar] = {}
    count_total = 0
    count_kept = 0

    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        count_total += 1

        summary = str(comp.get("SUMMARY", "") or "")
        description = str(comp.get("DESCRIPTION", "") or "")
        course = extract_course_code(summary, description)
        if not course:
            # Uncategorized: skip or route to a special bucket if you want
            continue

        # Prepare course calendar if missing
        if course not in buckets:
            buckets[course] = clone_calendar_base(cal, name=course)

        # Copy event & apply rewrite
        new_ev = Event()
        for key, val in comp.property_items():
            # We'll overwrite SUMMARY/DESCRIPTION after copying
            if key in ("SUMMARY", "DESCRIPTION"):
                continue
            new_ev.add(key, val)

        new_summary, new_description = apply_rewrite(summary, description, course, rules_by_course.get(course, {}))
        new_ev.add("SUMMARY", vText(new_summary))
        if new_description:
            new_ev.add("DESCRIPTION", vText(new_description))
        else:
            # Ensure DESCRIPTION exists (some clients expect it)
            new_ev.add("DESCRIPTION", vText(description or ""))

        buckets[course].add_component(new_ev)
        count_kept += 1

    safe_log("Parsed %d events; bucketed %d across %d course(s).", count_total, count_kept, len(buckets))

    # Write per-course feeds
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    token_map = load_token_map(TOKEN_MAP_PATH)

    written = 0
    for course, ccal in sorted(buckets.items()):
        tok = ensure_token(token_map, course)
        out_path = FEEDS_DIR / f"{course}--{tok}.ics"
        try:
            out_path.write_bytes(ccal.to_ical())
            written += 1
        except Exception as e:
            safe_warn("Failed writing %s: %s", out_path.name, str(e))

    # Persist token map (do not log its contents)
    save_token_map(TOKEN_MAP_PATH, token_map)
    safe_log("Wrote %d course feeds into %s.", written, str(FEEDS_DIR))

    return 0


if __name__ == "__main__":
    try:
        rc = main()
        sys.exit(rc)
    except Exception as e:
        # Keep errors terse; enable DEBUG locally if you want tracebacks
        safe_error("Fatal error: %s", str(e))
        sys.exit(1)
