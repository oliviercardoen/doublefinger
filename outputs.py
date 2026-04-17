import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def _sanitize(segment: str) -> str:
    return re.sub(r"[^a-z0-9.\-]", "-", segment.lower())


def derive_output_name(url: str) -> str:
    parsed = urlparse(url)
    host_parts = parsed.hostname.split(".")
    reversed_host = ".".join(reversed(host_parts))

    path_segments = [s for s in parsed.path.split("/") if s]
    if not path_segments:
        return _sanitize(reversed_host)

    first_segment = path_segments[0]
    return _sanitize(f"{reversed_host}.{first_segment}")


def derive_page_filename(url: str) -> str:
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]

    if not segments:
        return "index.md"

    name = "-".join(segments)
    return _sanitize(name) + ".md"


def ensure_output_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"Cannot create output directory {path}: {exc}") from exc


def list_outputs(base_dir: Path) -> list:
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
