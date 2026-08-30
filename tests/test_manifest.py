import json
import tempfile
import unittest
from pathlib import Path


class TestManifestRoundTrip(unittest.TestCase):
    def test_missing_manifest_returns_empty(self):
        from manifest import load_manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = load_manifest(Path(tmpdir))
            self.assertEqual(manifest["pages"], {})

    def test_recorded_page_survives_save_and_load(self):
        from manifest import load_manifest, record_page, save_manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            manifest = load_manifest(out)
            record_page(manifest, "https://example.com/docs", "docs.md",
                        "# Docs", ["https://example.com/docs/api"])
            save_manifest(out, manifest)

            reloaded = load_manifest(out)
            entry = reloaded["pages"]["https://example.com/docs"]
            self.assertEqual(entry["file"], "docs.md")
            self.assertEqual(entry["links"], ["https://example.com/docs/api"])
            self.assertIn("crawled_at", entry)

    def test_content_hash_matches_identical_content(self):
        from manifest import content_hash
        self.assertEqual(content_hash("# Docs"), content_hash("# Docs"))
        self.assertNotEqual(content_hash("# Docs"), content_hash("# Other"))

    def test_manifest_is_hidden_from_list_outputs(self):
        """The manifest must not be counted as a crawled page."""
        from manifest import new_manifest, save_manifest
        from outputs import list_outputs
        with tempfile.TemporaryDirectory() as base:
            crawl_dir = Path(base) / "com.example"
            crawl_dir.mkdir()
            (crawl_dir / "index.md").write_text("# Hello")
            save_manifest(crawl_dir, new_manifest())

            entry = list_outputs(Path(base))[0]
            self.assertEqual(entry["file_count"], 1)


class TestManifestResilience(unittest.TestCase):
    def test_corrupt_manifest_warns_and_returns_empty(self):
        from manifest import MANIFEST_NAME, load_manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            (out / MANIFEST_NAME).write_text("{not valid json")
            with self.assertWarns(UserWarning):
                manifest = load_manifest(out)
            self.assertEqual(manifest["pages"], {})

    def test_manifest_of_unexpected_shape_warns_and_returns_empty(self):
        from manifest import MANIFEST_NAME, load_manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            (out / MANIFEST_NAME).write_text(json.dumps(["not", "a", "dict"]))
            with self.assertWarns(UserWarning):
                manifest = load_manifest(out)
            self.assertEqual(manifest["pages"], {})


class TestIsRecorded(unittest.TestCase):
    def _recorded_dir(self, tmpdir, write_file=True):
        from manifest import record_page, new_manifest
        out = Path(tmpdir)
        manifest = new_manifest()
        record_page(manifest, "https://example.com/docs", "docs.md", "# Docs", [])
        if write_file:
            (out / "docs.md").write_text("# Docs")
        return out, manifest

    def test_recorded_page_with_file_present(self):
        from manifest import is_recorded
        with tempfile.TemporaryDirectory() as tmpdir:
            out, manifest = self._recorded_dir(tmpdir)
            self.assertTrue(is_recorded(manifest, "https://example.com/docs", out))

    def test_recorded_page_whose_file_was_deleted_is_not_recorded(self):
        """Deleting a .md file is enough to make the next crawl fetch it again."""
        from manifest import is_recorded
        with tempfile.TemporaryDirectory() as tmpdir:
            out, manifest = self._recorded_dir(tmpdir, write_file=False)
            self.assertFalse(is_recorded(manifest, "https://example.com/docs", out))

    def test_unknown_url_is_not_recorded(self):
        from manifest import is_recorded
        with tempfile.TemporaryDirectory() as tmpdir:
            out, manifest = self._recorded_dir(tmpdir)
            self.assertFalse(is_recorded(manifest, "https://example.com/other", out))

    def test_recorded_links_defaults_to_empty_for_legacy_entry(self):
        from manifest import recorded_links
        manifest = {"version": 1, "pages": {"https://example.com/": {"file": "index.md"}}}
        self.assertEqual(recorded_links(manifest, "https://example.com/"), [])


if __name__ == "__main__":
    unittest.main()
