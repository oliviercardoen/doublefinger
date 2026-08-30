import tempfile
import unittest
from pathlib import Path


def _crawl_dir(base, name, pages):
    """Build a crawl directory from {url: (filename, content, crawled_at)}."""
    from manifest import new_manifest, save_manifest
    directory = Path(base) / name
    directory.mkdir(parents=True)
    manifest = new_manifest()
    for url, (filename, content, crawled_at) in pages.items():
        (directory / filename).write_text(content, encoding="utf-8")
        from manifest import content_hash
        manifest["pages"][url] = {
            "file": filename,
            "sha256": content_hash(content),
            "crawled_at": crawled_at,
            "links": [],
        }
    save_manifest(directory, manifest)
    return directory


def _names(directory):
    return sorted(f.name for f in directory.glob("*.md"))


class TestResolveOutputDir(unittest.TestCase):
    def test_bare_name_resolved_under_base_dir(self):
        from merge import resolve_output_dir
        base = Path("/home/user/Downloads")
        self.assertEqual(
            resolve_output_dir("com.example.docs", base),
            base / "com.example.docs",
        )

    def test_absolute_path_used_as_is(self):
        from merge import resolve_output_dir
        self.assertEqual(
            resolve_output_dir("/tmp/my-crawl", Path("/home/user/Downloads")),
            Path("/tmp/my-crawl"),
        )


class TestMergeDeduplication(unittest.TestCase):
    def test_same_url_in_two_directories_yields_one_file(self):
        """The root crawl and the section crawl both hold /docs/intro."""
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "com.site", {
                "https://site.com/docs/intro": ("docs-intro.md", "# Intro", "2026-08-01T10:00:00"),
                "https://site.com/about": ("about.md", "# About", "2026-08-01T10:00:00"),
            })
            b = _crawl_dir(base, "com.site.docs", {
                "https://site.com/docs/intro": ("docs-intro.md", "# Intro", "2026-08-02T10:00:00"),
                "https://site.com/docs/api": ("docs-api.md", "# API", "2026-08-02T10:00:00"),
            })
            dest = Path(base) / "merged"

            report = merge_outputs([a, b], dest)

            self.assertEqual(_names(dest), ["about.md", "docs-api.md", "docs-intro.md"])
            self.assertEqual(report["total_pages"], 3)
            self.assertEqual(len(report["skipped_identical"]), 1)

    def test_identical_content_under_different_urls_is_deduplicated(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "one", {
                "https://site.com/a": ("a.md", "# Same", "2026-08-01T10:00:00"),
            })
            b = _crawl_dir(base, "two", {
                "https://site.com/b": ("b.md", "# Same", "2026-08-01T10:00:00"),
            })
            dest = Path(base) / "merged"

            report = merge_outputs([a, b], dest)

            self.assertEqual(_names(dest), ["a.md"])
            self.assertEqual(len(report["skipped_identical"]), 1)

    def test_newer_copy_of_a_changed_page_wins(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "old", {
                "https://site.com/docs": ("docs.md", "# Old text", "2026-08-01T10:00:00"),
            })
            b = _crawl_dir(base, "new", {
                "https://site.com/docs": ("docs.md", "# New text", "2026-08-02T10:00:00"),
            })
            dest = Path(base) / "merged"

            report = merge_outputs([a, b], dest)

            self.assertEqual((dest / "docs.md").read_text(encoding="utf-8"), "# New text")
            self.assertEqual(len(report["replaced_older"]), 1)

    def test_older_copy_does_not_overwrite_a_newer_one(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            new = _crawl_dir(base, "new", {
                "https://site.com/docs": ("docs.md", "# New text", "2026-08-02T10:00:00"),
            })
            old = _crawl_dir(base, "old", {
                "https://site.com/docs": ("docs.md", "# Old text", "2026-08-01T10:00:00"),
            })
            dest = Path(base) / "merged"

            report = merge_outputs([new, old], dest)

            self.assertEqual((dest / "docs.md").read_text(encoding="utf-8"), "# New text")
            self.assertEqual(len(report["kept_newer"]), 1)


class TestMergeConflicts(unittest.TestCase):
    def test_different_pages_claiming_one_filename_are_both_kept(self):
        """A filename collision must never silently drop a page."""
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "one", {
                "https://site.com/a_b": ("a-b.md", "# Underscore", "2026-08-01T10:00:00"),
            })
            b = _crawl_dir(base, "two", {
                "https://site.com/a-b": ("a-b.md", "# Hyphen", "2026-08-01T10:00:00"),
            })
            dest = Path(base) / "merged"

            report = merge_outputs([a, b], dest)

            self.assertEqual(len(_names(dest)), 2)
            self.assertEqual(len(report["renamed"]), 1)
            contents = {(dest / n).read_text(encoding="utf-8") for n in _names(dest)}
            self.assertEqual(contents, {"# Underscore", "# Hyphen"})

    def test_files_without_a_manifest_are_merged_by_content(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = Path(base) / "legacy-one"
            a.mkdir()
            (a / "page.md").write_text("# Legacy", encoding="utf-8")
            b = Path(base) / "legacy-two"
            b.mkdir()
            (b / "page.md").write_text("# Legacy", encoding="utf-8")
            dest = Path(base) / "merged"

            report = merge_outputs([a, b], dest)

            self.assertEqual(_names(dest), ["page.md"])
            self.assertEqual(len(report["skipped_identical"]), 1)


class TestMergeDestination(unittest.TestCase):
    def test_existing_destination_content_is_preserved(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            dest = _crawl_dir(base, "merged", {
                "https://site.com/kept": ("kept.md", "# Kept", "2026-08-01T10:00:00"),
            })
            source = _crawl_dir(base, "source", {
                "https://site.com/new": ("new.md", "# New", "2026-08-01T10:00:00"),
            })

            merge_outputs([source], dest)

            self.assertEqual(_names(dest), ["kept.md", "new.md"])
            self.assertEqual((dest / "kept.md").read_text(encoding="utf-8"), "# Kept")

    def test_merged_directory_carries_a_manifest(self):
        """The destination must stay resumable by a later crawl."""
        from manifest import load_manifest
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "one", {
                "https://site.com/a": ("a.md", "# A", "2026-08-01T10:00:00"),
            })
            dest = Path(base) / "merged"

            merge_outputs([a], dest)

            pages = load_manifest(dest)["pages"]
            self.assertEqual(set(pages), {"https://site.com/a"})
            self.assertEqual(pages["https://site.com/a"]["file"], "a.md")

    def test_renamed_page_is_recorded_under_its_new_filename(self):
        from manifest import load_manifest
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "one", {
                "https://site.com/a_b": ("a-b.md", "# One", "2026-08-01T10:00:00"),
            })
            b = _crawl_dir(base, "two", {
                "https://site.com/a-b": ("a-b.md", "# Two", "2026-08-01T10:00:00"),
            })
            dest = Path(base) / "merged"

            merge_outputs([a, b], dest)

            pages = load_manifest(dest)["pages"]
            for url, entry in pages.items():
                self.assertTrue((dest / entry["file"]).exists(), f"missing file for {url}")

    def test_dry_run_writes_nothing(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "one", {
                "https://site.com/a": ("a.md", "# A", "2026-08-01T10:00:00"),
            })
            dest = Path(base) / "merged"

            report = merge_outputs([a], dest, dry_run=True)

            self.assertFalse(dest.exists())
            self.assertEqual(report["total_pages"], 1)
            self.assertEqual(len(report["copied"]), 1)

    def test_sources_are_left_untouched(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "one", {
                "https://site.com/a": ("a.md", "# A", "2026-08-01T10:00:00"),
            })
            dest = Path(base) / "merged"

            merge_outputs([a], dest)

            self.assertEqual(_names(a), ["a.md"])
            self.assertEqual((a / "a.md").read_text(encoding="utf-8"), "# A")


class TestMergeErrors(unittest.TestCase):
    def test_missing_source_exits_with_a_clear_message(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            missing = Path(base) / "nope"
            with self.assertRaises(SystemExit) as ctx:
                merge_outputs([missing], Path(base) / "merged")
            self.assertIn("Not a crawl directory", str(ctx.exception))

    def test_destination_cannot_also_be_a_source(self):
        from merge import merge_outputs
        with tempfile.TemporaryDirectory() as base:
            a = _crawl_dir(base, "one", {
                "https://site.com/a": ("a.md", "# A", "2026-08-01T10:00:00"),
            })
            with self.assertRaises(SystemExit) as ctx:
                merge_outputs([a], a)
            self.assertIn("cannot also be a source", str(ctx.exception))


class TestMergeCli(unittest.TestCase):
    def _parse(self, argv):
        from doublefinger import build_parser
        return build_parser().parse_args(argv)

    def test_merge_accepts_several_sources_and_a_destination(self):
        args = self._parse(["merge", "com.a", "com.b", "--into", "com.all"])
        self.assertEqual(args.sources, ["com.a", "com.b"])
        self.assertEqual(args.into, "com.all")
        self.assertFalse(args.dry_run)

    def test_into_is_required(self):
        with self.assertRaises(SystemExit):
            self._parse(["merge", "com.a"])

    def test_dry_run_flag_parsed(self):
        args = self._parse(["merge", "com.a", "--into", "com.all", "--dry-run"])
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()
