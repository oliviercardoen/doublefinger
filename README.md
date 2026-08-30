# doublefinger

A CLI wrapper around [Crawl4AI](https://github.com/unclecode/crawl4ai) that crawls websites and saves clean Markdown output to disk.

## Project Overview

**Purpose:** crawl a website starting from a seed URL, follow internal links matching a glob pattern, and write one Markdown file per page into a structured output directory — without knowing the Crawl4AI API by heart. Repeated crawls of the same site are de-duplicated rather than re-fetched, and directories collected from different entry points can be merged into one.

**Stack:** Python 3.10+, Crawl4AI, argparse (stdlib), tomllib/tomli, asyncio.

**Entry point:** `python doublefinger.py <command> [options]`

---

## Architecture & Code Structure

```
doublefinger/
├── doublefinger.py   # CLI entry point — argparse wiring, dispatches to modules
├── crawler.py        # Crawl4AI crawling logic, URL pattern derivation, resumable BFS
├── outputs.py        # URL normalization, output directory naming, page filenames, list command
├── manifest.py       # Per-directory .doublefinger.json manifest (dedup + resume)
├── merge.py          # Merging crawl directories, de-duplication by URL and content
├── config.py         # Config file load/write (~/.config/doublefinger/config.toml)
├── install.sh        # System-wide installation (writes /usr/local/bin/doublefinger)
├── setup.sh          # Development environment setup (venv + deps + playwright)
├── requirements.txt  # crawl4ai, tomli (Python < 3.11)
└── tests/
    ├── __init__.py
    ├── test_config.py    # Config loading, defaults, tilde expansion, overrides
    ├── test_outputs.py   # URL normalization, directory naming, page filenames, list metadata
    ├── test_manifest.py  # Manifest round-trip, corruption handling, recorded-page checks
    ├── test_merge.py     # Merge de-duplication, filename conflicts, dry run, CLI parsing
    └── test_crawler.py   # URL pattern derivation, failed page handling, max_pages, resume
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
| `--wait N` | Seconds to wait after page load before extracting content. Use with `--browser` for JS-heavy SPAs (default: 0) |
| `--resume` | Skip pages already recorded in the output directory's manifest (this is the default) |
| `--force` | Re-crawl every page and rebuild the manifest from scratch. Mutually exclusive with `--resume` |

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

**Deduplication and resuming:**

Every URL is normalized before it is fetched or written, so one page has one
identity. Normalization lowercases the scheme and host, drops the default
port, drops the `#fragment`, strips tracking parameters (`utm_*`, `fbclid`,
`gclid`, …), sorts any remaining query parameters, and removes the trailing
slash:

```
https://Example.com:443/docs/?utm_source=news#intro  →  https://example.com/docs
https://example.com/docs                             →  https://example.com/docs
```

Query parameters that are *not* tracking parameters are kept, and they are
part of the filename, so `?page=2` gets its own file instead of silently
overwriting `blog.md`.

Each output directory carries a `.doublefinger.json` manifest recording, per
page, the file written, a SHA-256 of its content, the crawl date, and the
links followed from it. It is rewritten after every page, so an interrupted
crawl stays resumable.

Resuming is the **default**: a page already in the manifest is not fetched
again. Its recorded links are pushed back onto the queue instead, so the
crawl frontier survives across runs and only genuinely new URLs cost a
request. This is what makes repeated crawls over the same section cheap:

```bash
# First run fetches the whole /core/ subtree
doublefinger crawl https://docs.crawl4ai.com/core/

# Same subtree, different entry point: nothing is fetched twice
doublefinger crawl https://docs.crawl4ai.com/core/quickstart/
# → Crawled 0 page(s), skipped 24 already in the manifest
```

Deleting a `.md` file is enough to make the next run fetch that page again.

Because skipped pages are never re-fetched, links *added* to an already
crawled page are not discovered on a resumed run. Use `--force` to pick up
changes to a site you have already crawled:

```bash
doublefinger crawl https://docs.crawl4ai.com/core/ --force
```

### `list`

```
python doublefinger.py list
```

Lists all crawl output directories under `base_dir`. Displays directory name, file count, total size, and last modified date.

### `merge`

```
python doublefinger.py merge <dir> [<dir> ...] --into <dest> [--dry-run]
```

| Argument | Description |
|----------|-------------|
| `dir ...` | Crawl directories to merge, as names shown by `list` or as paths. Processed in order: the first one listed wins ties |
| `--into DEST` | Destination directory, as a name or a path. Created if missing (required) |
| `--dry-run` | Report what would be merged without writing anything |

Crawling a site from several entry points leaves the same pages spread over
several directories — a root crawl and a section crawl both hold
`docs-intro.md`. `merge` folds them into one directory without ever
overwriting a page silently.

Identity is decided in two steps:

1. **By URL.** The source manifests say which URL produced which file, so the
   same page collected twice is recognised even if its content has changed
   since. When two copies disagree, the more recently crawled one wins.
2. **By content hash.** Files with no manifest entry — a directory from an
   older version, or one you assembled by hand — are still de-duplicated when
   their bytes are identical.

A filename that two *genuinely different* pages would claim is never
overwritten: the second copy gets a short digest suffix and the rename is
reported.

```bash
doublefinger merge com.site com.site.docs --into com.site.all
```

```
  copy      com.site/about.md → about.md
  copy      com.site/docs-intro.md → docs-intro.md
  copy      com.site.docs/docs-api.md → docs-api.md
  replace   com.site.docs/docs-intro.md (newer than the copy already merged)

Merged 2 directories into ~/Downloads/com.site.all: 3 page(s), 3 copied, 0 duplicate(s) skipped.
```

The merge is **non-destructive**: sources are copied, never moved or removed,
and anything already in the destination is preserved and never replaced by an
older source. Re-running the same merge is a no-op. The destination receives
its own manifest, so it stays resumable by a later `crawl`.

Use `--dry-run` first when merging directories you care about:

```bash
doublefinger merge com.site com.site.docs --into com.site.all --dry-run
```

---

## How to Run

**1. Clone and install:**

```bash
git clone https://github.com/oliviercardoen/doublefinger
cd doublefinger
./install.sh
```

`install.sh` creates the virtualenv, installs all dependencies, and writes a
launcher to `/usr/local/bin/doublefinger`. No manual venv activation is ever
needed again.

**2. Crawl a site:**

```bash
# Crawl the core section of docs.crawl4ai.com
doublefinger crawl https://docs.crawl4ai.com/core/

# Limit to 10 pages
doublefinger crawl https://docs.crawl4ai.com/core/ --max-pages 10

# Use headless browser mode
doublefinger crawl https://docs.crawl4ai.com/core/ --browser

# Custom output directory
doublefinger crawl https://docs.crawl4ai.com/core/ --output-dir /tmp/my-crawl

# Explicit match pattern
doublefinger crawl https://docs.crawl4ai.com/ --match "https://docs.crawl4ai.com/**"

# Crawl a JavaScript-heavy jobs page with browser + wait
doublefinger crawl https://jobs.proximus.com/be/en/proximus \
  --browser --wait 3
```

**3. List outputs:**

```bash
doublefinger list
```

**4. Merge directories collected from different entry points:**

```bash
doublefinger merge com.crawl4ai.docs com.crawl4ai.docs.core --into com.crawl4ai.all
```

---

## Development

For contributors who want to work on the code, `setup.sh` creates a local
virtualenv without touching any system paths:

```bash
./setup.sh
source .venv/bin/activate
python doublefinger.py --help
```

---

## Testing

**Run tests:**

```bash
python3 -m unittest discover -s tests -t . -v
```

**Test files:**

| File | Covers |
|------|--------|
| `tests/test_config.py` | Config creation with defaults, reading existing config, tilde expansion in `base_dir`, malformed TOML error handling, CLI flag overrides, entry point importability |
| `tests/test_outputs.py` | URL normalization (slash, case, port, fragment, tracking params, query sorting), output directory name derivation (5 URL cases), per-page filename derivation including query and long-name truncation, directory creation, `list` metadata |
| `tests/test_manifest.py` | Manifest save/load round-trip, content hashing, corrupt and malformed manifest handling, recorded-page checks against files on disk, exclusion from `list` counts |
| `tests/test_merge.py` | Directory resolution by name or path, de-duplication by URL and by content hash, recency arbitration, filename conflict renaming, manifest-less directories, destination preservation, dry run, source immutability, error cases, CLI parsing |
| `tests/test_crawler.py` | URL match pattern auto-derivation (3 cases), failed page warning without crash, `max_pages` stops after N pages, `--wait` default/value/negative validation, `delay_before_return_html` passed to Crawl4AI, URL-variant deduplication, relative link resolution, resume/`--force` behaviour, frontier restoration |

All tests use `tempfile` for filesystem operations and `unittest.mock` only for Crawl4AI HTTP calls.

---

## Changelog

### v0.1.5 — 2026-08-30
- Added the `merge` command: folds several crawl directories into one,
  de-duplicating by URL first and by content hash second
- Conflicting copies of the same page are resolved by crawl date; two
  different pages claiming one filename are both kept, with a digest suffix
- Non-destructive: sources are copied, existing destination content is
  preserved, and re-running a merge is a no-op
- The merged directory receives its own manifest and stays resumable
- Added `--dry-run` to report a merge without writing anything
- Pages are now written as explicit UTF-8, so content hashes match the bytes
  on disk regardless of locale
- TDD: 18 new tests written and passing (79 total)

### v0.1.4 — 2026-08-30
- Added URL normalization: one page now has one identity, so variants
  differing only by trailing slash, case, default port, fragment or tracking
  parameters are crawled and written once
- Query strings are kept in page filenames, so paginated URLs no longer
  overwrite each other
- Added a per-directory `.doublefinger.json` manifest (`manifest.py`)
  recording file, content hash, crawl date and followed links
- Added `--resume` (default) and `--force` flags to `crawl`
- Relative link hrefs are now resolved against the page instead of dropped
- A section index (`/docs`) is no longer excluded from its own `/docs/**` subtree
- Long page paths are truncated with a digest suffix instead of failing to write
- TDD: 35 new tests written and passing (61 total)

### v0.1.3 — 2026-04-17
- Added `--wait N` flag to `crawl` command
- Passes `delay_before_return_html` to Crawl4AI for SPA support
- TDD: 5 new tests written and passing (26 total)
- README: updated Commands and How to Run sections

### v0.1.2 — 2026-04-17
- Renamed `build.sh` to `setup.sh` (development environment setup)
- Added `install.sh` (system-wide installation of the `doublefinger` command)
- README: updated How to Run section, added Development section
- TDD: added `test_entry_point_importable` (21 tests, 21 passing)

### v0.1.1 — 2026-04-17
- README: replaced example URLs with Crawl4AI documentation site
- No code changes

### v0.1.0 — 2026-04-17
- Initial implementation: `crawl` and `list` commands
- TDD: 20 tests written, 20 passing
- Modules: `config`, `outputs`, `crawler`, CLI wiring (`doublefinger.py`)
