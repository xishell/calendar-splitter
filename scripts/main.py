#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from typing import cast
from .fetch import fetch_upstream_if_changed
from .log_sanitize import safe_error, safe_log, setup_logging
from .rules import load_course_rules_dir
from .split import split_and_write
from .tokens import load_token_map, save_token_map


def _env_path(name: str, default: str | None = None, required: bool = False) -> Path | None:
    v = os.environ.get(name, default)
    if required and not v:
        safe_error("%s is required.", name)
        sys.exit(2)
    return Path(v) if v else None


def main() -> int:
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

    feeds_dir = _env_path("FEEDS_DIR", required=True)
    token_map_path = _env_path("TOKEN_MAP_PATH", required=True)
    events_dir = _env_path("EVENTS_DIR", "events")
    state_path = _env_path("UPSTREAM_STATE_PATH", "_feeds/upstream_state.json")

    if feeds_dir is None or token_map_path is None or state_path is None:
        safe_error("Missing required paths.")
        return 2

    source_url = os.environ.get("SOURCE_ICS_URL", "")
    local_fallback = cast(Path, _env_path("LOCAL_UPSTREAM_ICS", "personal.ics"))

    upstream = fetch_upstream_if_changed(source_url, local_fallback, state_path)
    if upstream is None:
        # Nothing changed; succeed quietly
        return 0

    rules_by_course = {}
    if events_dir and events_dir.exists():
        rules_by_course = load_course_rules_dir(events_dir)

    token_map = load_token_map(token_map_path)

    written = split_and_write(upstream, rules_by_course, feeds_dir, token_map)
    save_token_map(token_map_path, token_map)
    safe_log("Wrote %d feeds into %s.", written, str(feeds_dir))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        safe_error("Fatal error: %s", str(e))
        sys.exit(1)
