# calendar-splitter

Split a combined university calendar (ICS) into per-course feeds with enriched summaries and
descriptions, and generate additional feeds — study blocks, training, meal prep — from declarative
specs that schedule around whatever is already in the calendar.

Built for KTH calendars but works with any ICS source where events contain course codes.

## How it works

1. **Fetch** — downloads the upstream ICS (or reads a local file), skipping if unchanged (ETag/SHA256 caching)
2. **Parse** — extracts events and detects course codes from summaries/descriptions
3. **Classify** — matches events to configured event types using pattern + strategy rules
4. **Rewrite** — applies summary/description templates with lecture titles, modules, and Canvas links
5. **Generate** — expands `specs/*.json` into events, using the upstream events as a busy set
6. **Write** — outputs one `.ics` feed per course and per generated spec, with tokenized filenames

## Generated feeds

Course feeds are reshaped from upstream. Study blocks, workouts and meal prep have no upstream
event, so they are authored from a spec in `specs/`:

```json
{
  "feed": "GYM",
  "name": "Training",
  "timezone": "Europe/Stockholm",
  "priority": 30,
  "color": "#1a6467",
  "rules": [
    { "kind": "recurring", "summary": "Gym — {rotate}",
      "from": "2026-08-24", "until": "2026-10-16",
      "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
      "window": ["17:00", "21:00"], "duration_min": 75, "per_week": 3,
      "rotate": ["Day A (upper push)", "Day B (lower + core)"] },

    { "kind": "fixed", "summary": "1MA462 exam",
      "start": "2026-10-17T12:00", "end": "2026-10-17T17:00" }
  ]
}
```

### Rule kinds

**`fixed`** — an event at an exact time. Needs `start` and `end` (ISO, naive times take the feed's
timezone). Use for exams, deadlines and registration windows.

**`recurring`** — a rule the scheduler places for you. Needs `from`, `until`, `days`, and takes
`window`, `duration_min`, `per_week`, `rotate`. For each week it walks `days` in order and takes the
first free slot inside `window`, stepping in 15-minute increments, until `per_week` are placed.

### Conflict avoidance

`avoid_conflicts` (default `true`) keeps a rule off anything already scheduled: upstream lectures,
events from earlier specs, and earlier rules within the same spec. It is first-fit, not an
optimiser — it will not reshuffle existing placements to fit one more in. When a week cannot be
filled it logs a warning naming the rule and the week rather than failing.

`priority` (default 50) decides which spec claims slots first, lowest first. Without it the order
would be alphabetical, so renaming a file would silently reshuffle the schedule.

`color` (optional, CSS name or `#rrggbb`) is emitted as both `X-APPLE-CALENDAR-COLOR` and
`X-OUTLOOK-COLOR`, so subscribers get a distinct colour per feed.

## Dropped events

An event that never reaches a feed is the failure hardest to notice, so every one is recorded on
`PipelineResult.dropped` as `(summary, reason)`. Events filtered by a course config log at INFO;
events with no detectable course code log at DEBUG, since a personal calendar is full of them.

## Course config format

Each course is a JSON file (e.g. `courses/IS1200.json`):

```json
{
  "course_code": "IS1200",
  "course_name": "Computer Hardware Engineering",
  "canvas_url": "https://canvas.kth.se/courses/56261",
  "detection": {
    "require_code_in_summary": true,
    "course_code_pattern": "\\bIS1200\\b"
  },
  "templates": {
    "summary": "{kind} {n} - {title} - {course}",
    "description": "{module}\nCanvas: {canvas}\n\n{original}"
  },
  "event_types": [
    {
      "type": "lecture",
      "display_name": "Lecture",
      "patterns": ["\\bLecture\\s*(\\d+)\\b"],
      "items": [
        { "number": 1, "title": "Course Introduction", "module": "Module 1" }
      ]
    }
  ]
}
```

### Template variables

**Summary:** `{kind}`, `{n}`, `{title}`, `{course}`

**Description:** `{module}`, `{canvas}`, `{original}`

### Match strategies

Items can use `match` rules to filter events by time, location, description, or URL:

```json
{
  "number": 1,
  "title": "Intro",
  "match": [
    { "strategy": "time", "priority": 1, "day": "monday",
      "start_time": "13:00", "end_time": "15:00", "timezone": "Europe/Stockholm" }
  ]
}
```

Available strategies: `time`, `description`, `location`, `url`, `all`, `any`.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `FEEDS_DIR` | yes | Output directory for generated `.ics` feeds |
| `TOKEN_MAP_PATH` | yes | Path to the token mapping JSON |
| `SOURCE_ICS_URL` | no | Upstream calendar URL (falls back to local file) |
| `LOCAL_UPSTREAM_ICS` | no | Local ICS fallback path (default: `personal.ics`) |
| `COURSES_DIR` | no | Directory of course config JSONs (default: `courses`) |
| `SPECS_DIR` | no | Directory of generated-feed specs (default: `specs`) |
| `UPSTREAM_STATE_PATH` | no | Cache state file (default: `_feeds/upstream_state.json`) |
| `LOG_LEVEL` | no | Logging level (default: `INFO`) |

## Usage

```bash
# Install
pip install -e .

# Run
FEEDS_DIR=_feeds/feeds TOKEN_MAP_PATH=_feeds/tokens.json python -m calendar_splitter
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint and type check
ruff check calendar_splitter/
mypy calendar_splitter/
```

## Project structure

```
calendar_splitter/
├── __main__.py          # python -m entry point
├── cli.py               # CLI setup from env vars
├── config/              # Course config loading + validation
├── core/
│   ├── models.py        # Dataclasses (Event, CourseConfig, etc.)
│   ├── parser.py        # ICS parsing + course code detection
│   ├── rewriter.py      # Template-based event rewriting
│   └── writer.py        # ICS output generation
├── exceptions.py        # Custom exception hierarchy
├── fetch.py             # HTTP + local fetch with caching
├── logging.py           # Log redaction (tokens, UUIDs, query strings)
├── pipeline.py          # Orchestration: fetch → parse → classify → rewrite → write
├── strategies/          # Strategy evaluation engine
└── tokens.py            # Per-course feed URL token store
```
