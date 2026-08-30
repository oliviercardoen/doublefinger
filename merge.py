"""Merging crawl output directories for doublefinger.

Crawling a site from several entry points leaves the same pages spread over
several directories — ``com.site`` from a root crawl and ``com.site.docs``
from a section crawl both hold ``docs-intro.md``. :func:`merge_outputs`
folds those directories into one without ever overwriting a page silently.

Identity is decided in two steps:

1. **By URL.** The source manifests say which URL produced which file, so
   the same page collected twice is recognised even if its content has since
   changed. When two copies disagree, the more recently crawled one wins.
2. **By content hash.** Files with no manifest entry, or pages that moved to
   a new URL, are still de-duplicated when their bytes are identical.

A filename that two *different* pages would claim is not overwritten: the
second copy is given a short digest suffix, and the rename is reported.

The merge is non-destructive — sources are copied, never moved or removed —
and it writes a manifest into the destination so the merged directory stays
resumable by a later crawl.
"""

import shutil
from pathlib import Path

from manifest import file_hash, load_manifest, new_manifest, save_manifest


def resolve_output_dir(name: str, base_dir: Path) -> Path:
    """Resolve a crawl directory given either a path or a bare name.

    Bare names — the ones ``doublefinger list`` prints — are looked up under
    ``base_dir``; anything that looks like a path is used as given.

    Args:
        name: Directory name (``com.example.docs``) or path (``/tmp/crawl``).
        base_dir: Root directory holding crawl outputs.

    Returns:
        The resolved path, which is not guaranteed to exist.
    """
    path = Path(name).expanduser()
    if path.is_dir() or path.is_absolute() or "/" in str(name):
        return path
    return base_dir / name


def _suffixed(filename: str, digest: str) -> str:
    """Return ``filename`` with a short content digest inserted before ``.md``."""
    stem = filename[:-3] if filename.endswith(".md") else filename
    return f"{stem}-{digest[:8]}.md"


def _index_directory(directory: Path) -> list:
    """Describe every Markdown file in a crawl directory.

    Each record carries the file's path and name, the URL that produced it
    (``None`` when the manifest does not know), a hash of its current bytes,
    and the crawl metadata needed to arbitrate between two copies.

    Args:
        directory: A crawl output directory.

    Returns:
        A list of record dicts, sorted by filename.
    """
    manifest = load_manifest(directory)
    by_file = {}
    for url, entry in manifest["pages"].items():
        if isinstance(entry, dict) and entry.get("file"):
            by_file[entry["file"]] = (url, entry)

    records = []
    for path in sorted(directory.glob("*.md")):
        url, entry = by_file.get(path.name, (None, {}))
        records.append({
            "path": path,
            "file": path.name,
            "url": url,
            "sha256": file_hash(path),
            "crawled_at": entry.get("crawled_at", ""),
            "links": entry.get("links", []),
        })
    return records


def _identity(record: dict) -> str:
    """Return the key under which a record competes with others.

    Pages known to the manifest are identified by URL. Files with no
    manifest entry fall back to their filename, which keeps two unrelated
    orphans apart while still letting the content hash catch true duplicates.
    """
    if record["url"]:
        return record["url"]
    return f"file:{record['file']}"


def merge_outputs(sources: list, dest: Path, dry_run: bool = False) -> dict:
    """Merge several crawl directories into one, de-duplicating pages.

    Sources are processed in the order given, so the first directory listed
    wins ties that recency cannot settle. Anything already present in
    ``dest`` is taken into account and never disturbed.

    Args:
        sources: Crawl output directories to merge, in priority order.
        dest: Destination directory. Created if missing; may already hold a
            previous crawl or merge.
        dry_run: When ``True``, decide everything and report it, but write
            nothing to disk.

    Returns:
        A report dict with the keys ``copied``, ``skipped_identical``,
        ``replaced_older``, ``kept_newer``, ``renamed`` and ``total_pages``.
        Every entry is a printable string except ``renamed`` (pairs of
        original and new filename) and ``total_pages`` (an int).

    Raises:
        SystemExit: If a source directory is missing, or if ``dest`` is also
            listed as a source.
    """
    for source in sources:
        if not source.is_dir():
            raise SystemExit(f"Not a crawl directory: {source}")
        if dest.is_dir() and source.resolve() == dest.resolve():
            raise SystemExit(f"Destination {dest} cannot also be a source")

    report = {
        "copied": [],
        "skipped_identical": [],
        "replaced_older": [],
        "kept_newer": [],
        "renamed": [],
        "total_pages": 0,
    }

    chosen = {}       # identity key -> record kept for that page
    by_hash = {}      # content hash -> identity key already holding it
    used_names = {}   # destination filename -> identity key that owns it

    def adopt(record, dest_name, in_place):
        key = _identity(record)
        record = dict(record, dest_name=dest_name, in_place=in_place)
        chosen[key] = record
        by_hash.setdefault(record["sha256"], key)
        used_names[dest_name] = key
        return record

    # Whatever the destination already holds takes precedence: it is never
    # renamed, re-copied, or replaced by an older source.
    if dest.is_dir():
        for record in _index_directory(dest):
            adopt(record, record["file"], in_place=True)

    for source in sources:
        for record in _index_directory(source):
            key = _identity(record)
            label = f"{source.name}/{record['file']}"
            existing = chosen.get(key)

            if existing is not None:
                if existing["sha256"] == record["sha256"]:
                    report["skipped_identical"].append(label)
                elif record["crawled_at"] > existing["crawled_at"]:
                    # Same page, fresher copy: keep the destination filename
                    # already allocated for it and swap in the new content.
                    adopt(record, existing["dest_name"], in_place=False)
                    report["replaced_older"].append(
                        f"{label} (newer than the copy already merged)"
                    )
                else:
                    report["kept_newer"].append(
                        f"{label} (older than the copy already merged)"
                    )
                continue

            if record["sha256"] in by_hash:
                report["skipped_identical"].append(
                    f"{label} (identical to {by_hash[record['sha256']]})"
                )
                continue

            dest_name = record["file"]
            if dest_name in used_names:
                # A different page wants a filename that is taken; keep both.
                dest_name = _suffixed(dest_name, record["sha256"])
                report["renamed"].append((label, dest_name))

            adopt(record, dest_name, in_place=False)
            report["copied"].append(f"{label} → {dest_name}")

    report["total_pages"] = len(chosen)

    if dry_run:
        return report

    dest.mkdir(parents=True, exist_ok=True)
    merged = new_manifest()
    for key, record in chosen.items():
        if not record["in_place"]:
            shutil.copy2(record["path"], dest / record["dest_name"])
        if record["url"]:
            merged["pages"][record["url"]] = {
                "file": record["dest_name"],
                "sha256": record["sha256"],
                "crawled_at": record["crawled_at"],
                "links": record["links"],
            }
    save_manifest(dest, merged)

    return report
