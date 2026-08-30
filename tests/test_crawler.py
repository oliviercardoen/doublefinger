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


def _page(url, links=(), markdown="# Page"):
    """Build a mock Crawl4AI result for one page."""
    result = MagicMock()
    result.success = True
    result.url = url
    result.markdown = markdown
    result.links = {"internal": [{"href": href} for href in links]}
    return result


def _mock_crawler(site):
    """Build a mock AsyncWebCrawler serving ``site`` (a {url: result} dict).

    Requests for a URL absent from ``site`` come back as a failed result,
    which the crawler is expected to warn about rather than crash on.
    """
    def serve(url=None, config=None):
        if url in site:
            return site[url]
        missing = MagicMock()
        missing.success = False
        missing.url = url
        missing.markdown = None
        return missing

    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    instance.arun = AsyncMock(side_effect=serve)
    return instance


def _run(instance, output_dir, **kwargs):
    """Run crawl_site against a mock crawler with sensible test defaults."""
    from crawler import crawl_site
    options = {
        "seed_url": "https://example.com/docs/",
        "match_pattern": "https://example.com/docs/**",
        "max_pages": 0,
        "output_dir": output_dir,
        "use_browser": False,
        "no_cache": False,
    }
    options.update(kwargs)
    with patch("crawler.AsyncWebCrawler", return_value=instance), \
         patch("crawler.CrawlerRunConfig", return_value=MagicMock()):
        asyncio.run(crawl_site(**options))


# The seed page links to its sub-page three times, spelled three ways, plus
# a link back to itself with a tracking parameter.
SEED = "https://example.com/docs"
API = "https://example.com/docs/api"
SITE = {
    SEED: _page(SEED, links=[
        "https://example.com/docs/api/",
        "https://example.com/docs/api#reference",
        "/docs/api",
        "https://example.com/docs/?utm_source=newsletter",
    ]),
    API: _page(API),
}


class TestCrawlerUrlDeduplication(unittest.TestCase):
    def test_url_variants_are_fetched_once(self):
        """Four link spellings resolve to two real pages, so two fetches."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            instance = _mock_crawler(SITE)
            _run(instance, output_dir)

            self.assertEqual(instance.arun.call_count, 2)
            self.assertEqual(
                sorted(f.name for f in output_dir.glob("*.md")),
                ["docs-api.md", "docs.md"],
            )

    def test_relative_links_are_resolved_against_the_page(self):
        """The bare '/docs/api' href must be followed, not dropped."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            only_relative = {SEED: _page(SEED, links=["/docs/api"]), API: _page(API)}
            instance = _mock_crawler(only_relative)
            _run(instance, output_dir)

            self.assertTrue((output_dir / "docs-api.md").exists())

    def test_max_pages_counts_pages_not_link_spellings(self):
        """Duplicate spellings must not consume the --max-pages budget."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            instance = _mock_crawler(SITE)
            _run(instance, output_dir, max_pages=2)

            self.assertEqual(instance.arun.call_count, 2)


class TestCrawlerResume(unittest.TestCase):
    def test_second_run_skips_pages_already_crawled(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _run(_mock_crawler(SITE), output_dir)

            second = _mock_crawler(SITE)
            _run(second, output_dir)
            self.assertEqual(second.arun.call_count, 0)

    def test_force_recrawls_everything(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _run(_mock_crawler(SITE), output_dir)

            second = _mock_crawler(SITE)
            _run(second, output_dir, resume=False)
            self.assertEqual(second.arun.call_count, 2)

    def test_resume_restores_the_frontier_of_a_skipped_page(self):
        """A run stopped by --max-pages continues where it left off."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            first = _mock_crawler(SITE)
            _run(first, output_dir, max_pages=1)
            self.assertEqual(first.arun.call_count, 1)
            self.assertFalse((output_dir / "docs-api.md").exists())

            second = _mock_crawler(SITE)
            _run(second, output_dir)
            # The seed is skipped, but the link it recorded is followed.
            second.arun.assert_called_once()
            self.assertEqual(second.arun.call_args.kwargs["url"], API)
            self.assertTrue((output_dir / "docs-api.md").exists())

    def test_deleted_markdown_file_is_crawled_again(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _run(_mock_crawler(SITE), output_dir)
            (output_dir / "docs-api.md").unlink()

            second = _mock_crawler(SITE)
            _run(second, output_dir)
            second.arun.assert_called_once()
            self.assertEqual(second.arun.call_args.kwargs["url"], API)

    def test_manifest_records_file_and_links(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _run(_mock_crawler(SITE), output_dir)

            from manifest import load_manifest
            pages = load_manifest(output_dir)["pages"]
            self.assertEqual(set(pages), {SEED, API})
            self.assertEqual(pages[SEED]["file"], "docs.md")
            # The seed's self-link is in scope and recorded once; the crawl
            # loop de-duplicates it against `visited` rather than dropping it.
            self.assertEqual(pages[SEED]["links"], [API, SEED])


class TestResumeCli(unittest.TestCase):
    def _parse(self, argv):
        from doublefinger import build_parser
        return build_parser().parse_args(argv)

    def test_resume_is_the_default(self):
        args = self._parse(["crawl", "https://example.com"])
        self.assertFalse(args.force)

    def test_force_flag_parsed(self):
        args = self._parse(["crawl", "https://example.com", "--force"])
        self.assertTrue(args.force)

    def test_resume_and_force_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            self._parse(["crawl", "https://example.com", "--resume", "--force"])


if __name__ == "__main__":
    unittest.main()
