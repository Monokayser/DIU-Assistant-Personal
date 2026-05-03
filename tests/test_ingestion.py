from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.apps.documents.rag.ingestion as ingestion
from src.apps.documents.rag.ingestion import PageData, build_site_index, crawl_site, discover_sitemap_urls


class IngestionTests(unittest.TestCase):
    def test_sitemap_discovery_reads_nested_official_urls(self) -> None:
        sitemap_index = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://daffodilvarsity.edu.bd/pages.xml</loc></sitemap>
        </sitemapindex>
        """
        page_sitemap = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://daffodilvarsity.edu.bd/admission-contact</loc></url>
            <url><loc>https://example.com/not-approved</loc></url>
        </urlset>
        """

        def fake_fetch(url: str) -> str:
            return page_sitemap if url.endswith("pages.xml") else sitemap_index

        with patch.object(ingestion, "SITEMAP_URLS", ["https://daffodilvarsity.edu.bd/sitemap.xml"]):
            with patch.object(ingestion, "_fetch_sitemap_xml", side_effect=fake_fetch):
                urls = discover_sitemap_urls()

        self.assertEqual(urls, ["https://daffodilvarsity.edu.bd/admission-contact"])

    def test_crawler_does_not_follow_external_approved_page_links(self) -> None:
        external_url = "https://www.topuniversities.com/universities/daffodil-international-university"

        def fake_fetch(url: str) -> PageData | None:
            if url == external_url:
                return PageData(
                    url=url,
                    title="QS Profile",
                    text="Daffodil International University ranking information. " * 5,
                    links=["https://www.topuniversities.com/universities/not-diu"],
                )
            if url == "https://daffodilvarsity.edu.bd":
                return PageData(
                    url=url,
                    title="DIU",
                    text="Official Daffodil International University information. " * 5,
                    links=[],
                )
            return PageData(
                url=url,
                title="Unexpected",
                text="This page should not be reached. " * 8,
                links=[],
            )

        with patch.object(ingestion, "SEED_URLS", [external_url]):
            with patch.object(ingestion, "fetch_page", side_effect=fake_fetch):
                pages = crawl_site(
                    "https://daffodilvarsity.edu.bd/",
                    max_pages=5,
                    request_delay=0,
                    include_sitemaps=False,
                )

        crawled_urls = {page.url for page in pages}
        self.assertIn(external_url, crawled_urls)
        self.assertNotIn("https://www.topuniversities.com/universities/not-diu", crawled_urls)

    def test_build_site_index_writes_approved_source_metadata(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            output_path = Path(temp_dir.name) / "site_index.json"
            with patch.object(
                ingestion,
                "crawl_site",
                return_value=[
                    PageData(
                        url="https://daffodilvarsity.edu.bd/",
                        title="DIU",
                        text="Official Daffodil International University information for students and applicants. " * 5,
                        links=[],
                    )
                ],
            ):
                metadata = build_site_index(
                    "https://daffodilvarsity.edu.bd/",
                    output_path,
                    max_pages=25,
                    request_delay=0,
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["crawl_budget_pages"], 25)
            self.assertIn("approved_sources", payload["metadata"])
            self.assertIn("https://daffodilvarsity.edu.bd/", payload["metadata"]["approved_sources"])
            self.assertTrue(payload["chunks"])
        finally:
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
