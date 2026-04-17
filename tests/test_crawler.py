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

            with patch("crawler.AsyncWebCrawler", return_value=mock_crawler_instance):
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

            with patch("crawler.AsyncWebCrawler", return_value=mock_crawler_instance):
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


if __name__ == "__main__":
    unittest.main()
