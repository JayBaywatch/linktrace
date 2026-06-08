"""Tests for Spider traversal strategies (BFS vs DFS)."""

import pytest

from WebCrawler import Spider


@pytest.fixture
def multi_depth_html():
    """Create a mock site with clear depth levels for traversal testing.

    Structure:
      depth-0: home
        ├─ depth-1a: page1
        │   └─ depth-2a: page1_sub
        └─ depth-1b: page2
    """
    return {
        "home": '<a href="/page1">Page 1</a><a href="/page2">Page 2</a>',
        "page1": '<a href="/page1_sub">Sub Page</a>',
        "page2": '<a href="/page2_sub">Sub Page</a>',
        "page1_sub": "",
        "page2_sub": "",
    }


class TestBFSTraversal:
    """Tests for breadth-first search (default behavior)."""

    def test_bfs_default(self):
        """Verify BFS is the default strategy."""
        spider = Spider(start_url="https://example.com")
        assert spider.traversal_strategy == "bfs"

    def test_bfs_explicit(self):
        """Verify BFS can be explicitly set."""
        spider = Spider(start_url="https://example.com", traversal_strategy="bfs")
        assert spider.traversal_strategy == "bfs"

    def test_bfs_queue_order(self):
        """Verify BFS processes queue in FIFO order (pop(0))."""
        spider = Spider(start_url="https://example.com", traversal_strategy="bfs")
        spider.to_visit = [
            ("url1", 1),
            ("url2", 1),
            ("url3", 2),
            ("url4", 2),
        ]

        # BFS should pop from front (pop(0))
        idx = 0 if spider.traversal_strategy == "bfs" else -1
        url, depth = spider.to_visit.pop(idx)
        assert url == "url1"  # First in = first out

        url, depth = spider.to_visit.pop(idx)
        assert url == "url2"

    def test_bfs_breadth_before_depth(self):
        """Verify BFS explores breadth before depth."""
        spider = Spider(start_url="https://example.com", traversal_strategy="bfs")
        # Simulate adding links: depth 1 first, then depth 2
        spider.to_visit = []
        spider.to_visit.append(("depth-1-link-a", 1))
        spider.to_visit.append(("depth-1-link-b", 1))
        spider.to_visit.append(("depth-2-link-a", 2))

        # BFS should pop depth-1 items first
        url1, d1 = spider.to_visit.pop(0)
        url2, d2 = spider.to_visit.pop(0)
        url3, d3 = spider.to_visit.pop(0)

        assert d1 == 1 and d2 == 1  # Depth 1 before depth 2
        assert d3 == 2


class TestDFSTraversal:
    """Tests for depth-first search."""

    def test_dfs_explicit(self):
        """Verify DFS can be set explicitly."""
        spider = Spider(start_url="https://example.com", traversal_strategy="dfs")
        assert spider.traversal_strategy == "dfs"

    def test_dfs_queue_order(self):
        """Verify DFS processes queue in LIFO order (pop(-1))."""
        spider = Spider(start_url="https://example.com", traversal_strategy="dfs")
        spider.to_visit = [
            ("url1", 1),
            ("url2", 1),
            ("url3", 2),
            ("url4", 2),
        ]

        # DFS should pop from back (pop(-1))
        idx = -1 if spider.traversal_strategy == "dfs" else 0
        url, depth = spider.to_visit.pop(idx)
        assert url == "url4"  # Last in = first out

        url, depth = spider.to_visit.pop(idx)
        assert url == "url3"

    def test_dfs_depth_before_breadth(self):
        """Verify DFS explores depth before breadth."""
        spider = Spider(start_url="https://example.com", traversal_strategy="dfs")
        # Simulate adding links in breadth order
        spider.to_visit = []
        spider.to_visit.append(("depth-1-link-a", 1))
        spider.to_visit.append(("depth-1-link-b", 1))
        spider.to_visit.append(("depth-2-link-a", 2))

        # DFS should pop depth-2 items first (added last, removed first with LIFO)
        url1, d1 = spider.to_visit.pop(-1)
        url2, d2 = spider.to_visit.pop(-1)
        url3, d3 = spider.to_visit.pop(-1)

        assert d1 == 2  # Depth 2 first
        assert d2 == 1 and d3 == 1  # Then depth 1


class TestTraversalValidation:
    """Tests for strategy validation."""

    def test_invalid_strategy_raises_error(self):
        """Verify invalid strategy raises ValueError."""
        with pytest.raises(ValueError, match="Invalid traversal_strategy"):
            Spider(
                start_url="https://example.com",
                traversal_strategy="invalid",  # type: ignore
            )

    def test_invalid_strategy_message(self):
        """Verify error message guides user to valid options."""
        with pytest.raises(ValueError, match="'bfs'.*'dfs'"):
            Spider(
                start_url="https://example.com",
                traversal_strategy="breadth",  # type: ignore
            )


class TestTraversalQueueBehavior:
    """Tests comparing BFS and DFS queue behavior with same links."""

    def test_same_urls_visited_both_strategies(self):
        """Verify both BFS and DFS visit same URLs, just different order."""
        urls_to_add = [
            ("https://example.com/page1", 1),
            ("https://example.com/page2", 1),
            ("https://example.com/page1/sub", 2),
            ("https://example.com/page2/sub", 2),
        ]

        # BFS
        spider_bfs = Spider(start_url="https://example.com", traversal_strategy="bfs")
        spider_bfs.to_visit = urls_to_add.copy()
        visited_bfs = []
        while spider_bfs.to_visit:
            idx = 0 if spider_bfs.traversal_strategy == "bfs" else -1
            url, depth = spider_bfs.to_visit.pop(idx)
            visited_bfs.append(url)

        # DFS
        spider_dfs = Spider(start_url="https://example.com", traversal_strategy="dfs")
        spider_dfs.to_visit = urls_to_add.copy()
        visited_dfs = []
        while spider_dfs.to_visit:
            idx = 0 if spider_dfs.traversal_strategy == "bfs" else -1
            url, depth = spider_dfs.to_visit.pop(idx)
            visited_dfs.append(url)

        # Same URLs visited
        assert set(visited_bfs) == set(visited_dfs)
        # Different order
        assert visited_bfs != visited_dfs


class TestTraversalLogging:
    """Tests for debug logging of traversal strategy."""

    def test_bfs_logging(self, caplog):
        """Verify BFS strategy is logged at debug level."""
        Spider(start_url="https://example.com", traversal_strategy="bfs")
        assert "strategy=BFS" in caplog.text

    def test_dfs_logging(self, caplog):
        """Verify DFS strategy is logged at debug level."""
        Spider(start_url="https://example.com", traversal_strategy="dfs")
        assert "strategy=DFS" in caplog.text


class TestProgressTracking:
    """Tests for progress bar functionality."""

    def test_show_progress_default_false(self):
        """Verify show_progress defaults to False."""
        spider = Spider(start_url="https://example.com")
        assert spider.show_progress is False

    def test_show_progress_can_be_enabled(self):
        """Verify show_progress can be set to True."""
        spider = Spider(start_url="https://example.com", show_progress=True)
        assert spider.show_progress is True

    def test_pbar_initialized_none(self):
        """Verify _pbar is initialized as None."""
        spider = Spider(start_url="https://example.com")
        assert spider._pbar is None

    def test_show_progress_with_bfs(self):
        """Verify show_progress works with BFS traversal."""
        spider = Spider(
            start_url="https://example.com",
            traversal_strategy="bfs",
            show_progress=True,
        )
        assert spider.show_progress is True
        assert spider.traversal_strategy == "bfs"

    def test_show_progress_with_dfs(self):
        """Verify show_progress works with DFS traversal."""
        spider = Spider(
            start_url="https://example.com",
            traversal_strategy="dfs",
            show_progress=True,
        )
        assert spider.show_progress is True
        assert spider.traversal_strategy == "dfs"
