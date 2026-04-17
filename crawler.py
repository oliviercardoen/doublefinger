import fnmatch
import warnings
from pathlib import Path
from urllib.parse import urlparse

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    AsyncWebCrawler = None

from outputs import derive_page_filename


def derive_match_pattern(url: str) -> str:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return f"{base}/**"
    return f"{base}/{segments[0]}/**"


def _url_matches(url: str, pattern: str) -> bool:
    return fnmatch.fnmatch(url, pattern)


async def crawl_site(
    seed_url: str,
    match_pattern: str,
    max_pages: int,
    output_dir: Path,
    use_browser: bool,
    no_cache: bool,
) -> None:
    if AsyncWebCrawler is None:
        raise SystemExit("Run ./build.sh to install dependencies.")

    crawler_kwargs = {}
    if use_browser:
        crawler_kwargs["browser_type"] = "chromium"

    visited = set()
    queue = [seed_url]
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

            run_kwargs = {}
            if no_cache:
                run_kwargs["cache_mode"] = "bypass"

            result = await crawler.arun(url=url, **run_kwargs)

            if not result.success:
                warnings.warn(f"Failed to crawl {url}", UserWarning, stacklevel=1)
                continue

            pages_crawled += 1

            filename = derive_page_filename(url)
            (output_dir / filename).write_text(result.markdown or "")

            if hasattr(result, "links") and result.links:
                for link in result.links.get("internal", []):
                    href = link.get("href", "") if isinstance(link, dict) else link
                    if href and href not in visited and _url_matches(href, match_pattern):
                        queue.append(href)

    print(f"\nCrawled {pages_crawled} page(s) → {output_dir}")
