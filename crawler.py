"""Crawling logic for doublefinger, built on top of Crawl4AI's AsyncWebCrawler.

Implements:
- URL match-pattern derivation from a seed URL.
- A breadth-first async crawl loop that writes one Markdown file per page.
- Graceful handling of failed pages (warning, no crash).
- Optional headless-browser mode, cache bypass, and post-load wait delay.
"""

import fnmatch
import warnings
from pathlib import Path
from urllib.parse import urlparse

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai import CrawlerRunConfig
except ImportError:
    # Defer the hard error to runtime so the module can still be imported
    # and tested without Crawl4AI installed.
    AsyncWebCrawler = None
    CrawlerRunConfig = None

from outputs import derive_page_filename


def derive_match_pattern(url: str) -> str:
    """Auto-derive a glob pattern that covers the subtree of a seed URL.

    The pattern is ``<scheme>://<host>/<first-path-segment>/**``.
    When the seed URL has no path segment (root URL), the pattern is
    ``<scheme>://<host>/**``.

    Examples::

        https://iac.goffinet.org/ansible-fondamental/  →  https://iac.goffinet.org/ansible-fondamental/**
        https://iac.goffinet.org/                      →  https://iac.goffinet.org/**
        https://docs.example.com/guide/intro           →  https://docs.example.com/guide/**

    Args:
        url: The seed URL passed to the crawl command.

    Returns:
        A glob pattern string compatible with :func:`fnmatch.fnmatch`.
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return f"{base}/**"
    return f"{base}/{segments[0]}/**"


def derive_wait_config(wait: int) -> float:
    """Convert an integer wait value to the float expected by Crawl4AI.

    Args:
        wait: Seconds to wait after page load, as provided by the CLI flag.

    Returns:
        ``float(wait)``, giving ``0.0`` when no wait is requested.
    """
    return float(wait)


def _url_matches(url: str, pattern: str) -> bool:
    """Return True if ``url`` matches the given glob ``pattern``."""
    return fnmatch.fnmatch(url, pattern)


async def crawl_site(
    seed_url: str,
    match_pattern: str,
    max_pages: int,
    output_dir: Path,
    use_browser: bool,
    no_cache: bool,
    wait: int = 0,
) -> None:
    """Crawl a website breadth-first and write each page as a Markdown file.

    Starting from ``seed_url``, the crawler follows internal links whose
    href matches ``match_pattern``. Each successfully crawled page is saved
    as a ``.md`` file inside ``output_dir`` using the filename derived by
    :func:`outputs.derive_page_filename`.

    Failed pages (``result.success is False``) emit a :class:`UserWarning`
    and are skipped without interrupting the crawl.

    Args:
        seed_url: The first URL to crawl. Also used as the starting point
            for the BFS queue.
        match_pattern: Glob pattern (e.g. ``https://example.com/docs/**``)
            used to decide which internal links to follow.
        max_pages: Maximum number of pages to crawl. ``0`` means unlimited.
        output_dir: Directory where Markdown files will be written.
            Must already exist (see :func:`outputs.ensure_output_dir`).
        use_browser: When ``True``, Crawl4AI uses a Playwright headless
            Chromium browser instead of a plain HTTP fetch.
        no_cache: When ``True``, bypasses Crawl4AI's built-in response cache.
        wait: Seconds to wait after page load before extracting content.
            Passed as ``delay_before_return_html`` to :class:`CrawlerRunConfig`.
            Useful for JavaScript-heavy SPAs. ``0`` disables the delay.

    Raises:
        SystemExit: If Crawl4AI is not installed.
    """
    if AsyncWebCrawler is None:
        raise SystemExit("Run ./build.sh to install dependencies.")

    crawler_kwargs = {}
    if use_browser:
        crawler_kwargs["browser_type"] = "chromium"

    visited: set[str] = set()
    queue: list[str] = [seed_url]
    pages_crawled = 0

    async with AsyncWebCrawler(**crawler_kwargs) as crawler:
        while queue:
            if max_pages and pages_crawled >= max_pages:
                break

            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            print(f"Crawling: {url}")

            run_config_kwargs = {}
            if no_cache:
                run_config_kwargs["cache_mode"] = "bypass"
            run_config_kwargs["delay_before_return_html"] = derive_wait_config(wait)

            config = CrawlerRunConfig(**run_config_kwargs)
            result = await crawler.arun(url=url, config=config)

            if not result.success:
                warnings.warn(f"Failed to crawl {url}", UserWarning, stacklevel=1)
                continue

            pages_crawled += 1

            filename = derive_page_filename(url)
            (output_dir / filename).write_text(result.markdown or "")

            # Enqueue internal links that fall within the match pattern.
            if hasattr(result, "links") and result.links:
                for link in result.links.get("internal", []):
                    href = link.get("href", "") if isinstance(link, dict) else link
                    if href and href not in visited and _url_matches(href, match_pattern):
                        queue.append(href)

    print(f"\nCrawled {pages_crawled} page(s) → {output_dir}")
