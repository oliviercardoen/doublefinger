"""Output directory and filename management for doublefinger.

Provides helpers to:
- Derive a structured directory name from a seed URL (reversed hostname + first path segment).
- Derive a per-page Markdown filename from a page URL.
- Create the output directory on disk, with a clear error on failure.
- List all existing crawl output directories with file count, size, and modification time.
"""

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def _sanitize(segment: str) -> str:
    """Lowercase a string and replace any character outside [a-z0-9.-] with a hyphen."""
    return re.sub(r"[^a-z0-9.\-]", "-", segment.lower())


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

    All non-empty path segments are joined with hyphens and suffixed with
    ``.md``. A root URL (no path segments) maps to ``index.md``.

    Examples::

        https://iac.goffinet.org/ansible-fondamental/installation-ansible/
            →  ansible-fondamental-installation-ansible.md
        https://iac.goffinet.org/ansible-fondamental/
            →  ansible-fondamental.md
        https://iac.goffinet.org/
            →  index.md

    Args:
        url: The URL of the page that was crawled.

    Returns:
        A lowercase, hyphen-safe ``.md`` filename.
    """
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]

    if not segments:
        return "index.md"

    name = "-".join(segments)
    return _sanitize(name) + ".md"


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
