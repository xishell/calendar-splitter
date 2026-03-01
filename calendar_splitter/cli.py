"""Command-line entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from calendar_splitter.logging import get_logger, setup_logging
from calendar_splitter.pipeline import PipelineConfig, run_pipeline
from calendar_splitter.readme import generate_readme

_log = get_logger(__name__)


def _run_generate_readme() -> int:
    """Generate README.md for the feeds repository."""
    token_map_path = os.environ.get("TOKEN_MAP_PATH", "")
    base_url = os.environ.get("BASE_URL", "")
    readme_dir = os.environ.get("README_DIR", "")

    if not token_map_path or not base_url or not readme_dir:
        _log.error("TOKEN_MAP_PATH, BASE_URL, and README_DIR are required.")
        return 2

    root = Path(readme_dir)
    generate_readme(
        token_map_path=Path(token_map_path),
        base_url=base_url,
        header_path=root / "README.header.md",
        footer_path=root / "README.footer.md",
        output_path=root / "README.md",
    )
    _log.info("Generated README.md in %s", readme_dir)
    return 0


def main() -> int:
    """Run calendar-splitter from environment variables."""
    load_dotenv()
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

    if "--generate-readme" in sys.argv:
        return _run_generate_readme()

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
