"""Per-directory crawl manifest for doublefinger.

Every output directory carries a ``.doublefinger.json`` manifest recording,
for each page written: the Markdown file it produced, a SHA-256 of that
content, the crawl timestamp, and the internal links that were followed
from it.

The stored links are what make ``--resume`` useful. A page already in the
manifest is not re-fetched, but its recorded links are pushed back onto the
crawl queue, so the frontier survives across runs and only genuinely new
URLs cost a request.

The content hashes are also what a future ``merge`` command needs to spot
identical pages across two output directories.

A missing manifest is normal (first crawl); a corrupt one is reported as a
warning and treated as empty, never as a fatal error.
"""

import hashlib
import json
import os
import warnings
from datetime import datetime
from pathlib import Path

MANIFEST_NAME = ".doublefinger.json"
MANIFEST_VERSION = 1


def manifest_path(output_dir: Path) -> Path:
    """Return the manifest file path for a given output directory."""
    return output_dir / MANIFEST_NAME


def new_manifest() -> dict:
    """Return an empty manifest structure."""
    return {"version": MANIFEST_VERSION, "pages": {}}


def load_manifest(output_dir: Path) -> dict:
    """Load the manifest stored in ``output_dir``, or return an empty one.

    Args:
        output_dir: Directory that may contain a ``.doublefinger.json``.

    Returns:
        The parsed manifest dict. An absent file yields an empty manifest.
        A file that cannot be parsed, or whose shape is not recognised,
        emits a :class:`UserWarning` and also yields an empty manifest —
        a damaged manifest costs a full re-crawl, never a crash.
    """
    path = manifest_path(output_dir)
    if not path.exists():
        return new_manifest()

    try:
        with open(path, "rb") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        warnings.warn(
            f"Ignoring unreadable manifest {path}: {exc}", UserWarning, stacklevel=2
        )
        return new_manifest()

    if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
        warnings.warn(
            f"Ignoring malformed manifest {path}", UserWarning, stacklevel=2
        )
        return new_manifest()

    data.setdefault("version", MANIFEST_VERSION)
    return data


def save_manifest(output_dir: Path, manifest: dict) -> None:
    """Write the manifest to ``output_dir`` atomically.

    The manifest is written to a temporary file in the same directory and
    then renamed over the target, so an interrupted crawl can never leave a
    half-written manifest behind.

    Args:
        output_dir: Directory to write the manifest into.
        manifest: The manifest dict to serialise.
    """
    path = manifest_path(output_dir)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def content_hash(text: str) -> str:
    """Return the SHA-256 hex digest of ``text`` (UTF-8 encoded)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_page(
    manifest: dict, url: str, filename: str, content: str, links: list
) -> None:
    """Add or replace the manifest entry for a crawled page.

    Args:
        manifest: The manifest dict to mutate.
        url: Normalized URL of the page, used as the entry key.
        filename: Name of the Markdown file written for this page.
        content: The Markdown that was written, hashed for later comparison.
        links: Normalized internal links followed from this page.
    """
    manifest["pages"][url] = {
        "file": filename,
        "sha256": content_hash(content),
        "crawled_at": datetime.now().isoformat(timespec="seconds"),
        "links": list(links),
    }


def is_recorded(manifest: dict, url: str, output_dir: Path) -> bool:
    """Return True if ``url`` was crawled before and its file is still present.

    A manifest entry whose Markdown file has since been deleted does not
    count as recorded, so removing a file from the output directory is
    enough to make the next resumed crawl fetch that page again.

    Args:
        manifest: The manifest dict to look in.
        url: Normalized URL to check.
        output_dir: Directory the manifest belongs to.
    """
    entry = manifest["pages"].get(url)
    if not isinstance(entry, dict):
        return False
    filename = entry.get("file")
    if not filename:
        return False
    return (output_dir / filename).exists()


def recorded_links(manifest: dict, url: str) -> list:
    """Return the internal links recorded for ``url``, or an empty list.

    Entries written by an older version of doublefinger may have no
    ``links`` key; those simply yield no frontier to restore.
    """
    entry = manifest["pages"].get(url)
    if not isinstance(entry, dict):
        return []
    links = entry.get("links")
    return links if isinstance(links, list) else []
