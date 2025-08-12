import logging, re, sys

RE_UUID = re.compile(r"\b[0-9a-fA-F]{16,}\b|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[089abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b")
RE_QS = re.compile(r"(\?.*)$")
RE_FEED = re.compile(r"(/feeds/[A-Z0-9\-_.]+)--([0-9a-fA-F]{8,})\.ics\b")

def _redact(s: str) -> str:
    return RE_UUID.sub("***", RE_FEED.sub(r"\1--***.ics", RE_QS.sub("", s)))

def setup_logging(level="INFO"):
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format="%(levelname)s: %(message)s", stream=sys.stdout)

def safe_log(msg, *a): logging.info(_redact(msg % a if a else msg))
def safe_warn(msg, *a): logging.warning(_redact(msg % a if a else msg))
def safe_error(msg, *a): logging.error(_redact(msg % a if a else msg))
