from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict


def load_token_map(path: Path) -> Dict[str, str]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def save_token_map(path: Path, mapping: Dict[str, str]) -> None:
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_token(token_map: Dict[str, str], course: str) -> str:
    if course in token_map and token_map[course]:
        return token_map[course]
    new_tok = uuid.uuid4().hex[:16]
    token_map[course] = new_tok
    return new_tok
