"""Crawling logic for doublefinger, built on top of Crawl4AI's AsyncWebCrawler.

Implements:
- URL match-pattern derivation from a seed URL.
- A breadth-first async crawl loop that writes one Markdown file per page.
- URL normalization so one page is never crawled or written twice.
- A resumable crawl backed by the output directory's manifest.
- Graceful handling of failed pages (warning, no crash).
- Optional headless-browser mode, cache bypass, and post-load wait delay.
"""

import fnmatch
import warnings
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai import CrawlerRunConfig
except ImportError:
    # Defer the hard error to runtime so the module can still be imported
    # and tested without Crawl4AI installed.
    AsyncWebCrawler = None
    CrawlerRunConfig = None

from manifest import (
    is_recorded,
    load_manifest,
    new_manifest,
    record_page,
    recorded_links,
    save_manifest,
)
from outputs import derive_page_filename, normalize_url


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
    """Return True if ``url`` falls inside the subtree described by ``pattern``.

    Beyond a plain glob match, a pattern such as ``https://x.org/docs/**``
    also covers the section index ``https://x.org/docs`` itself: normalized
    URLs carry no trailing slash, so the index would otherwise be excluded
    from its own subtree.
    """
    if fnmatch.fnmatch(url, pattern):
        return True
    if pattern.endswith("/**") and url == pattern[:-3]:
        return True
    return False


def _matching_links(result, page_url: str, match_pattern: str) -> list:
    """Return the normalized internal links of a page that match the pattern.

    Relative hrefs are resolved against ``page_url`` before normalization,
    and duplicates are removed while preserving discovery order.

    Args:
        result: The Crawl4AI result object for the crawled page.
        page_url: The (normalized) URL the result belongs to.
        match_pattern: Glob pattern deciding which links are in scope.

    Returns:
        A list of normalized, in-scope, de-duplicated URLs.
    """
    if not getattr(result, "links", None):
        return []

    links = []
    seen = set()
    for link in result.links.get("internal", []):
        href = link.get("href", "") if isinstance(link, dict) else link
        if not href:
            continue
        href = normalize_url(urljoin(page_url, href))
        if href in seen or not _url_matches(href, match_pattern):
            continue
        seen.add(href)
        links.append(href)
    return links


async def crawl_site(
    seed_url: str,
    match_pattern: str,
    max_pages: int,
    output_dir: Path,
    use_browser: bool,
    no_cache: bool,
    wait: int = 0,
    resume: bool = True,
) -> None:
    """Crawl a website breadth-first and write each page as a Markdown file.

    Starting from ``seed_url``, the crawler follows internal links whose
    href matches ``match_pattern``. Every URL is normalized by
    :func:`outputs.normalize_url` before use, so a page reached through
    several spellings costs one request and one file.

    Each successfully crawled page is saved as a ``.md`` file inside
    ``output_dir`` and recorded in that directory's manifest, together with
    the links followed from it. When ``resume`` is true, a page already
    recorded there is not fetched again; its recorded links are pushed back
    onto the queue instead, so a second crawl over the same subtree only
    pays for URLs that are genuinely new.

    Failed pages (``result.success is False``) emit a :class:`UserWarning`
    and are skipped without interrupting the crawl.

    Args:
        seed_url: The first URL to crawl. Also used as the starting point
            for the BFS queue.
        match_pattern: Glob pattern (e.g. ``https://example.com/docs/**``)
            used to decide which internal links to follow.
        max_pages: Maximum number of pages to crawl. ``0`` means unlimited.
            Only pages actually fetched count towards the limit; pages
            skipped on resume do not.
        output_dir: Directory where Markdown files will be written.
            Must already exist (see :func:`outputs.ensure_output_dir`).
        use_browser: When ``True``, Crawl4AI uses a Playwright headless
            Chromium browser instead of a plain HTTP fetch.
        no_cache: When ``True``, bypasses Crawl4AI's built-in response cache.
        wait: Seconds to wait after page load before extracting content.
            Passed as ``delay_before_return_html`` to :class:`CrawlerRunConfig`.
            Useful for JavaScript-heavy SPAs. ``0`` disables the delay.
        resume: When ``True`` (the default), reuse the existing manifest and
            skip pages already crawled into ``output_dir``. When ``False``,
            re-crawl every page and rebuild the manifest from scratch.

    Raises:
        SystemExit: If Crawl4AI is not installed.
    """
    if AsyncWebCrawler is None:
        raise SystemExit("Run ./build.sh to install dependencies.")

    crawler_kwargs = {}
    if use_browser:
        crawler_kwargs["browser_type"] = "chromium"

    # A forced crawl defines the new truth for this directory, so it starts
    # from an empty manifest rather than accumulating stale entries.
    manifest = load_manifest(output_dir) if resume else new_manifest()

    visited: set[str] = set()
    queue: list[str] = [normalize_url(seed_url)]
    pages_crawled = 0
    pages_skipped = 0

    async with AsyncWebCrawler(**crawler_kwargs) as crawler:
        while queue:
            if max_pages and pages_crawled >= max_pages:
                break

            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            if resume and is_recorded(manifest, url, output_dir):
                pages_skipped += 1
                # Restore the frontier this page produced last time, so the
                # crawl can still reach pages added since.
                for href in recorded_links(manifest, url):
                    if href not in visited and _url_matches(href, match_pattern):
                        queue.append(href)
                continue

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
            content = result.markdown or ""
            (output_dir / filename).write_text(content)

            links = _matching_links(result, url, match_pattern)
            for href in links:
                if href not in visited:
                    queue.append(href)

            # Saved page by page so an interrupted crawl stays resumable.
            record_page(manifest, url, filename, content, links)
            save_manifest(output_dir, manifest)

    if pages_skipped:
        print(
            f"\nCrawled {pages_crawled} page(s), skipped {pages_skipped} already "
            f"in the manifest (use --force to re-crawl) → {output_dir}"
        )
    else:
        print(f"\nCrawled {pages_crawled} page(s) → {output_dir}")
