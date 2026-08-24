"""Remove feeds for courses that have finished.

A feed nobody writes any more still sits on the site and still appears in the
README as something to subscribe to. Age is the safe signal: a checkout resets
mtimes, so the question is when git last recorded a change to the file.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from calendar_splitter.logging import get_logger

_log = get_logger(__name__)

# ten months: long enough that a course is unambiguously over
DEFAULT_MAX_AGE_DAYS = 304


@dataclass(frozen=True)
class Candidate:
    """A published feed and how long since git last saw it change."""

    path: Path
    feed: str
    age_days: int


def feed_name(path: Path) -> str:
    """FEED--token.ics -> FEED."""
    return path.name.split("--")[0]


def last_changed(path: Path, repo: Path) -> datetime | None:
    """When git last recorded a change to this file, or None if it has no history."""
    # -C moves git's cwd, so a path relative to ours would silently match nothing
    out = subprocess.run(
        ["git", "-C", str(repo.resolve()), "log", "-1", "--format=%ct", "--",
         str(path.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    stamp = out.stdout.strip()
    if out.returncode != 0 or not stamp:
        return None
    return datetime.fromtimestamp(int(stamp), tz=UTC)


def find_stale(
    feeds_dir: Path, repo: Path, max_age_days: int, now: datetime | None = None
) -> list[Candidate]:
    """Published feeds git has not seen change for longer than max_age_days."""
    now = now or datetime.now(UTC)
    stale = []
    for path in sorted(feeds_dir.glob("*.ics")):
        changed = last_changed(path, repo)
        if changed is None:
            # never committed, so it is not ours to judge
            continue
        age = (now - changed).days
        if age > max_age_days:
            stale.append(Candidate(path, feed_name(path), age))
    return stale


@dataclass(frozen=True)
class PruneConfig:
    """Where the published feeds live and how old is too old."""

    feeds_dir: Path
    token_map_path: Path
    repo: Path
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
    dry_run: bool = False


def prune(config: PruneConfig, now: datetime | None = None) -> list[Candidate]:
    """Delete stale feeds and drop their tokens so the README stops listing them."""
    stale = find_stale(config.feeds_dir, config.repo, config.max_age_days, now)
    if not stale:
        _log.info("No feeds older than %d days.", config.max_age_days)
        return []

    for c in stale:
        _log.info("%s %s (%d days since last change)",
                  "Would remove" if config.dry_run else "Removing", c.feed, c.age_days)
    if config.dry_run:
        return stale

    tokens = {}
    if config.token_map_path.exists():
        tokens = json.loads(config.token_map_path.read_text(encoding="utf-8"))

    for c in stale:
        c.path.unlink(missing_ok=True)
        tokens.pop(c.feed, None)

    if config.token_map_path.exists():
        config.token_map_path.write_text(
            json.dumps(tokens, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _log.info("Removed %d feed(s).", len(stale))
    return stale
