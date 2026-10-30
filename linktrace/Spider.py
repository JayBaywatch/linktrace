import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable
from typing import Any, Literal

from linktrace.Crawler import BrokenLink, Crawler, Document
from linktrace.fetchers.base import Fetcher
from linktrace.rules import CrawlRules
from linktrace.Serializers import Serializers


class FlushError(RuntimeError):
    """Raised when ``Spider(flush_to=...)`` cannot write a crawled page.

    A failed write means the output file is incomplete, so the crawl is
    aborted rather than continuing and finishing with silently missing rows.
    The original ``OSError`` is available as ``__cause__``.
    """


class Spider:
    def __init__(
        self,
        start_url: str,
        max_depth: int = 3,
        debug: bool = False,
        log_name: str | None = None,
        ssl_verify: bool | str = True,
        verify_hostname: bool = True,
        request_timeout: int = 30,
        cache_dir: str | None = None,
        max_retries: int = 3,
        traversal_strategy: Literal["bfs", "dfs"] = "bfs",
        show_progress: bool = False,
        on_page_crawled: (
            Callable[[Document], Any] | None | Callable[[Document], Any]
        ) = None,
        on_error: (
            Callable[[str, Exception], None] | None | Callable[[str, Exception], None]
        ) = None,
        on_crawl_complete: Callable[[], None] | None = None,
        accumulate_results: bool = False,
        request_delay: float = 0.0,
        user_agent: str = "linktrace/0.1.0",
        respect_robots_txt: bool = True,
        max_concurrency: int = 10,
        max_connections: int = 100,
        max_connections_per_host: int = 10,
        rules: CrawlRules | None = None,
        use_sitemaps: bool = False,
        fetcher: Fetcher | None = None,
        keep_hash_routes: bool = False,
        flush_to: str | None = None,
        flush_html: bool = False,
        retain_documents: bool | None = None,
        max_response_bytes: int | None = 10 * 1024 * 1024,
        cache_ttl: int = 86400,
        cache_max_bytes: int | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.keep_hash_routes = keep_hash_routes
        self.max_response_bytes = max_response_bytes
        self.cache_ttl = cache_ttl
        self.cache_max_bytes = cache_max_bytes

        # Memory management. ``flush_to`` streams each Document to a JSONL
        # file as soon as it is crawled. Documents are retained in memory
        # unless the caller opted into a streaming output (flush_to, or a
        # callback without accumulate_results) or said so explicitly.
        self.flush_to = flush_to
        self.flush_html = flush_html
        streaming = flush_to is not None or (
            on_page_crawled is not None and not accumulate_results
        )
        self.retain_documents = (
            retain_documents if retain_documents is not None else not streaming
        )
        self._flush_file: Any = None
        start_url = Crawler.normalize_url(start_url, keep_hash_routes=keep_hash_routes)
        self.start_url = start_url
        self.max_depth = max_depth
        self.ssl_verify = ssl_verify  # bool or str(path to CA cert)
        self.verify_hostname = verify_hostname
        self.request_timeout = request_timeout
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.user_agent = user_agent
        self.respect_robots_txt = respect_robots_txt

        if max_concurrency < 1:
            raise ValueError(f"max_concurrency must be >= 1, got {max_concurrency}.")
        self.max_concurrency = max_concurrency
        self.max_connections = max_connections
        self.max_connections_per_host = max_connections_per_host

        # Empty CrawlRules allows everything, preserving prior behavior.
        self.rules = rules if rules is not None else CrawlRules()
        self.use_sitemaps = use_sitemaps

        if traversal_strategy not in ("bfs", "dfs"):
            raise ValueError(
                f"Invalid traversal_strategy '{traversal_strategy}'. "
                "Must be 'bfs' (breadth-first) or 'dfs' (depth-first)."
            )
        self.traversal_strategy = traversal_strategy
        self.show_progress = show_progress

        self.visited: set[str] = set()
        self.discovered: set[str] = {start_url}
        self.in_progress: set[str] = set()
        # Frontier: appended at the right; BFS pops left, DFS pops right.
        self.to_visit: deque[tuple[str, int]] = deque([(start_url, 0)])
        self.documents: list[Document] = []
        self._logger = logging.getLogger(log_name if log_name else __name__)
        self._logger.setLevel(logging.DEBUG)
        self.visited_count = 0
        self.lock = asyncio.Lock()

        # Callback hooks
        self.on_page_crawled = on_page_crawled
        self.on_error = on_error
        self.on_crawl_complete = on_crawl_complete
        self.accumulate_results = accumulate_results
        self.accumulated_results: list[Any] = []

        self._logger.debug(
            f"Spider initialized: strategy={self.traversal_strategy.upper()}, "
            f"max_depth={max_depth}"
        )

        self._pbar: Any = None

        # Add a console handler only if logging isn't already configured
        # (own handler or root handlers); otherwise messages print twice
        if not self._logger.handlers and not logging.getLogger().handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "%(asctime)s %(name)-12s %(levelname)-8s %(message)s"
            )
            ch.setFormatter(formatter)
            self._logger.addHandler(ch)

    async def _invoke_callback(
        self,
        callback: Callable[..., Any] | Callable[..., Any],
        *args: Any,
    ) -> Any:
        """Invoke callback, supporting both sync and async functions."""
        if asyncio.iscoroutinefunction(callback):
            return await callback(*args)
        else:
            return callback(*args)

    def run(self) -> list[Document]:
        """Run the spider synchronously (blocking) and return the documents.

        Convenience wrapper around :meth:`run_async` for scripts. Inside an
        already-running event loop (Jupyter, an async app) use
        ``await spider.run_async()`` instead.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async())
        raise RuntimeError(
            "Spider.run() cannot be called from a running event loop "
            "(e.g. Jupyter). Use 'await spider.run_async()' instead."
        )

    async def run_async(self) -> list[Document]:
        """Run the spider with persistent session."""
        if self.show_progress:
            from tqdm import tqdm

            self._pbar = tqdm(
                desc="Crawling",
                unit=" URLs",
                dynamic_ncols=True,
                position=0,
                leave=True,
            )

        try:
            if self.flush_to is not None:
                import aiofiles

                self._flush_file = await aiofiles.open(
                    self.flush_to, "a", encoding="utf-8"
                )

            async with Crawler(
                log_name=self._logger.name,
                ssl_verify=self.ssl_verify,
                verify_hostname=self.verify_hostname,
                request_timeout=self.request_timeout,
                cache_dir=self.cache_dir,
                max_retries=self.max_retries,
                request_delay=self.request_delay,
                user_agent=self.user_agent,
                respect_robots_txt=self.respect_robots_txt,
                max_connections=self.max_connections,
                max_connections_per_host=self.max_connections_per_host,
                fetcher=self.fetcher,
                keep_hash_routes=self.keep_hash_routes,
                max_response_bytes=self.max_response_bytes,
                cache_ttl=self.cache_ttl,
                cache_max_bytes=self.cache_max_bytes,
            ) as crawler:
                if self.use_sitemaps:
                    await self._seed_from_sitemaps(crawler)

                while self.to_visit:
                    async with self.lock:
                        batch: list[tuple[str, int]] = []
                        batch_size = min(self.max_concurrency, len(self.to_visit))
                        for _ in range(batch_size):
                            if not self.to_visit:
                                break
                            if self.traversal_strategy == "bfs":
                                url, current_depth = self.to_visit.popleft()
                            else:
                                url, current_depth = self.to_visit.pop()
                            if (
                                url in self.visited
                                or url in self.in_progress
                                or current_depth > self.max_depth
                            ):
                                continue
                            self.in_progress.add(url)
                            batch.append((url, current_depth))

                    if batch:
                        tasks = [
                            self.crawl_and_collect(url, depth, crawler)
                            for url, depth in batch
                        ]
                        # Let the whole batch settle, then surface a flush
                        # failure: outstanding tasks have finished, nothing is
                        # left half-written, and the caller sees the error.
                        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                        for outcome in outcomes:
                            if isinstance(outcome, BaseException):
                                raise outcome

            self._mark_broken_links()
        finally:
            if self._flush_file is not None:
                await self._flush_file.close()
                self._flush_file = None

            if self._pbar is not None:
                self._pbar.close()
                self._pbar = None

            # Call completion hook
            if self.on_crawl_complete is not None:
                await self._invoke_callback(self.on_crawl_complete)

        # Return logic: documents when retained, else the callback results
        # (streaming / flushed crawls return an empty list).
        if self.on_page_crawled is None:
            return self.documents
        elif self.accumulate_results:
            return self.accumulated_results
        else:
            return []

    def _mark_broken_links(self) -> None:
        """Fill ``Document.broken_internal_links`` from crawled status codes.

        Runs once after the crawl. An internal link is broken when the page
        it points to was crawled and came back with a 4xx/5xx status. External
        links are never fetched, so ``broken_external_links`` stays empty.
        Only retained documents are marked; with ``retain_documents=False``
        (streaming or ``flush_to`` crawls) there is nothing to mark.

        Redirect targets are indexed too, so a link to ``/b`` resolves when
        ``/b`` was only ever reached via ``/a -> /b``. A page fetched directly
        always wins over a status learned through a redirect.
        """
        status_by_url: dict[str, int] = {}
        for doc in self.documents:
            if doc.redirected:
                status_by_url.setdefault(doc.final_url, doc.status_code)
        for doc in self.documents:
            status_by_url[doc.url] = doc.status_code
        for doc in self.documents:
            doc.broken_internal_links = [
                BrokenLink(link.url, status_by_url[link.url])
                for link in doc.internal_links
                if status_by_url.get(link.url, 0) >= 400
            ]

    async def _seed_from_sitemaps(self, crawler: Crawler) -> None:
        """Seed the queue with URLs discovered from the site's sitemaps.

        Discovered URLs are normalized and filtered through the crawl rules, and
        enqueued at depth 0 so their own links are still followed within
        ``max_depth``.
        """
        try:
            urls = await crawler.discover_sitemap_urls(self.start_url)
        except Exception as e:
            self._logger.warning(f"Sitemap discovery failed: {e}")
            return

        seeded = 0
        async with self.lock:
            for url in urls:
                norm = Crawler.normalize_url(
                    url, keep_hash_routes=self.keep_hash_routes
                )
                if norm in self.discovered:
                    continue
                self.discovered.add(norm)
                if not self.rules.allows(norm):
                    continue
                self.to_visit.append((norm, 0))
                seeded += 1
        self._logger.info(f"Seeded {seeded} URL(s) from sitemaps")

    async def crawl_and_collect(
        self, url: str, current_depth: int, crawler: Crawler
    ) -> None:
        """Crawl a URL and collect internal links."""
        try:
            doc = await crawler.crawl_document_async(url)
            if doc is not None:
                self.track_visits(url, doc)
                async with self.lock:
                    if doc.redirected:
                        # The served URL is now known content; never fetch it
                        # again under its own name.
                        self.discovered.add(doc.final_url)
                        self.visited.add(doc.final_url)
                    self.visited_count += 1
                    self._logger.info(
                        f"Visited: {url} (Total Visited: {self.visited_count})"
                    )
                    if self._pbar is not None:
                        self._pbar.update(1)
                        self._pbar.set_postfix(
                            {
                                "visited": self.visited_count,
                                "pending": len(self.to_visit),
                            }
                        )

                # Invoke callback if provided
                if self.on_page_crawled is not None:
                    result = await self._invoke_callback(self.on_page_crawled, doc)
                    if self.accumulate_results:
                        self.accumulated_results.append(result)

                if self._flush_file is not None:
                    try:
                        await self._flush_document(doc)
                    except Exception as e:
                        raise FlushError(
                            f"Could not write {url} to {self.flush_to}: {e}"
                        ) from e

                if not self.retain_documents:
                    # Free the heavy parts now; the Document object itself is
                    # only referenced by the caller's callback (if any).
                    doc.source = None
                    doc.dom = None

                # Add internal links to the queue
                for link in doc.internal_links:
                    async with self.lock:
                        if link.url in self.discovered:
                            continue

                        self.discovered.add(link.url)
                        if not self.rules.allows(link.url):
                            self._logger.debug(f"Filtered by rules: {link.url}")
                            continue

                        self.to_visit.append((link.url, current_depth + 1))

        except FlushError as e:
            # Not a per-page failure: the output file is now incomplete.
            self._logger.error(str(e))
            raise
        except Exception as e:
            self._logger.error(f"Failed to crawl {url}: {e}")
            if self.on_error is not None:
                await self._invoke_callback(self.on_error, url, e)
        finally:
            self.in_progress.discard(url)

    def track_visits(self, url: str, doc: Document) -> None:
        if self.retain_documents:
            self.documents.append(doc)
        self.visited.add(url)

    async def _flush_document(self, doc: Document) -> None:
        """Append ``doc`` as one JSON line to the ``flush_to`` file."""
        line = json.dumps(Serializers.document_to_dict(doc, self.flush_html))
        async with self.lock:
            await self._flush_file.write(line + "\n")


if __name__ == "__main__":
    test_uri = "https://cnn.com/"
    spider = Spider(start_url=test_uri, max_depth=2, debug=False)

    loop = asyncio.get_event_loop()
    documents = loop.run_until_complete(spider.run_async())

    for doc in documents:
        print(doc.title.encode("ascii", "ignore"))
        print("== internals ==")
        for link in doc.internal_links:
            print(link.url, link.text)
        print("== externals ==")
        for link in doc.external_links:
            print(link.url, link.text)

    x = 1
