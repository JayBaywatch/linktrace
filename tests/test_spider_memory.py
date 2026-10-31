"""Tests for Spider.run(), broken-link marking, flushing and memory retention."""

import asyncio
import json

import pytest

from linktrace import FetchContext, Fetcher, FetchResult, Spider

HOME = '<title>Home</title><a href="/ok">ok</a><a href="/gone">gone</a>'
OK = "<title>OK</title>"


class SiteFetcher(Fetcher):
    name = "http"

    def __init__(self) -> None:
        self.pages = {
            "https://x.test/": HOME,
            "https://x.test/ok": OK,
        }

    async def open(self, ctx: FetchContext) -> None:
        pass

    async def fetch(self, url: str, headers: dict[str, str]) -> FetchResult:
        body = self.pages.get(url)
        if body is None:
            return FetchResult(url, 404, fetcher=self.name)
        return FetchResult(url, 200, body=body, fetcher=self.name)


def make_spider(**kw) -> Spider:
    return Spider(
        "https://x.test/",
        max_depth=1,
        fetcher=SiteFetcher(),
        respect_robots_txt=False,
        **kw,
    )


class TestRunSync:
    def test_run_returns_documents(self):
        docs = make_spider().run()
        assert {d.url for d in docs} == {
            "https://x.test/",
            "https://x.test/ok",
            "https://x.test/gone",
        }

    async def test_run_inside_event_loop_raises(self):
        with pytest.raises(RuntimeError, match="run_async"):
            make_spider().run()


class TestBrokenLinks:
    async def test_broken_internal_links_marked_after_crawl(self):
        docs = await make_spider().run_async()
        home = next(d for d in docs if d.url == "https://x.test/")
        assert [(b.url, b.status_code) for b in home.broken_internal_links] == [
            ("https://x.test/gone", 404)
        ]
        assert home.broken_external_links == []
        ok = next(d for d in docs if d.url == "https://x.test/ok")
        assert ok.broken_internal_links == []


class TestRetention:
    def test_defaults(self):
        assert make_spider().retain_documents is True
        assert make_spider(on_page_crawled=lambda d: None).retain_documents is False
        assert (
            make_spider(
                on_page_crawled=lambda d: None, accumulate_results=True
            ).retain_documents
            is True
        )
        assert make_spider(flush_to="x.jsonl").retain_documents is False
        assert (
            make_spider(flush_to="x.jsonl", retain_documents=True).retain_documents
            is True
        )

    async def test_streaming_mode_does_not_retain_documents(self):
        seen = []
        spider = make_spider(on_page_crawled=seen.append)
        result = await spider.run_async()
        assert result == []
        assert spider.documents == []
        assert len(seen) == 3
        assert spider.visited_count == 3
        # Heavy fields were released after the callback ran.
        assert all(d.source is None and d.dom is None for d in seen)

    async def test_callback_sees_source_before_release(self):
        sources = []

        async def cb(doc):
            await asyncio.sleep(0)
            sources.append(doc.source)

        await make_spider(on_page_crawled=cb).run_async()
        assert any(s and "Home" in s for s in sources)

    async def test_explicit_retain_with_callback(self):
        spider = make_spider(on_page_crawled=lambda d: None, retain_documents=True)
        await spider.run_async()
        assert len(spider.documents) == 3
        assert any(d.source for d in spider.documents)


class TestFlushToDisk:
    async def test_flush_writes_one_json_line_per_document(self, tmp_path):
        out = tmp_path / "crawl.jsonl"
        spider = make_spider(flush_to=str(out))
        result = await spider.run_async()

        assert result == []
        assert spider.documents == []
        lines = [json.loads(line) for line in out.read_text().splitlines()]
        assert {row["url"] for row in lines} == {
            "https://x.test/",
            "https://x.test/ok",
            "https://x.test/gone",
        }
        home = next(row for row in lines if row["url"] == "https://x.test/")
        assert home["title"] == "Home"
        assert home["fetcher"] == "http"
        assert {link["url"] for link in home["internal_links"]} == {
            "https://x.test/ok",
            "https://x.test/gone",
        }
        assert "html" not in home

    async def test_flush_html_includes_source(self, tmp_path):
        out = tmp_path / "crawl.jsonl"
        await make_spider(flush_to=str(out), flush_html=True).run_async()
        rows = [json.loads(line) for line in out.read_text().splitlines()]
        home = next(row for row in rows if row["url"] == "https://x.test/")
        assert "Home" in home["html"]

    async def test_flush_appends_across_runs(self, tmp_path):
        out = tmp_path / "crawl.jsonl"
        await make_spider(flush_to=str(out)).run_async()
        await make_spider(flush_to=str(out)).run_async()
        assert len(out.read_text().splitlines()) == 6

    async def test_flush_and_retain_together(self, tmp_path):
        out = tmp_path / "crawl.jsonl"
        spider = make_spider(flush_to=str(out), retain_documents=True)
        docs = await spider.run_async()
        assert len(docs) == 3
        assert len(out.read_text().splitlines()) == 3
