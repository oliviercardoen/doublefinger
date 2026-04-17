import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestUrlPatternDerivation(unittest.TestCase):
    def _pattern(self, url):
        from crawler import derive_match_pattern
        return derive_match_pattern(url)

    def test_url_with_path_segment(self):
        self.assertEqual(
            self._pattern("https://iac.goffinet.org/ansible-fondamental/"),
            "https://iac.goffinet.org/ansible-fondamental/**",
        )

    def test_url_root(self):
        self.assertEqual(
            self._pattern("https://iac.goffinet.org/"),
            "https://iac.goffinet.org/**",
        )

    def test_url_with_nested_path(self):
        self.assertEqual(
            self._pattern("https://docs.example.com/guide/intro"),
            "https://docs.example.com/guide/**",
        )


class TestCrawlerFailedPage(unittest.TestCase):
    def test_failed_page_logs_warning_does_not_raise(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            mock_result = MagicMock()
            mock_result.success = False
            mock_result.url = "https://example.com/"
            mock_result.markdown = None

            mock_crawler_instance = MagicMock()
            mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
            mock_crawler_instance.__aexit__ = AsyncMock(return_value=False)
            mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

            with patch("crawler.AsyncWebCrawler", return_value=mock_crawler_instance), \
                 patch("crawler.CrawlerRunConfig", return_value=MagicMock()):
                import warnings
                from crawler import crawl_site

                with self.assertWarns(UserWarning):
                    asyncio.run(
                        crawl_site(
                            seed_url="https://example.com/",
                            match_pattern="https://example.com/**",
                            max_pages=1,
                            output_dir=output_dir,
                            use_browser=False,
                            no_cache=False,
                        )
                    )


class TestCrawlerMaxPages(unittest.TestCase):
    def test_max_pages_one_stops_after_one_page(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            mock_result = MagicMock()
            mock_result.success = True
            mock_result.url = "https://example.com/"
            mock_result.markdown = "# Hello"
            mock_result.links = {"internal": []}

            mock_crawler_instance = MagicMock()
            mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
            mock_crawler_instance.__aexit__ = AsyncMock(return_value=False)
            mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

            with patch("crawler.AsyncWebCrawler", return_value=mock_crawler_instance), \
                 patch("crawler.CrawlerRunConfig", return_value=MagicMock()):
                from crawler import crawl_site

                asyncio.run(
                    crawl_site(
                        seed_url="https://example.com/",
                        match_pattern="https://example.com/**",
                        max_pages=1,
                        output_dir=output_dir,
                        use_browser=False,
                        no_cache=False,
                    )
                )

            self.assertEqual(mock_crawler_instance.arun.call_count, 1)


class TestWaitConfig(unittest.TestCase):
    def test_wait_default_is_zero(self):
        """derive_wait_config returns 0.0 when wait=0 (no delay)."""
        from crawler import derive_wait_config
        self.assertEqual(derive_wait_config(0), 0.0)

    def test_wait_passed_to_crawl4ai(self):
        """When wait=2, CrawlerRunConfig is built with delay_before_return_html=2.0."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            mock_result = MagicMock()
            mock_result.success = True
            mock_result.url = "https://example.com/"
            mock_result.markdown = "# Hello"
            mock_result.links = {"internal": []}

            mock_crawler_instance = MagicMock()
            mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
            mock_crawler_instance.__aexit__ = AsyncMock(return_value=False)
            mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

            mock_run_config = MagicMock()

            with patch("crawler.AsyncWebCrawler", return_value=mock_crawler_instance), \
                 patch("crawler.CrawlerRunConfig", return_value=mock_run_config) as mock_cfg_cls:
                from crawler import crawl_site

                asyncio.run(
                    crawl_site(
                        seed_url="https://example.com/",
                        match_pattern="https://example.com/**",
                        max_pages=1,
                        output_dir=output_dir,
                        use_browser=False,
                        no_cache=False,
                        wait=2,
                    )
                )

            mock_cfg_cls.assert_called_once()
            _, kwargs = mock_cfg_cls.call_args
            self.assertEqual(kwargs.get("delay_before_return_html"), 2.0)


class TestWaitCli(unittest.TestCase):
    def _parse(self, argv):
        from doublefinger import build_parser
        return build_parser().parse_args(argv)

    def test_cli_wait_flag_parsed_correctly(self):
        """--wait 3 is parsed as integer 3."""
        args = self._parse(["crawl", "https://example.com", "--wait", "3"])
        self.assertEqual(args.wait, 3)

    def test_cli_wait_flag_default(self):
        """--wait defaults to 0 when not provided."""
        args = self._parse(["crawl", "https://example.com"])
        self.assertEqual(args.wait, 0)

    def test_wait_negative_value_rejected(self):
        """--wait -1 raises SystemExit via argparse type validation; --wait 1 must succeed."""
        # Positive value must parse cleanly (proves --wait is a known flag).
        args = self._parse(["crawl", "https://example.com", "--wait", "1"])
        self.assertEqual(args.wait, 1)
        # Negative value must be rejected.
        with self.assertRaises(SystemExit):
            self._parse(["crawl", "https://example.com", "--wait", "-1"])


if __name__ == "__main__":
    unittest.main()
