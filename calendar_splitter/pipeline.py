"""Pipeline orchestration: fetch -> parse -> classify -> rewrite -> write."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from icalendar import Calendar

from calendar_splitter.config import load_courses_from_dir
from calendar_splitter.core.models import CourseConfig, FeedResult
from calendar_splitter.core.parser import detect_course_code, parse_calendar, parse_calendar_raw
from calendar_splitter.core.rewriter import rewrite_event
from calendar_splitter.core.writer import (
    build_event,
    build_generated_event,
    clone_calendar_base,
    new_calendar,
)
from calendar_splitter.fetch import fetch_upstream
from calendar_splitter.generate import generate_feed, load_specs, slug
from calendar_splitter.logging import get_logger, redact
from calendar_splitter.strategies import classify_event
from calendar_splitter.tokens import TokenStore

_log = get_logger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for a pipeline run."""

    source_url: str = ""
    local_fallback: Path = Path("personal.ics")
    state_path: Path = Path("_feeds/upstream_state.json")
    courses_dir: Path = Path("courses")
    feeds_dir: Path = Path("_feeds")
    token_map_path: Path = Path("_feeds/tokens.json")
    specs_dir: Path = Path("specs")
    # minutes each way to campus; upstream lectures reserve this around themselves
    campus_travel_min: int = 0
    # course codes still on the timetable but not actually attended
    busy_exclude: tuple[str, ...] = ()
    timeout: int = 30


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    feeds: list[FeedResult] = field(default_factory=list)
    total_events: int = 0
    kept_events: int = 0
    filtered_events: int = 0
    generated_events: int = 0
    skipped: bool = False
    # summary + reason for every event that did not make it into a feed
    dropped: list[tuple[str, str]] = field(default_factory=list)


def _add_generated_feeds(
    config: PipelineConfig,
    events: list[Any],
    buckets: dict[str, tuple[Calendar, list[tuple[str, str]]]],
    result: PipelineResult,
) -> None:
    """Expand specs into feeds, treating upstream events as the busy set."""
    pad = timedelta(minutes=config.campus_travel_min)
    skip = {c.upper() for c in config.busy_exclude}
    busy = []
    dropped = 0
    for e in events:
        if not (e.start and e.end):
            continue
        code = detect_course_code(e.summary, e.description)
        if code and code.upper() in skip:
            dropped += 1
            continue
        busy.append((e.start - pad, e.end + pad))
    if dropped:
        _log.info("Ignored %d event(s) from %s when placing generated feeds.",
                  dropped, ", ".join(sorted(skip)))
    for spec in load_specs(config.specs_dir):
        slots = generate_feed(spec, busy)
        if not slots:
            continue
        cal = new_calendar(spec.name or spec.feed, color=spec.color)
        seen: dict[str, int] = {}
        for slot in slots:
            # a block that shifts within its day must keep its uid, or every subscriber
            # sees the old one deleted and a new one added on each run
            base = f"{spec.feed.lower()}-{slot.start:%Y%m%d}-{slug(slot.summary)}"
            n = seen[base] = seen.get(base, -1) + 1
            cal.add_component(build_generated_event(f"{base}-{n}@calendar-splitter", slot))
        buckets[spec.feed] = (cal, [])
        result.generated_events += len(slots)


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Execute the full pipeline."""
    # Fetch
    upstream = fetch_upstream(
        source_url=config.source_url or None,
        local_fallback=config.local_fallback,
        state_path=config.state_path,
        timeout=config.timeout,
    )
    if upstream is None:
        _log.info("Upstream unchanged, nothing to do.")
        return PipelineResult(skipped=True)

    # Load configs
    courses = load_courses_from_dir(config.courses_dir)

    # Parse
    events = parse_calendar(upstream)
    raw_cal = parse_calendar_raw(upstream)

    # Classify + rewrite
    buckets: dict[str, tuple[Calendar, list[tuple[str, str]]]] = {}
    result = PipelineResult(total_events=len(events))

    for event in events:
        course_code = detect_course_code(event.summary, event.description)
        if not course_code:
            result.dropped.append((event.summary, "no course code detected"))
            continue

        course_config = courses.get(course_code)
        if course_config is None:
            # No config for this course — create a default passthrough
            course_config = CourseConfig(course_code=course_code)

        classified = classify_event(event, course_code, course_config)
        if classified is None:
            result.filtered_events += 1
            result.dropped.append((event.summary, f"{course_code}: no matching event type"))
            continue

        new_summary, new_desc = rewrite_event(classified, course_config)
        ical_event = build_event(classified, new_summary, new_desc)

        if course_code not in buckets:
            buckets[course_code] = (clone_calendar_base(raw_cal, course_code), [])
        cal, _ = buckets[course_code]
        cal.add_component(ical_event)
        result.kept_events += 1

    _log.info(
        "Parsed %d events; kept %d, filtered %d across %d courses.",
        result.total_events,
        result.kept_events,
        result.filtered_events,
        len(buckets),
    )
    # a silently vanishing event is the failure mode that is hardest to notice
    for summary, reason in result.dropped:
        if "no matching event type" in reason:
            _log.info("Filtered %r (%s)", summary, reason)
        else:
            _log.debug("Dropped %r: %s", summary, reason)

    _add_generated_feeds(config, events, buckets, result)

    # Write feeds
    token_store = TokenStore(config.token_map_path)
    token_store.load()

    config.feeds_dir.mkdir(parents=True, exist_ok=True)

    for feed_name, (cal, _) in sorted(buckets.items()):
        token = token_store.get_or_create(feed_name)
        out_path = config.feeds_dir / f"{feed_name}--{token}.ics"
        try:
            out_path.write_bytes(cal.to_ical())
            event_count = sum(1 for c in cal.walk() if c.name == "VEVENT")
            result.feeds.append(FeedResult(
                course_code=feed_name,
                path=str(out_path),
                event_count=event_count,
            ))
        except Exception as exc:
            _log.warning("Failed writing %s: %s", redact(out_path.name), exc)

    token_store.save()
    _log.info("Wrote %d feeds into %s.", len(result.feeds), redact(str(config.feeds_dir)))

    return result
