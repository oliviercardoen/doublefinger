"""doublefinger — CLI entry point.

Exposes two sub-commands via argparse (stdlib only):

    crawl   Crawl a website and save pages as Markdown files.
    list    List all existing crawl output directories.

Usage::

    python doublefinger.py crawl <url> [options]
    python doublefinger.py list
"""

import argparse
import asyncio
import sys
from pathlib import Path

from config import ConfigError, load_config, apply_overrides
from crawler import derive_match_pattern, crawl_site
from outputs import derive_output_name, ensure_output_dir, list_outputs


def cmd_crawl(args: argparse.Namespace, cfg: dict) -> None:
    """Execute the ``crawl`` sub-command.

    Resolves the match pattern and output directory from CLI flags and
    config, creates the output directory, then delegates to
    :func:`crawler.crawl_site` via ``asyncio.run``.

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

    subparsers.add_parser("list", help="List crawl output directories")

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


if __name__ == "__main__":
    main()
