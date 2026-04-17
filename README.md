# doublefinger

A CLI wrapper around [Crawl4AI](https://github.com/unclecode/crawl4ai) that crawls websites and saves clean Markdown output to disk.

## Project Overview

**Purpose:** crawl a website starting from a seed URL, follow internal links matching a glob pattern, and write one Markdown file per page into a structured output directory — without knowing the Crawl4AI API by heart.

**Stack:** Python 3.10+, Crawl4AI, argparse (stdlib), tomllib/tomli, asyncio.

**Entry point:** `python doublefinger.py <command> [options]`

---

## Architecture & Code Structure

```
doublefinger/
├── doublefinger.py   # CLI entry point — argparse wiring, dispatches to modules
├── crawler.py        # Crawl4AI crawling logic, URL pattern derivation
├── outputs.py        # Output directory naming, page filename derivation, list command
├── config.py         # Config file load/write (~/.config/doublefinger/config.toml)
├── build.sh          # Creates venv, installs dependencies, runs playwright install
├── requirements.txt  # crawl4ai, tomli (Python < 3.11)
└── tests/
    ├── __init__.py
    ├── test_config.py    # Config loading, defaults, tilde expansion, overrides
    ├── test_outputs.py   # Directory naming, page filename derivation, list metadata
    └── test_crawler.py   # URL pattern derivation, failed page handling, max_pages
```

---

## Configuration

Config file: `~/.config/doublefinger/config.toml`

Created automatically with defaults on first run.

| Key | Default | Description |
|-----|---------|-------------|
| `output.base_dir` | `~/Downloads` | Root directory for all crawl outputs |
| `crawl.default_max_pages` | `0` | Max pages per crawl (0 = unlimited) |
| `crawl.default_format` | `"markdown"` | Output format |

**Override rules:** CLI flags always take precedence over config file values.

Example config:
```toml
[output]
base_dir = "~/Downloads"

[crawl]
default_max_pages = 0
default_format = "markdown"
```

---

## Commands

### `crawl`

```
python doublefinger.py crawl <url> [options]
```

| Argument | Description |
|----------|-------------|
| `url` | Seed URL to start crawling from (required) |
| `--match PATTERN` | URL glob pattern to follow links. Default: auto-derived as `<scheme>://<host>/<first-path-segment>/**` |
| `--max-pages N` | Maximum pages to crawl. `0` = unlimited (default: from config) |
| `--output-dir PATH` | Override the default output directory |
| `--browser` | Force Playwright headless browser mode (default: simple HTTP mode) |
| `--no-cache` | Disable Crawl4AI's built-in cache |

**Output directory naming:**

The seed URL is converted to a directory name by reversing the hostname and prepending the first path segment:

```
https://docs.crawl4ai.com/core/
→ com.crawl4ai.docs.core
```

One `.md` file per crawled page, named from the URL path:

```
https://docs.crawl4ai.com/core/quickstart/
→ core-quickstart.md
```

### `list`

```
python doublefinger.py list
```

Lists all crawl output directories under `base_dir`. Displays directory name, file count, total size, and last modified date.

---

## How to Run

**1. Build the environment:**

```bash
./build.sh
```

**2. Activate:**

```bash
source .venv/bin/activate
```

**3. Crawl a site:**

```bash
# Crawl the core section of docs.crawl4ai.com
python doublefinger.py crawl https://docs.crawl4ai.com/core/

# Limit to 10 pages
python doublefinger.py crawl https://docs.crawl4ai.com/core/ --max-pages 10

# Use headless browser mode
python doublefinger.py crawl https://docs.crawl4ai.com/core/ --browser

# Custom output directory
python doublefinger.py crawl https://docs.crawl4ai.com/core/ --output-dir /tmp/my-crawl

# Explicit match pattern
python doublefinger.py crawl https://docs.crawl4ai.com/ --match "https://docs.crawl4ai.com/**"
```

**4. List outputs:**

```bash
python doublefinger.py list
```

---

## Testing

**Run tests:**

```bash
python3 -m pytest tests/ -v
```

**Test files:**

| File | Covers |
|------|--------|
| `tests/test_config.py` | Config creation with defaults, reading existing config, tilde expansion in `base_dir`, malformed TOML error handling, CLI flag overrides |
| `tests/test_outputs.py` | Output directory name derivation (5 URL cases), per-page filename derivation (3 cases), directory creation, `list` metadata (file count, size, last modified) |
| `tests/test_crawler.py` | URL match pattern auto-derivation (3 cases), failed page warning without crash, `max_pages=1` stops after one page |

All tests use `tempfile` for filesystem operations and `unittest.mock` only for Crawl4AI HTTP calls.

---

## Changelog

### v0.1.1 — 2026-04-17
- README: replaced example URLs with Crawl4AI documentation site
- No code changes

### v0.1.0 — 2026-04-17
- Initial implementation: `crawl` and `list` commands
- TDD: 20 tests written, 20 passing
- Modules: `config`, `outputs`, `crawler`, CLI wiring (`doublefinger.py`)
