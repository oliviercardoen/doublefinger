import os
import tempfile
import time
import unittest
from pathlib import Path


class TestOutputDirName(unittest.TestCase):
    def _derive(self, url):
        from outputs import derive_output_name
        return derive_output_name(url)

    def test_url_with_path_segment(self):
        self.assertEqual(
            self._derive("https://iac.goffinet.org/ansible-fondamental/"),
            "org.goffinet.iac.ansible-fondamental",
        )

    def test_url_root_only(self):
        self.assertEqual(
            self._derive("https://iac.goffinet.org/"),
            "org.goffinet.iac",
        )

    def test_url_with_nested_path_takes_first_segment(self):
        self.assertEqual(
            self._derive("https://docs.example.com/guide/intro"),
            "com.example.docs.guide",
        )

    def test_url_no_path(self):
        self.assertEqual(
            self._derive("https://example.com"),
            "com.example",
        )

    def test_url_multi_level_tld(self):
        self.assertEqual(
            self._derive("https://sub.domain.example.co.uk/path/to/page"),
            "uk.co.example.domain.sub.path",
        )


class TestPageFilename(unittest.TestCase):
    def _filename(self, url):
        from outputs import derive_page_filename
        return derive_page_filename(url)

    def test_nested_page_path(self):
        self.assertEqual(
            self._filename(
                "https://iac.goffinet.org/ansible-fondamental/installation-ansible/"
            ),
            "ansible-fondamental-installation-ansible.md",
        )

    def test_single_segment_path(self):
        self.assertEqual(
            self._filename("https://iac.goffinet.org/ansible-fondamental/"),
            "ansible-fondamental.md",
        )

    def test_root_path(self):
        self.assertEqual(
            self._filename("https://iac.goffinet.org/"),
            "index.md",
        )


class TestOutputDirectory(unittest.TestCase):
    def test_output_dir_created_if_missing(self):
        from outputs import ensure_output_dir
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_subdir"
            self.assertFalse(new_dir.exists())
            ensure_output_dir(new_dir)
            self.assertTrue(new_dir.exists())

    def test_list_command_returns_metadata(self):
        from outputs import list_outputs
        with tempfile.TemporaryDirectory() as base:
            base_path = Path(base)
            crawl_dir = base_path / "com.example"
            crawl_dir.mkdir()
            (crawl_dir / "index.md").write_text("# Hello")
            (crawl_dir / "page.md").write_text("# Page")

            results = list_outputs(base_path)
            self.assertEqual(len(results), 1)
            entry = results[0]
            self.assertEqual(entry["name"], "com.example")
            self.assertEqual(entry["file_count"], 2)
            self.assertGreater(entry["total_size"], 0)
            self.assertIn("last_modified", entry)


class TestNormalizeUrl(unittest.TestCase):
    def _norm(self, url):
        from outputs import normalize_url
        return normalize_url(url)

    def test_trailing_slash_removed(self):
        self.assertEqual(
            self._norm("https://example.com/docs/"),
            "https://example.com/docs",
        )

    def test_scheme_and_host_lowercased(self):
        self.assertEqual(
            self._norm("HTTPS://Example.COM/Docs"),
            "https://example.com/Docs",
        )

    def test_fragment_dropped(self):
        self.assertEqual(
            self._norm("https://example.com/docs#installation"),
            "https://example.com/docs",
        )

    def test_default_port_dropped_custom_port_kept(self):
        self.assertEqual(self._norm("https://example.com:443/docs"),
                         "https://example.com/docs")
        self.assertEqual(self._norm("http://example.com:8080/docs"),
                         "http://example.com:8080/docs")

    def test_tracking_parameters_stripped(self):
        self.assertEqual(
            self._norm("https://example.com/docs?utm_source=news&fbclid=abc"),
            "https://example.com/docs",
        )

    def test_meaningful_parameters_kept_and_sorted(self):
        self.assertEqual(
            self._norm("https://example.com/blog?b=2&a=1"),
            "https://example.com/blog?a=1&b=2",
        )

    def test_repeated_slashes_collapsed(self):
        self.assertEqual(
            self._norm("https://example.com//docs//api/"),
            "https://example.com/docs/api",
        )

    def test_root_url_normalizes_to_single_slash(self):
        self.assertEqual(self._norm("https://example.com"), "https://example.com/")
        self.assertEqual(self._norm("https://example.com/"), "https://example.com/")

    def test_variants_of_same_page_share_one_identity(self):
        """The whole point: these five spellings are one page, so one key."""
        variants = [
            "https://example.com/docs/",
            "https://example.com/docs",
            "https://example.com/docs/#intro",
            "https://example.com/docs/?utm_source=twitter",
            "HTTPS://example.com:443/docs/",
        ]
        self.assertEqual(len({self._norm(v) for v in variants}), 1)

    def test_relative_url_returned_unchanged(self):
        self.assertEqual(self._norm("/docs/intro"), "/docs/intro")


class TestPageFilenameNormalization(unittest.TestCase):
    def _filename(self, url):
        from outputs import derive_page_filename
        return derive_page_filename(url)

    def test_url_variants_produce_one_filename(self):
        self.assertEqual(
            self._filename("https://example.com/docs/?utm_source=x#intro"),
            self._filename("https://example.com/docs"),
        )

    def test_query_kept_so_paginated_pages_do_not_collide(self):
        """?page=2 must not overwrite the unparameterised page."""
        self.assertEqual(self._filename("https://example.com/blog?page=2"),
                         "blog-page-2.md")
        self.assertNotEqual(self._filename("https://example.com/blog?page=2"),
                            self._filename("https://example.com/blog"))

    def test_very_long_path_is_truncated_with_digest(self):
        from outputs import MAX_STEM_LENGTH
        url = "https://example.com/" + "/".join(f"segment{i}" for i in range(60))
        name = self._filename(url)
        self.assertTrue(name.endswith(".md"))
        self.assertLessEqual(len(name), MAX_STEM_LENGTH + 12)

    def test_long_paths_differing_at_the_end_stay_distinct(self):
        base = "https://example.com/" + "/".join(f"segment{i}" for i in range(60))
        self.assertNotEqual(self._filename(base + "/alpha"),
                            self._filename(base + "/omega"))


if __name__ == "__main__":
    unittest.main()
