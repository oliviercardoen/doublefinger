"""doublefinger — CLI entry point.

Exposes three sub-commands via argparse (stdlib only):

    crawl   Crawl a website and save pages as Markdown files.
    list    List all existing crawl output directories.
    merge   Merge several crawl directories into one, de-duplicating pages.

Usage::

    python doublefinger.py crawl <url> [options]
    python doublefinger.py list
    python doublefinger.py merge <dir> [<dir> ...] --into <dest>
"""

import argparse
import asyncio
import sys
from pathlib import Path

from config import ConfigError, load_config, apply_overrides
from crawler import derive_match_pattern, crawl_site
from merge import merge_outputs, resolve_output_dir
from outputs import derive_output_name, ensure_output_dir, list_outputs


def cmd_crawl(args: argparse.Namespace, cfg: dict) -> None:
    """Execute the ``crawl`` sub-command.

    Resolves the match pattern and output directory from CLI flags and
    config, creates the output directory, then delegates to
    :func:`crawler.crawl_site` via ``asyncio.run``.

    Resuming is the default: pages already recorded in the output
    directory's manifest are skipped unless ``--force`` was given.

    Args:
        args: Parsed CLI arguments (from :func:`build_parser`).
        cfg: Effective configuration dict (overrides already applied).
    """
    match_pattern = args.match or derive_match_pattern(args.url)

    output_base = Path(cfg["output"]["base_dir"])
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = output_base / derive_output_name(args.url)

    ensure_output_dir(output_dir)

    max_pages = args.max_pages if args.max_pages is not None else cfg["crawl"]["default_max_pages"]

    asyncio.run(
        crawl_site(
            seed_url=args.url,
            match_pattern=match_pattern,
            max_pages=max_pages,
            output_dir=output_dir,
            use_browser=args.browser,
            no_cache=args.no_cache,
            wait=args.wait,
            resume=not args.force,
        )
    )


def cmd_list(args: argparse.Namespace, cfg: dict) -> None:
    """Execute the ``list`` sub-command.

    Prints a formatted table of all crawl output directories found under
    ``cfg["output"]["base_dir"]``, including file count, human-readable
    total size, and last modification date.

    Args:
        args: Parsed CLI arguments (unused, kept for uniform signature).
        cfg: Effective configuration dict.
    """
    base_dir = Path(cfg["output"]["base_dir"])
    entries = list_outputs(base_dir)

    if not entries:
        print(f"No crawl outputs found in {base_dir}")
        return

    print(f"{'Directory':<45} {'Files':>6} {'Size':>10} {'Last Modified'}")
    print("-" * 80)
    for e in entries:
        size_str = _human_size(e["total_size"])
        print(f"{e['name']:<45} {e['file_count']:>6} {size_str:>10} {e['last_modified']}")


def cmd_merge(args: argparse.Namespace, cfg: dict) -> None:
    """Execute the ``merge`` sub-command.

    Resolves each source and the destination against the configured
    ``base_dir``, delegates to :func:`merge.merge_outputs`, then prints what
    was copied, de-duplicated, renamed, or superseded.

    Args:
        args: Parsed CLI arguments (from :func:`build_parser`).
        cfg: Effective configuration dict.
    """
    base_dir = Path(cfg["output"]["base_dir"])
    sources = [resolve_output_dir(name, base_dir) for name in args.sources]
    dest = resolve_output_dir(args.into, base_dir)

    report = merge_outputs(sources, dest, dry_run=args.dry_run)

    for label in report["copied"]:
        print(f"  copy      {label}")
    for original, new_name in report["renamed"]:
        print(f"  rename    {original} → {new_name} (filename already taken)")
    for label in report["replaced_older"]:
        print(f"  replace   {label}")
    for label in report["kept_newer"]:
        print(f"  keep      {label}")
    for label in report["skipped_identical"]:
        print(f"  duplicate {label}")

    prefix = "Would merge" if args.dry_run else "Merged"
    print(
        f"\n{prefix} {len(sources)} director{'y' if len(sources) == 1 else 'ies'} "
        f"into {dest}: {report['total_pages']} page(s), "
        f"{len(report['copied'])} copied, "
        f"{len(report['skipped_identical'])} duplicate(s) skipped."
    )
    if args.dry_run:
        print("Nothing was written (--dry-run).")


def _human_size(size: int) -> str:
    """Convert a byte count to a human-readable string (B, KB, MB, GB, TB).

    Args:
        size: File size in bytes.

    Returns:
        A string such as ``"1.4KB"`` or ``"23.0MB"``.
    """
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _non_negative_int(value: str) -> int:
    """Argparse type function that accepts only non-negative integers.

    Args:
        value: Raw string value from the command line.

    Returns:
        The parsed integer.

    Raises:
        argparse.ArgumentTypeError: If ``value`` parses to a negative integer.
    """
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid integer")
    if ivalue < 0:
        raise argparse.ArgumentTypeError(f"--wait must be >= 0, got {ivalue}")
    return ivalue


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser.

    Defines the ``crawl`` and ``list`` sub-commands with all their
    arguments and help strings.

    Returns:
        A fully configured :class:`argparse.ArgumentParser` instance.
    """
    parser = argparse.ArgumentParser(
        prog="doublefinger",
        description="CLI wrapper around Crawl4AI — crawl websites to clean Markdown.",
    )
    subparsers = parser.add_subparsers(dest="command")

    crawl_p = subparsers.add_parser("crawl", help="Crawl a website")
    crawl_p.add_argument("url", help="Seed URL to start crawling from")
    crawl_p.add_argument("--match", help="URL glob pattern to follow links")
    crawl_p.add_argument("--max-pages", type=int, default=None, dest="max_pages",
                         help="Maximum number of pages to crawl (0 = unlimited)")
    crawl_p.add_argument("--output-dir", dest="output_dir",
                         help="Override the default output directory")
    crawl_p.add_argument("--browser", action="store_true",
                         help="Force Playwright headless browser mode")
    crawl_p.add_argument("--no-cache", action="store_true", dest="no_cache",
                         help="Disable Crawl4AI's built-in cache")
    crawl_p.add_argument(
        "--wait",
        type=_non_negative_int,
        default=0,
        metavar="SECONDS",
        help=(
            "Seconds to wait after page load before extracting content. "
            "Use with --browser for JavaScript-heavy pages (default: 0)"
        ),
    )

    resume_group = crawl_p.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip pages already recorded in the output directory's manifest "
            "and only fetch new ones (default)"
        ),
    )
    resume_group.add_argument(
        "--force",
        action="store_true",
        help="Re-crawl every page and rebuild the manifest from scratch",
    )

    subparsers.add_parser("list", help="List crawl output directories")

    merge_p = subparsers.add_parser(
        "merge",
        help="Merge crawl directories into one, de-duplicating pages",
    )
    merge_p.add_argument(
        "sources",
        nargs="+",
        metavar="DIR",
        help=(
            "Crawl directories to merge, as names shown by `list` or as paths. "
            "Processed in order: the first one wins ties."
        ),
    )
    merge_p.add_argument(
        "--into",
        required=True,
        metavar="DEST",
        help="Destination directory, as a name or a path. Created if missing",
    )
    merge_p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Report what would be merged without writing anything",
    )

    return parser


def main() -> None:
    """Parse CLI arguments, load config, apply overrides, and dispatch to a sub-command.

    Exits with status 1 if no sub-command is given or if the config file
    is malformed.
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Collect only the CLI flags that were explicitly provided so that
    # apply_overrides does not stomp on config defaults unnecessarily.
    overrides = {}
    if hasattr(args, "output_dir") and args.output_dir:
        overrides["output_dir"] = args.output_dir
    if hasattr(args, "max_pages") and args.max_pages is not None:
        overrides["max_pages"] = args.max_pages
    cfg = apply_overrides(cfg, **overrides)

    if args.command == "crawl":
        cmd_crawl(args, cfg)
    elif args.command == "list":
        cmd_list(args, cfg)
    elif args.command == "merge":
        cmd_merge(args, cfg)


if __name__ == "__main__":
    main()
