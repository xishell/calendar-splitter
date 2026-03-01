"""Generate README.md for the feeds repository."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def generate_readme(
    token_map_path: Path,
    base_url: str,
    header_path: Path | None = None,
    footer_path: Path | None = None,
    output_path: Path | None = None,
) -> str:
    """Build a README with a feed table from the token map.

    Args:
        token_map_path: Path to token_map.json.
        base_url: Base URL for feed links (e.g. "https://cal.steffensens.io/feeds").
        header_path: Optional path to README.header.md template.
        footer_path: Optional path to README.footer.md template.
        output_path: If provided, write the README to this path.

    Returns:
        The generated README content.
    """
    tokens: dict[str, str] = {}
    try:
        raw = json.loads(token_map_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            tokens = raw
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    base_url = base_url.rstrip("/")
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Build table
    rows = []
    for course, token in sorted(tokens.items()):
        filename = f"{course}--{token}.ics"
        url = f"{base_url}/{filename}"
        rows.append(f"| `{course}` | `{token}` | {url} |")

    table = "| Course | Token | Feed URL |\n|---|---|---|\n"
    table += "\n".join(rows)

    # Assemble from header template or default
    if header_path and header_path.exists():
        header = header_path.read_text(encoding="utf-8")
        content = header.replace(
            "<!-- BEGIN FEED TABLE -->\n<!-- END FEED TABLE -->",
            f"<!-- BEGIN FEED TABLE -->\n{table}\n<!-- END FEED TABLE -->",
        )
    else:
        content = (
            f"# Calendar Feeds\n\n"
            f"<!-- BEGIN FEED TABLE -->\n{table}\n<!-- END FEED TABLE -->\n"
        )

    # Append footer template if present
    if footer_path and footer_path.exists():
        content += footer_path.read_text(encoding="utf-8")

    # Append timestamp
    content += f"\n_Last updated: {now}_\n"

    if output_path:
        output_path.write_text(content, encoding="utf-8")

    return content
