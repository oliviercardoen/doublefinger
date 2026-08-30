"""Output directory and filename management for doublefinger.

Provides helpers to:
- Normalize a URL to a canonical form, so the same page reached by several
  spellings is crawled and stored once.
- Derive a structured directory name from a seed URL (reversed hostname + first path segment).
- Derive a per-page Markdown filename from a page URL.
- Create the output directory on disk, with a clear error on failure.
- List all existing crawl output directories with file count, size, and modification time.
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query parameters that identify a referrer or campaign rather than a page.
# Stripped during normalization so that ?utm_source=... does not turn one
# page into several crawl targets.
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "fbclid", "gclid", "dclid", "gbraid",
    "wbraid", "msclkid", "mc_cid", "mc_eid", "igshid", "twclid", "ref_src",
    "_ga", "_gl", "yclid",
})

# Longest filename stem we will produce, leaving room for the ".md" suffix
# well inside the 255-byte limit of common filesystems.
MAX_STEM_LENGTH = 180

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _sanitize(segment: str) -> str:
    """Lowercase a string and replace any character outside [a-z0-9.-] with a hyphen."""
    return re.sub(r"[^a-z0-9.\-]", "-", segment.lower())


def normalize_url(url: str) -> str:
    """Reduce a URL to the canonical form used as a page's identity.

    Two URLs that normalize to the same string denote the same page: they
    are fetched once, written to one file, and recorded under one manifest
    key. The transformation is:

    - scheme and host lowercased, default port dropped;
    - fragment dropped (``#section`` is a position inside a page, not a page);
    - tracking parameters removed (see :data:`TRACKING_PARAMS`);
    - remaining query parameters kept but sorted, so parameter order stops
      mattering while genuinely distinct pages such as ``?page=2`` stay distinct;
    - repeated slashes collapsed and the trailing slash removed.

    Examples::

        https://Example.com:443/docs/?utm_source=x#intro  →  https://example.com/docs
        https://example.com/docs/                         →  https://example.com/docs
        https://example.com//docs//api/                   →  https://example.com/docs/api
        https://example.com/list?b=2&a=1                  →  https://example.com/list?a=1&b=2
        https://example.com                               →  https://example.com/

    Args:
        url: Any absolute URL. A string that is not an absolute URL (no
            scheme or no host) is returned unchanged.

    Returns:
        The normalized URL string.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    scheme = parsed.scheme.lower()
    netloc = (parsed.hostname or "").lower()
    port = None
    try:
        port = parsed.port
    except ValueError:
        # An unparseable port is left to the caller's URL as-is.
        return url
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{netloc}:{port}"

    path = re.sub(r"/{2,}", "/", parsed.path)
    path = path.rstrip("/") or "/"

    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept))

    return urlunparse((scheme, netloc, path, "", query, ""))


def derive_output_name(url: str) -> str:
    """Derive a filesystem-safe directory name from a seed URL.

    The name is built by reversing the hostname labels and appending the
    first non-empty path segment (if any), separated by a dot.

    Examples::

        https://iac.goffinet.org/ansible-fondamental/  →  org.goffinet.iac.ansible-fondamental
        https://iac.goffinet.org/                      →  org.goffinet.iac
        https://docs.example.com/guide/intro           →  com.example.docs.guide
        https://example.com                            →  com.example
        https://sub.domain.example.co.uk/path/to/page →  uk.co.example.domain.sub.path

    Args:
        url: The seed URL used to start a crawl.

    Returns:
        A lowercase, dot-and-hyphen-safe directory name string.
    """
    parsed = urlparse(url)
    host_parts = parsed.hostname.split(".")
    reversed_host = ".".join(reversed(host_parts))

    path_segments = [s for s in parsed.path.split("/") if s]
    if not path_segments:
        return _sanitize(reversed_host)

    first_segment = path_segments[0]
    return _sanitize(f"{reversed_host}.{first_segment}")


def derive_page_filename(url: str) -> str:
    """Derive a Markdown filename from a crawled page URL.

    The URL is normalized first, so trailing slashes, casing and tracking
    parameters cannot produce two names for one page. All non-empty path
    segments are joined with hyphens; any surviving query string is appended
    so that paginated URLs keep separate files rather than overwriting each
    other. A root URL maps to ``index.md``.

    Very long names are truncated and given a short digest suffix to stay
    within filesystem limits while remaining unique.

    Examples::

        https://iac.goffinet.org/ansible-fondamental/installation-ansible/
            →  ansible-fondamental-installation-ansible.md
        https://iac.goffinet.org/ansible-fondamental/
            →  ansible-fondamental.md
        https://iac.goffinet.org/
            →  index.md
        https://iac.goffinet.org/blog?page=2
            →  blog-page-2.md

    Args:
        url: The URL of the page that was crawled.

    Returns:
        A lowercase, hyphen-safe ``.md`` filename.
    """
    parsed = urlparse(normalize_url(url))
    segments = [s for s in parsed.path.split("/") if s]

    name = "-".join(segments) if segments else "index"
    if parsed.query:
        name = f"{name}-{parsed.query}"

    stem = _sanitize(name)
    if len(stem) > MAX_STEM_LENGTH:
        digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8]
        stem = f"{stem[:MAX_STEM_LENGTH]}-{digest}"
    return stem + ".md"


def ensure_output_dir(path: Path) -> None:
    """Create the output directory (and any missing parents) if it does not exist.

    Args:
        path: The directory path to create.

    Raises:
        SystemExit: If the directory cannot be created (e.g. permission denied).
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"Cannot create output directory {path}: {exc}") from exc


def list_outputs(base_dir: Path) -> list:
    """Return metadata for every crawl output directory found under ``base_dir``.

    Each entry in the returned list is a dict with the keys:

    - ``name`` (str): directory name.
    - ``file_count`` (int): number of ``.md`` files inside.
    - ``total_size`` (int): combined size of all ``.md`` files in bytes.
    - ``last_modified`` (str): most recent ``.md`` file modification time,
      formatted as ``YYYY-MM-DD HH:MM``. Falls back to the directory mtime
      when the directory contains no ``.md`` files.

    Args:
        base_dir: Root directory that contains crawl output sub-directories.

    Returns:
        A list of metadata dicts sorted alphabetically by directory name.
        Returns an empty list if ``base_dir`` does not exist.
    """
    results = []
    if not base_dir.exists():
        return results

    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir():
            continue
        md_files = list(entry.glob("*.md"))
        total_size = sum(f.stat().st_size for f in md_files)
        if md_files:
            last_mod = max(f.stat().st_mtime for f in md_files)
        else:
            last_mod = entry.stat().st_mtime
        results.append({
            "name": entry.name,
            "file_count": len(md_files),
            "total_size": total_size,
            "last_modified": datetime.fromtimestamp(last_mod).strftime("%Y-%m-%d %H:%M"),
        })
    return results
