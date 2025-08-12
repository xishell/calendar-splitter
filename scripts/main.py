#!/usr/bin/env python3
import os, sys, pathlib
from log_sanitize import safe_error, safe_log, setup_logging
from fetch import fetch_upstream_if_changed
from rules import load_course_rules_dir
from split import split_and_write
from tokens import load_token_map, save_token_map

def env_path(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        safe_error("%s is required.", name); sys.exit(2)
    return pathlib.Path(v) if v else None

def main():
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
    FEEDS_DIR = env_path("FEEDS_DIR", required=True).resolve()
    TOKEN_MAP_PATH = env_path("TOKEN_MAP_PATH", required=True).resolve()
    EVENTS_DIR = env_path("EVENTS_DIR", "events")
    upstream = fetch_upstream_if_changed()
    if upstream is None:
        return 0
    rules_by_course = load_course_rules_dir(EVENTS_DIR) if EVENTS_DIR else {}
    token_map = load_token_map(TOKEN_MAP_PATH)
    written = split_and_write(upstream, rules_by_course, FEEDS_DIR, token_map)
    save_token_map(TOKEN_MAP_PATH, token_map)
    safe_log("Wrote %d feeds into %s.", written, str(FEEDS_DIR))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        safe_error("Fatal error: %s", str(e)); sys.exit(1)
