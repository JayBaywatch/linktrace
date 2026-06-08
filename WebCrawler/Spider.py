import asyncio
import logging

from WebCrawler.Crawler import Crawler


class Spider:
    def __init__(
        self,
        start_url,
        max_depth=3,
        debug=False,
        log_name=None,
        ssl_verify=True,
        verify_hostname=True,
        request_timeout=30,
        cache_dir=None,
        max_retries=3,
    ):
        self.start_url = start_url
        self.max_depth = max_depth
        self.ssl_verify = ssl_verify  # bool or str(path to CA cert)
        self.verify_hostname = verify_hostname
        self.request_timeout = request_timeout
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.visited = set()
        self.to_visit = [(start_url, 0)]
        self.documents = []
        self._logger = logging.getLogger(log_name if log_name else __name__)
        self._logger.setLevel(logging.DEBUG)
        self.visited_count = 0
        self.lock = asyncio.Lock()

        # Add console handler to logger
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s %(name)-12s %(levelname)-8s %(message)s"
        )
        ch.setFormatter(formatter)
        self._logger.addHandler(ch)

    async def run_async(self):
        """Run the spider with persistent session."""
        async with Crawler(
            log_name=self._logger.name,
            ssl_verify=self.ssl_verify,
            verify_hostname=self.verify_hostname,
            request_timeout=self.request_timeout,
            cache_dir=self.cache_dir,
            max_retries=self.max_retries,
        ) as crawler:
            tasks = []
            while self.to_visit:
                url, current_depth = self.to_visit.pop(0)
                if url in self.visited or current_depth > self.max_depth:
                    continue

                tasks.append(self.crawl_and_collect(url, current_depth, crawler))

            await asyncio.gather(*tasks)
        return self.documents

    async def crawl_and_collect(self, url, current_depth, crawler):
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
                # Add internal links to the queue
                for link in doc.internal_links:
                    if link.url not in self.visited:
                        self.to_visit.append((link.url, current_depth + 1))

        except Exception as e:
            self._logger.error(f"Failed to crawl {url}: {e}")

    def track_visits(self, url, doc):
        self.documents.append(doc)
        self.visited.add(url)

    def run(self):
        while self.to_visit:
            url, current_depth = self.to_visit.pop(0)
            if url in self.visited or current_depth > self.max_depth:
                continue

            try:
                doc = self.crawler.crawl_document(url)
                self.track_visits(url, doc)
                self._logger.info(f"Visited: {url}")

                # Add internal links to the queue
                for link in doc.internal_links:
                    if link.url not in self.visited:
                        self.to_visit.append((link.url, current_depth + 1))

            except Exception as e:
                self._logger.error(f"Failed to crawl {url}: {e}")

        return self.documents


if __name__ == "__main__":
    test_uri = "https://cnn.com/"
    spider = Spider(start_url=test_uri, max_depth=3, debug=False)

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
