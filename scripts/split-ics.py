import os, re, json, uuid, requests
from pathlib import Path
from icalendar import Calendar

ROOT = Path(__file__).resolve().parents[1]

# Output / state
FEEDS_DIR = Path(os.environ.get("FEEDS_DIR", ROOT / "docs" / "feeds"))
FEEDS_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_MAP_PATH = Path(os.environ.get("TOKEN_MAP_PATH", ROOT / "token_map.json"))

# Optional: rules for course split
CONFIG = ROOT / "config" / "rules.json"

# NEW: directory with rewrite configs (multiple JSON files)
EVENTS_DIR = Path(os.environ.get("EVENTS_DIR", ROOT / "events"))

# Patterns for course detection
COURSE_PAREN_REGEX = re.compile(r"\(([A-Z]{2,}\d{3,})\)\s*$", re.IGNORECASE)
COURSE_URL_REGEX   = re.compile(r"/course/([A-Za-z0-9]{2,}\d{3,})/")
PROGRAM_URL_REGEX  = re.compile(r"/program/([A-Za-z0-9-]{2,})/")

def load_json(p: Path, default=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default if default is not None else {})

def save_json(p: Path, data):
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def text(v): return "" if v is None else str(v)

def normalize_code(code: str) -> str:
    return code.upper().strip()

def infer_code(vevent, rules):
    summary = text(vevent.get("SUMMARY"))
    desc = text(vevent.get("DESCRIPTION"))

    m = COURSE_PAREN_REGEX.search(summary or "")
    if m: return normalize_code(m.group(1))

    m = COURSE_URL_REGEX.search(desc or "")
    if m: return normalize_code(m.group(1))

    m = PROGRAM_URL_REGEX.search(desc or "")
    if m: return f"PROGRAM-{normalize_code(m.group(1))}"

    for rule in rules.get("custom_rules", []):
        rx = re.compile(rule.get("regex", ""), re.IGNORECASE)
        code = rule.get("code")
        if code and (rx.search(summary or "") or rx.search(desc or "")):
            return normalize_code(code)

    return "UNCATEGORIZED"

def new_calendar(src_cal, prodid="-//Calendar Splitter//EN"):
    cal = Calendar()
    cal.add("PRODID", prodid)
    cal.add("VERSION", "2.0")
    if src_cal.get("X-WR-TIMEZONE"):
        cal.add("X-WR-TIMEZONE", src_cal.get("X-WR-TIMEZONE"))
    return cal

def copy_vtimezones(src_cal, dst_cal):
    for comp in src_cal.subcomponents:
        if getattr(comp, "name", None) == "VTIMEZONE":
            dst_cal.add_component(comp)

def ensure_token(code, token_map):
    tok = token_map.get(code)
    if not tok:
        tok = uuid.uuid4().hex[:16]
        token_map[code] = tok
    return tok

def fetch_upstream():
    url = os.environ.get("SOURCE_ICS_URL", "").strip()
    if url:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.content
    local_file = ROOT / "personal.ics"
    if local_file.exists():
        return local_file.read_bytes()
    raise SystemExit("No SOURCE_ICS_URL provided and no 'personal.ics' found in project root.")

# -------------------- NEW: Generic rewrite engine ----------------------------

class RewriteRule:
    """
    Holds one JSON rule set:
      - course, canvas
      - compiled summary regex (one capturing group => number)
      - title & description templates
      - number map
    """
    def __init__(self, course, summary_regex, require_course_in_summary, title_tmpl, desc_tmpl, items, canvas=None):
        self.course = (course or "").upper().strip()
        self.canvas = (canvas or "").strip()
        self.rx = re.compile(summary_regex, re.IGNORECASE)
        self.require_course_in_summary = bool(require_course_in_summary)
        self.title_tmpl = title_tmpl or "{old_summary}"
        self.desc_tmpl = desc_tmpl or "{old_desc}"
        self.items = {
            int(i["number"]): {
                "title": (i.get("title") or "").strip(),
                "module": (i.get("module") or "").strip()
            }
            for i in items if "number" in i
        }

    def _tidy(self, s: str) -> str:
        # Drop lines that end up like "Canvas: " when {canvas} is empty and collapse extra blank lines
        lines = [ln for ln in (s or "").splitlines()]
        cleaned = []
        for ln in lines:
            if ln.strip().lower().startswith("canvas:") and ln.strip().lower() == "canvas:":
                continue
            cleaned.append(ln)
        out = "\n".join(cleaned).strip()
        while "\n\n\n" in out:
            out = out.replace("\n\n\n", "\n\n")
        return out

    def maybe_apply(self, vevent, inferred_course):
        if inferred_course != self.course:
            return False

        summary = str(vevent.get("SUMMARY") or "")
        if self.require_course_in_summary and f"({self.course}" not in summary.upper():
            return False

        m = self.rx.search(summary)
        if not m:
            return False

        try:
            n = int(m.group(1))
        except Exception:
            return False

        if n not in self.items:
            return False

        data = self.items[n]
        ctx = {
            "n": n,
            "title": data.get("title", ""),
            "module": data.get("module", ""),
            "course": self.course,
            "canvas": self.canvas,
            "old_desc": str(vevent.get("DESCRIPTION") or "").strip(),
            "old_summary": summary
        }

        new_summary = self.title_tmpl.format(**ctx).strip()
        new_desc = self._tidy(self.desc_tmpl.format(**ctx))

        vevent["SUMMARY"] = new_summary
        vevent["DESCRIPTION"] = new_desc
        return True

def load_rewrite_rules():
    rules = []
    if EVENTS_DIR.exists():
        for p in sorted(EVENTS_DIR.glob("*.json")):
            try:
                spec = load_json(p, default={})
                course = spec.get("course")
                match = spec.get("match", {})
                rx = match.get("summary_regex")
                req = match.get("require_course_in_summary", True)
                title_tmpl = spec.get("title_template")
                desc_tmpl = spec.get("description_template")
                items = spec.get("items", [])
                canvas = spec.get("canvas")
                if course and rx and items:
                    rules.append(RewriteRule(course, rx, req, title_tmpl, desc_tmpl, items, canvas=canvas))
            except Exception as e:
                print(f"[warn] skipping {p.name}: {e}")
    return rules

# -----------------------------------------------------------------------------

def main():
    split_rules = load_json(CONFIG, default={"custom_rules": []})
    token_map = load_json(TOKEN_MAP_PATH, default={})
    rewrite_rules = load_rewrite_rules()

    raw = fetch_upstream()
    src_cal = Calendar.from_ical(raw)

    # Pass 1: optionally rewrite events using all rule files
    for comp in list(src_cal.subcomponents):
        if getattr(comp, "name", None) != "VEVENT":
            continue
        inferred = infer_code(comp, split_rules)
        # Try every rewrite rule (only the first that matches applies; remove break to stack)
        for rr in rewrite_rules:
            if rr.maybe_apply(comp, inferred):
                break

    # Pass 2: split into calendars by course/program
    buckets = {}
    for comp in src_cal.subcomponents:
        if getattr(comp, "name", None) != "VEVENT":
            continue
        code = infer_code(comp, split_rules)
        buckets.setdefault(code, new_calendar(src_cal)).add_component(comp)

    for cal in buckets.values():
        copy_vtimezones(src_cal, cal)

    for code, cal in buckets.items():
        token = ensure_token(code, token_map)
        (FEEDS_DIR / f"{code}--{token}.ics").write_bytes(cal.to_ical())

    save_json(TOKEN_MAP_PATH, token_map)

    base = os.environ.get("BASE_URL", "https://calendar.example.com/feeds")
    for code, tok in token_map.items():
        print(f"{code}: {base}/{code}--{tok}.ics")

if __name__ == "__main__":
    main()
