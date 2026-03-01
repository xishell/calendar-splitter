"""Command-line entry point."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from calendar_splitter.logging import get_logger, setup_logging
from calendar_splitter.pipeline import PipelineConfig, run_pipeline

_log = get_logger(__name__)


def main() -> int:
    """Run calendar-splitter from environment variables."""
    load_dotenv()

    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

    feeds_dir = os.environ.get("FEEDS_DIR", "")
    token_map_path = os.environ.get("TOKEN_MAP_PATH", "")

    if not feeds_dir:
        _log.error("FEEDS_DIR is required.")
        return 2
    if not token_map_path:
        _log.error("TOKEN_MAP_PATH is required.")
        return 2

    config = PipelineConfig(
        source_url=os.environ.get("SOURCE_ICS_URL", ""),
        local_fallback=Path(os.environ.get("LOCAL_UPSTREAM_ICS", "personal.ics")),
        state_path=Path(os.environ.get("UPSTREAM_STATE_PATH", "_feeds/upstream_state.json")),
        courses_dir=Path(os.environ.get("COURSES_DIR", "courses")),
        feeds_dir=Path(feeds_dir),
        token_map_path=Path(token_map_path),
        timeout=int(os.environ.get("FETCH_TIMEOUT", "30")),
    )

    try:
        result = run_pipeline(config)
        if result.skipped:
            _log.info("Nothing changed; no feeds written.")
        else:
            _log.info("Done. Wrote %d feed(s).", len(result.feeds))
        return 0
    except Exception as exc:
        _log.error("Fatal error: %s", exc)
        return 1
