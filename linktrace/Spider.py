import asyncio
import logging
from collections.abc import Callable
from typing import Any, Literal

from linktrace.Crawler import Crawler, Document


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
    ) -> None:
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
        self.to_visit = [(start_url, 0)]
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

        # Add console handler to logger
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
            ) as crawler:
                while self.to_visit:
                    tasks = []
                    batch_size = min(10, len(self.to_visit))

                    for _ in range(batch_size):
                        idx = 0 if self.traversal_strategy == "bfs" else -1
                        url, current_depth = self.to_visit.pop(idx)
                        if (
                            url in self.visited
                            or url in self.in_progress
                            or current_depth > self.max_depth
                        ):
                            continue

                        self.in_progress.add(url)

                        tasks.append(
                            self.crawl_and_collect(url, current_depth, crawler)
                        )

                    if tasks:
                        await asyncio.gather(*tasks)
        finally:
            if self._pbar is not None:
                self._pbar.close()
                self._pbar = None

            # Call completion hook
            if self.on_crawl_complete is not None:
                await self._invoke_callback(self.on_crawl_complete)

        # Return logic: Option B
        if self.on_page_crawled is None:
            return self.documents
        elif self.accumulate_results:
            return self.accumulated_results
        else:
            return []

    async def crawl_and_collect(
        self, url: str, current_depth: int, crawler: Crawler
    ) -> None:
        """Crawl a URL and collect internal links."""
        try:
            doc = await crawler.crawl_document_async(url)
            if doc is not None:
                self.track_visits(url, doc)
                async with self.lock:
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

                # Add internal links to the queue
                for link in doc.internal_links:
                    async with self.lock:
                        if link.url in self.discovered:
                            continue

                        self.discovered.add(link.url)
                        self.to_visit.append((link.url, current_depth + 1))

        except Exception as e:
            self._logger.error(f"Failed to crawl {url}: {e}")
            if self.on_error is not None:
                await self._invoke_callback(self.on_error, url, e)
        finally:
            self.in_progress.discard(url)

    def track_visits(self, url: str, doc: Document) -> None:
        self.documents.append(doc)
        self.visited.add(url)


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
