"""Custom exception hierarchy for calendar-splitter."""


class CalendarSplitterError(Exception):
    """Base exception for all calendar-splitter errors."""


class ConfigError(CalendarSplitterError):
    """Raised when course configuration is invalid or cannot be loaded."""


class FetchError(CalendarSplitterError):
    """Raised when fetching upstream calendar data fails."""


class ParseError(CalendarSplitterError):
    """Raised when ICS data cannot be parsed."""


class TemplateError(CalendarSplitterError):
    """Raised when a template string is invalid or cannot be rendered."""
