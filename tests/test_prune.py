"""Tests for removing feeds whose courses have finished."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from calendar_splitter.prune import PruneConfig, feed_name, find_stale, last_changed, prune

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def _git(repo: Path, *args: str, when: datetime | None = None) -> None:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if when:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    """A feeds repo with one fresh feed and one abandoned nine months ago."""
    _git(tmp_path, "init", "-q", "-b", "main")
    feeds = tmp_path / "docs" / "feeds"
    feeds.mkdir(parents=True)

    (feeds / "OLD--aaa.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "old", when=NOW - timedelta(days=400))

    (feeds / "NEW--bbb.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "new", when=NOW - timedelta(days=2))

    (tmp_path / "token_map.json").write_text(json.dumps({"OLD": "aaa", "NEW": "bbb"}))
    return tmp_path


def _config(repo, **kw):
    return PruneConfig(
        feeds_dir=repo / "docs" / "feeds",
        token_map_path=repo / "token_map.json",
        repo=repo,
        **kw,
    )


def test_feed_name_strips_the_token():
    assert feed_name(Path("docs/feeds/IK1203--6ec8325c89524db9.ics")) == "IK1203"


def test_last_changed_reads_git_not_mtime(repo):
    old = last_changed(repo / "docs" / "feeds" / "OLD--aaa.ics", repo)
    assert old is not None
    assert (NOW - old).days > 300


def test_untracked_file_is_left_alone(repo):
    stray = repo / "docs" / "feeds" / "STRAY--ccc.ics"
    stray.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    assert last_changed(stray, repo) is None
    assert [c.feed for c in find_stale(repo / "docs" / "feeds", repo, 304, NOW)] == ["OLD"]


def test_finds_only_the_abandoned_feed(repo):
    stale = find_stale(repo / "docs" / "feeds", repo, 304, NOW)
    assert [c.feed for c in stale] == ["OLD"]
    assert stale[0].age_days == 400


def test_prune_removes_the_file_and_its_token(repo):
    prune(_config(repo), now=NOW)
    assert not (repo / "docs" / "feeds" / "OLD--aaa.ics").exists()
    assert (repo / "docs" / "feeds" / "NEW--bbb.ics").exists()
    assert json.loads((repo / "token_map.json").read_text()) == {"NEW": "bbb"}


def test_dry_run_reports_without_deleting(repo):
    reported = prune(_config(repo, dry_run=True), now=NOW)
    assert [c.feed for c in reported] == ["OLD"]
    assert (repo / "docs" / "feeds" / "OLD--aaa.ics").exists()
    assert "OLD" in json.loads((repo / "token_map.json").read_text())


def test_a_longer_cutoff_spares_everything(repo):
    assert prune(_config(repo, max_age_days=500), now=NOW) == []
    assert (repo / "docs" / "feeds" / "OLD--aaa.ics").exists()


def test_dropping_the_token_is_what_removes_it_from_the_readme(repo):
    """The README is built from the token map, so the entry must go too."""
    prune(_config(repo), now=NOW)
    assert "OLD" not in (repo / "token_map.json").read_text()


def test_relative_paths_resolve_against_the_repo(repo, monkeypatch, tmp_path):
    """git -C moves git's cwd; a path relative to ours must still be found."""
    monkeypatch.chdir(tmp_path.parent)
    rel = Path(repo.name) if repo.parent == tmp_path.parent else repo
    stale = find_stale(rel / "docs" / "feeds", rel, 304, NOW)
    assert [c.feed for c in stale] == ["OLD"]
