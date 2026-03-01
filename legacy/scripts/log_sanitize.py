import logging
import re
import sys

# Redaction patterns: UUIDs/long hex, query strings, tokenized feed paths
RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{16,}\b|"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[089abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
RE_QS = re.compile(r"(\?.*)$")
RE_FEED = re.compile(r"(/feeds/[A-Z0-9\-_.]+)--([0-9a-fA-F]{8,})\.ics\b")


def _redact(s: str) -> str:
    s = RE_QS.sub("", s)
    s = RE_FEED.sub(r"\1--***.ics", s)
    s = RE_UUID.sub("***", s)
    return s


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
    )


def safe_log(msg: str, *a: object) -> None:
    logging.info(_redact(msg % a if a else msg))


def safe_warn(msg: str, *a: object) -> None:
    logging.warning(_redact(msg % a if a else msg))


def safe_error(msg: str, *a: object) -> None:
    logging.error(_redact(msg % a if a else msg))
