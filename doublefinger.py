import argparse
import asyncio
import sys
from pathlib import Path

from config import ConfigError, load_config, apply_overrides
from crawler import derive_match_pattern, crawl_site
from outputs import derive_output_name, ensure_output_dir, list_outputs


def cmd_crawl(args, cfg):
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
        )
    )


def cmd_list(args, cfg):
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
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def build_parser():
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

    subparsers.add_parser("list", help="List crawl output directories")

    return parser


def main():
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
