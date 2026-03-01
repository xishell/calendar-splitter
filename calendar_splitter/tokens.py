"""Token store for per-course feed URL tokens."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


class TokenStore:
    """Manages a persistent mapping of course codes to feed URL tokens."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._map: dict[str, str] = {}

    def load(self) -> None:
        """Load tokens from disk."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._map = data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            self._map = {}

    def get_or_create(self, course: str) -> str:
        """Return existing token or create a new one."""
        existing = self._map.get(course)
        if existing:
            return existing
        token = uuid.uuid4().hex[:16]
        self._map[course] = token
        return token

    def save(self) -> None:
        """Persist tokens to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._map, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @property
    def map(self) -> dict[str, str]:
        """Read-only access to the token mapping."""
        return dict(self._map)
