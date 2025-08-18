# Calendar Splitter

A Python tool for parsing university course calendars (iCal format) and splitting them into individual, tokenized course feeds. Originally designed for KTH Royal Institute of Technology calendar systems.

## Features

- **Smart Course Detection**: Automatically identifies courses from calendar events using course codes and KTH URLs
- **Event Enhancement**: Enriches events with structured information (lecture titles, modules, Canvas links)
- **Token-based Privacy**: Generates UUID tokens for feed URLs to prevent unauthorized discovery
- **Change Detection**: Uses HTTP ETag/Last-Modified headers to avoid unnecessary processing
- **Flexible Configuration**: JSON-based course rules with regex matching and template customization
- **Docker Ready**: Containerized deployment with GitHub Actions automation

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd calendar-splitter
```

2. Create virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

### Basic Usage

```bash
# Set required environment variables
export FEEDS_DIR="output/feeds"
export TOKEN_MAP_PATH="tokens.json"
export SOURCE_ICS_URL="https://example.com/calendar.ics"

# Run the splitter
python -m scripts.main
```

## Configuration

### Environment Variables

| Variable              | Required | Default                      | Description                                 |
| --------------------- | -------- | ---------------------------- | ------------------------------------------- |
| `FEEDS_DIR`           | Yes      | -                            | Output directory for generated feeds        |
| `TOKEN_MAP_PATH`      | Yes      | -                            | Path to store course→token mappings         |
| `SOURCE_ICS_URL`      | No       | -                            | URL to fetch calendar from (optional)       |
| `LOCAL_UPSTREAM_ICS`  | No       | `personal.ics`               | Local fallback calendar file                |
| `EVENTS_DIR`          | No       | `events`                     | Directory containing course rule files      |
| `UPSTREAM_STATE_PATH` | No       | `_feeds/upstream_state.json` | Cache file for change detection             |
| `LOG_LEVEL`           | No       | `INFO`                       | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Course Rules

Create JSON files in the `events/` directory to customize how courses are processed:

```json
{
  "course": "IS1200",
  "canvas": "https://canvas.kth.se/courses/56261",
  "match": {
    "require_course_in_summary": true,
    "summary_regex": "\\bLecture\\s*(\\d+)\\b"
  },
  "title_template": "Lecture {n} - {title} - {course}",
  "description_template": "{module}\nCanvas: {canvas}\n\n{old_desc}",
  "items": [
    {
      "number": 1,
      "title": "Course Introduction",
      "module": "Module 1: Programming Fundamentals"
    }
  ]
}
```

#### Rule Schema

- **`course`**: Course code (e.g., "IS1200")
- **`canvas`**: Canvas course URL (optional)
- **`match`**: Event matching criteria
  - `require_course_in_summary`: Must contain "(COURSE)" in summary
  - `summary_regex`: Custom regex for extracting lecture numbers
- **`title_template`**: Template for event titles (supports `{n}`, `{title}`, `{course}`)
- **`description_template`**: Template for descriptions (supports `{module}`, `{canvas}`, `{old_desc}`)
- **`items`**: Array of lecture/lab/exercise definitions

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Fetch Module  │ -> │  Split Module   │ -> │  Output Feeds   │
│                 │    │                 │    │                 │
│ • HTTP fetching │    │ • Course detect │    │ • Tokenized ICS │
│ • ETag caching  │    │ • Rule matching │    │ • UUID security │
│ • Local fallback│    │ • Event rewrite │    │ • Change detect │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Key Components

- **`scripts/fetch.py`**: HTTP fetching with smart caching
- **`scripts/split.py`**: Core calendar parsing and splitting logic
- **`scripts/rules.py`**: Course rule loading and validation
- **`scripts/rewrite.py`**: Event enhancement and templating
- **`scripts/tokens.py`**: UUID token generation and management
- **`scripts/main.py`**: CLI entry point and orchestration

## Development

### Setup Development Environment

```bash
# Install development dependencies
pip install -r dev-requirements.txt

# Run tests
pytest -v

# Run type checking
mypy scripts

# Run linting
ruff check .
```

### Running Tests

```bash
# Basic test run
pytest

# With coverage
pytest --cov=scripts --cov-report=term-missing

# Specific test file
pytest tests/test_split.py -v
```

### Code Quality

This project uses:

- **MyPy** for static type checking
- **Ruff** for linting and code formatting
- **Pytest** for testing with coverage reporting
- **GitHub Actions** for CI/CD

## Deployment

### Docker

```bash
# Build image
docker build -t calendar-splitter .

# Run container
docker run -e FEEDS_DIR=/app/output \
           -e TOKEN_MAP_PATH=/app/tokens.json \
           -e SOURCE_ICS_URL="https://..." \
           -v $(pwd)/output:/app/output \
           calendar-splitter
```

### GitHub Actions

The project includes automated CI/CD:

- **CI Pipeline** (`.github/workflows/ci.yml`):
  - Runs tests, type checking, and linting
  - Triggered on pushes and pull requests

- **Feed Generation** (`.github/workflows/generate-feeds.yml`):
  - Scheduled daily calendar processing
  - Automatic commit and deploy to GitHub Pages
  - Supports private course configuration repositories

## Examples

### Basic Course Splitting

Input calendar with mixed events:

```
SUMMARY: Lecture 1 - Introduction (IS1200)
SUMMARY: Lab 3 - Programming (IS1200)
SUMMARY: Project Meeting (DH2642)
```

Output: Separate tokenized feeds:

- `IS1200--a1b2c3d4e5f6.ics`
- `DH2642--f6e5d4c3b2a1.ics`

### Enhanced Event Processing

Original event:

```
SUMMARY: Lecture 5 (IS1200)
DESCRIPTION: Basic course info
```

Enhanced output:

```
SUMMARY: Lecture 5 - I/O Systems (part I) - IS1200
DESCRIPTION: Module 2: I/O Systems
Canvas: https://canvas.kth.se/courses/56261

Basic course info
```

## Security Considerations

- **Token Privacy**: Course feeds use UUID tokens to prevent unauthorized access
- **Secret Masking**: GitHub Actions automatically masks sensitive URLs and tokens
- **Input Validation**: All JSON inputs are validated and sanitized
- **Safe Logging**: Automatically redacts UUIDs, query strings, and sensitive data

