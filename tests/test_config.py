import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestConfigDefaults(unittest.TestCase):
    def test_creates_config_with_defaults_if_missing(self):
        from config import load_config
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            cfg = load_config(config_path=config_path)
            self.assertTrue(config_path.exists())
            self.assertEqual(cfg["output"]["base_dir"], str(Path("~/Downloads").expanduser()))
            self.assertEqual(cfg["crawl"]["default_max_pages"], 0)
            self.assertEqual(cfg["crawl"]["default_format"], "markdown")

    def test_reads_values_from_existing_file(self):
        from config import load_config
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                '[output]\nbase_dir = "/tmp/mycrawls"\n\n[crawl]\ndefault_max_pages = 10\ndefault_format = "markdown"\n'
            )
            cfg = load_config(config_path=config_path)
            self.assertEqual(cfg["output"]["base_dir"], "/tmp/mycrawls")
            self.assertEqual(cfg["crawl"]["default_max_pages"], 10)

    def test_base_dir_tilde_is_expanded(self):
        from config import load_config
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                '[output]\nbase_dir = "~/my-crawls"\n\n[crawl]\ndefault_max_pages = 0\ndefault_format = "markdown"\n'
            )
            cfg = load_config(config_path=config_path)
            self.assertFalse(cfg["output"]["base_dir"].startswith("~"))
            self.assertTrue(cfg["output"]["base_dir"].startswith("/"))

    def test_malformed_toml_raises_clear_error(self):
        from config import load_config, ConfigError
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text("this is not valid toml ][[\n")
            with self.assertRaises(ConfigError) as ctx:
                load_config(config_path=config_path)
            self.assertIn(str(config_path), str(ctx.exception))

    def test_cli_flags_override_config_values(self):
        from config import apply_overrides
        cfg = {
            "output": {"base_dir": "/tmp/default"},
            "crawl": {"default_max_pages": 0, "default_format": "markdown"},
        }
        result = apply_overrides(cfg, output_dir="/tmp/override", max_pages=5)
        self.assertEqual(result["output"]["base_dir"], "/tmp/override")
        self.assertEqual(result["crawl"]["default_max_pages"], 5)


class TestEntryPoint(unittest.TestCase):
    def test_entry_point_importable(self):
        import doublefinger
        self.assertTrue(hasattr(doublefinger, "main"))


if __name__ == "__main__":
    unittest.main()
