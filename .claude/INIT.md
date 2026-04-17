Create a new Python project called `doublefinger` from scratch.
Read this entire prompt carefully before creating any file.
Follow a strict TDD Red/Green cycle for every piece of logic.

## Project purpose

`doublefinger` is a CLI wrapper around the Crawl4AI library.
It lets the user crawl websites and save clean Markdown output
without having to know the Crawl4AI API by heart.
All crawling logic must use Crawl4AI directly (no subprocess, no Node.js).

## Project structure to create

doublefinger/
├── doublefinger.py        # CLI entry point (argparse)
├── crawler.py             # Crawl4AI crawling logic
├── outputs.py             # Output directory management + list command
├── config.py              # Config file read/write (~/.config/doublefinger/config.toml)
├── build.sh               # Creates venv, installs dependencies, runs playwright install
├── requirements.txt       # crawl4ai, tomli/tomllib
├── tests/
│   ├── __init__.py
│   ├── test_config.py     # Tests for config loading and defaults
│   ├── test_outputs.py    # Tests for directory naming and list command
│   └── test_crawler.py    # Tests for URL pattern derivation and page naming
└── README.md              # Generated last, after all tests pass

## MANDATORY TDD WORKFLOW

For every module, follow this exact sequence:

  STEP 1 — Write the test file first (do not create the module yet)
  STEP 2 — Run the tests: confirm they ALL fail (Red)
            If a test passes before implementation, it is wrong — fix it.
  STEP 3 — Write the minimal implementation to make the tests pass (Green)
  STEP 4 — Run the tests again: confirm they ALL pass
  STEP 5 — Refactor if needed, re-run tests to confirm still Green
  STEP 6 — Move to the next module

Order of modules: config → outputs → crawler → doublefinger (CLI wiring)

Never write implementation code before the corresponding test exists.
Never skip the Red verification step.

## Test coverage requirements

### tests/test_config.py

Test that:
- Config file is created with default values if it does not exist
- Config values are correctly read from an existing file
- base_dir is expanded (~ resolved to absolute path)
- A malformed TOML file raises a clear error (not a raw exception)
- CLI flag values override config file values when both are present

### tests/test_outputs.py

Test the output directory name derivation function with these exact cases:

  Input URL                                          Expected output name
  ------------------------------------------------   -----------------------------------
  https://iac.goffinet.org/ansible-fondamental/      org.goffinet.iac.ansible-fondamental
  https://iac.goffinet.org/                          org.goffinet.iac
  https://docs.example.com/guide/intro               com.example.docs.guide
  https://example.com                                com.example
  https://sub.domain.example.co.uk/path/to/page      uk.co.example.domain.sub.path

Test the per-page filename derivation with:

  Page URL                                                    Expected filename
  ----------------------------------------------------------  -------------------------------------------
  https://iac.goffinet.org/ansible-fondamental/installation-ansible/
                                                              ansible-fondamental-installation-ansible.md
  https://iac.goffinet.org/ansible-fondamental/               ansible-fondamental.md
  https://iac.goffinet.org/                                   index.md

Test that:
- Output directory is created if it does not exist
- list command returns correct metadata (file count, size, last modified)
  for a temporary directory created during the test

### tests/test_crawler.py

Test the URL pattern auto-derivation:

  Input URL                                          Expected match pattern
  ------------------------------------------------   -----------------------------------------
  https://iac.goffinet.org/ansible-fondamental/      https://iac.goffinet.org/ansible-fondamental/**
  https://iac.goffinet.org/                          https://iac.goffinet.org/**
  https://docs.example.com/guide/intro               https://docs.example.com/guide/**

Test that:
- A failed page (simulated with a mock) logs a warning and does not raise
- The crawler respects max_pages=1 by stopping after one page
  (use mock/patch to avoid real HTTP calls in unit tests)

## CLI interface (argparse, stdlib only)

Entry point: `python doublefinger.py <command> [options]`

### Command: crawl

python doublefinger.py crawl <url> [options]

Required argument:
  url                     Seed URL to start crawling from

Options:
  --match PATTERN         URL glob pattern to follow links
                          Default: auto-derived as <scheme>://<host>/<first-path-segment>/**
  --max-pages N           Maximum number of pages to crawl (default: 0 = unlimited)
  --output-dir PATH       Override the default output directory
  --browser               Force Playwright headless browser mode
                          (default: simple HTTP mode)
  --no-cache              Disable Crawl4AI's built-in cache

### Command: list

python doublefinger.py list

Lists all crawl output directories found under the configured base output
directory. For each entry, display:
- Directory name
- Number of Markdown files inside
- Total size (human-readable)
- Last modified date

## Output directory naming convention

Given a seed URL, derive the output directory name as follows:

  https://iac.goffinet.org/ansible-fondamental/
  → reverse the hostname:    org.goffinet.iac
  → take first path segment: ansible-fondamental
  → combine:                 org.goffinet.iac.ansible-fondamental

Rules:
- Strip leading/trailing slashes from path segments
- Ignore empty path segments
- If there is no path segment (root URL), use reversed hostname only
- Lowercase everything
- Replace any character that is not alphanumeric, dot, or hyphen with a hyphen

Full output path: <base_output_dir>/<derived_name>/
One Markdown file per crawled page, named from the page URL path.
Example: ansible-fondamental-installation-ansible.md

## Config file: ~/.config/doublefinger/config.toml

Created automatically with defaults on first run if it does not exist.

[output]
base_dir = "~/Downloads"

[crawl]
default_max_pages = 0
default_format = "markdown"

Use tomllib (Python 3.11+) with fallback to tomli for older versions.

## Crawling logic (crawler.py)

Use Crawl4AI's AsyncWebCrawler.
- Default mode: simple HTTP mode (no browser)
- --browser flag: enable Playwright headless browser mode
- Follow internal links matching the --match pattern
- Extract content as Markdown using Crawl4AI's built-in conversion
- Write one .md file per page into the output directory
- Print progress to stdout: "Crawling: <url>" for each page
- Print summary at end: total pages crawled, output directory path

## Error handling rules

- Failed page: print warning, continue (never crash the crawl)
- Output directory cannot be created: exit with clear error message
- Malformed config.toml: exit with clear message pointing to the file path
- Crawl4AI not installed: print "Run ./build.sh to install dependencies."

## build.sh

#!/bin/bash
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
echo "doublefinger is ready. Activate with: source .venv/bin/activate"

## requirements.txt

crawl4ai
tomli; python_version < "3.11"

## README.md — generate this LAST, after all tests pass

The README must document the CURRENT STATE of the project only.
Never document planned or unimplemented features.

Required sections:
1. Project Overview (purpose, stack, entry points)
2. Architecture & Code Structure (directory tree + responsibility of each file)
3. Configuration (all config keys, defaults, override rules)
4. Commands (crawl and list with all flags and examples)
5. How to Run (build.sh, activation, usage examples using iac.goffinet.org)
6. Testing (how to run tests, what each test file covers)
7. Changelog

Changelog format (add an entry for this initial version):

## Changelog

### v0.1.0 — YYYY-MM-DD
- Initial implementation: crawl and list commands
- TDD: X tests written, X passing
- Modules: config, outputs, crawler, CLI wiring

## Implementation rules

- Read Crawl4AI documentation or source to use the correct API
- argparse only — no Click, no Typer
- tomllib/tomli only — no other config libraries
- All async code uses asyncio.run() as CLI entry point
- No global state — pass config explicitly as parameters
- No subprocess anywhere
- Prefer simple, readable code over clever abstractions
- Write tests before implementation — no exceptions
- Do not mock what you can test with tempfile and real filesystem
- Use unittest.mock only for external calls (HTTP, Crawl4AI browser)