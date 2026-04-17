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


if __name__ == "__main__":
    unittest.main()
