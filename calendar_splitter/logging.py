"""Logging with automatic redaction of sensitive data."""

from __future__ import annotations

import logging
import re
import sys

# Redaction patterns
_RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{16,}\b|"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}"
    r"-[089abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_RE_QUERY_STRING = re.compile(r"(\?.*)$")
_RE_FEED_PATH = re.compile(r"(/feeds/[A-Z0-9\-_.]+)--([0-9a-fA-F]{8,})\.ics\b")


def redact(text: str) -> str:
    """Remove sensitive tokens from log text."""
    text = _RE_QUERY_STRING.sub("", text)
    text = _RE_FEED_PATH.sub(r"\1--***.ics", text)
    return _RE_UUID.sub("***", text)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with redaction-safe formatting."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)
