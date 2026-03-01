"""Template-based event rewriting."""

from __future__ import annotations

import re

from calendar_splitter.core.models import ClassifiedEvent, CourseConfig


def _clean_summary(text: str) -> str:
    """Remove dash artifacts and extra whitespace from templated summary."""
    text = re.sub(r"\s*-\s*-\s*", " - ", text)
    return re.sub(r"\s+", " ", text).strip()


def _format_summary(
    tpl: str, display_name: str, n: int | None, title: str, course: str
) -> str:
    """Format a summary template, cleaning up artifacts from empty fields."""
    try:
        raw = tpl.format(
            kind=display_name,
            n=n if n is not None else "",
            title=title,
            course=course,
        )
        return _clean_summary(raw)
    except (KeyError, ValueError):
        return ""


def rewrite_event(
    classified: ClassifiedEvent, config: CourseConfig
) -> tuple[str, str]:
    """Rewrite event summary and description using course templates.

    Returns (new_summary, new_description).
    """
    event = classified.event
    kind = classified.kind
    n = classified.number
    item = classified.item

    title = item.get("title") if item else ""
    module = item.get("module") if item else ""

    # Summary
    new_summary = event.summary
    if kind:
        display_name = kind.capitalize()
        if classified.event_type:
            display_name = classified.event_type.display_name

        formatted = _format_summary(
            config.templates.summary, display_name, n, title, config.course_code
        )
        if formatted:
            new_summary = formatted

    # Description
    original = (event.description or "").strip()
    if original:
        new_desc = config.templates.description.format(
            module=(module or "").strip(),
            canvas=(config.canvas_url or "").strip(),
            original=original,
        ).strip()
    else:
        parts: list[str] = []
        if module:
            parts.append(module)
        if config.canvas_url:
            parts.append(f"Canvas: {config.canvas_url}")
        new_desc = "\n\n".join(parts).strip()

    return new_summary, new_desc
