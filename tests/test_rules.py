"""Tests for CrawlRules URL filtering."""

from linktrace import CrawlRules, Spider


class TestEmptyRules:
    def test_empty_rules_allow_everything(self):
        rules = CrawlRules()
        assert rules.allows("https://example.com/anything")
        assert rules.allows("https://other.org/x.pdf?sort=asc")

    def test_spider_defaults_to_permissive_rules(self):
        spider = Spider(start_url="https://example.com")
        assert isinstance(spider.rules, CrawlRules)
        assert spider.rules.allows("https://example.com/whatever")


class TestPathPrefixes:
    def test_include_path_prefixes_whitelist(self):
        rules = CrawlRules(include_path_prefixes=["/homes-for-sale/"])
        assert rules.allows("https://example.com/homes-for-sale/123")
        assert not rules.allows("https://example.com/blog/post")

    def test_exclude_path_prefixes_blacklist(self):
        rules = CrawlRules(exclude_path_prefixes=["/blog/", "/login"])
        assert rules.allows("https://example.com/homes-for-sale/123")
        assert not rules.allows("https://example.com/blog/post")
        assert not rules.allows("https://example.com/login")

    def test_exclude_beats_include(self):
        rules = CrawlRules(
            include_path_prefixes=["/homes/"],
            exclude_path_prefixes=["/homes/archived/"],
        )
        assert rules.allows("https://example.com/homes/123")
        assert not rules.allows("https://example.com/homes/archived/9")


class TestExtensions:
    def test_blocked_extensions(self):
        rules = CrawlRules(blocked_extensions=["pdf", ".jpg"])
        assert not rules.allows("https://example.com/doc.pdf")
        assert not rules.allows("https://example.com/photo.JPG")
        assert rules.allows("https://example.com/page")

    def test_allowed_extensions_whitelist_keeps_extensionless(self):
        rules = CrawlRules(allowed_extensions=["html", ""])
        assert rules.allows("https://example.com/page.html")
        assert rules.allows("https://example.com/homes-for-sale/")
        assert not rules.allows("https://example.com/doc.pdf")


class TestQueryParams:
    def test_exclude_query_params(self):
        rules = CrawlRules(exclude_query_params=["sort", "calendar"])
        assert rules.allows("https://example.com/list")
        assert not rules.allows("https://example.com/list?sort=price")
        assert not rules.allows("https://example.com/events?calendar=2026-07")

    def test_other_params_allowed(self):
        rules = CrawlRules(exclude_query_params=["sort"])
        assert rules.allows("https://example.com/list?page=2")


class TestDomains:
    def test_blocked_domains_with_subdomains(self):
        rules = CrawlRules(blocked_domains=["ads.example.com"])
        assert not rules.allows("https://ads.example.com/x")
        assert not rules.allows("https://sub.ads.example.com/x")
        assert rules.allows("https://example.com/x")

    def test_allowed_domains_whitelist(self):
        rules = CrawlRules(allowed_domains=["example.com"])
        assert rules.allows("https://example.com/x")
        assert rules.allows("https://www.example.com/x")
        assert not rules.allows("https://other.org/x")

    def test_port_is_ignored_for_domain_match(self):
        rules = CrawlRules(allowed_domains=["example.com"])
        assert rules.allows("https://example.com:8443/x")


class TestRegex:
    def test_exclude_patterns(self):
        rules = CrawlRules(exclude_patterns=[r"/page/\d+/comments"])
        assert rules.allows("https://example.com/page/5")
        assert not rules.allows("https://example.com/page/5/comments")

    def test_include_patterns_whitelist(self):
        rules = CrawlRules(include_patterns=[r"/property/\d+"])
        assert rules.allows("https://example.com/property/42")
        assert not rules.allows("https://example.com/about")


class TestRealEstateScenario:
    def test_combined_real_estate_rules(self):
        rules = CrawlRules(
            allowed_domains=["realty.example.com"],
            include_path_prefixes=["/homes-for-sale/", "/agents/"],
            exclude_path_prefixes=["/login", "/privacy"],
            blocked_extensions=["pdf", "jpg", "png"],
            exclude_query_params=["sort", "view", "calendar"],
        )
        assert rules.allows("https://realty.example.com/homes-for-sale/123")
        assert rules.allows("https://realty.example.com/agents/jane")
        assert not rules.allows("https://realty.example.com/login")
        assert not rules.allows(
            "https://realty.example.com/homes-for-sale/123?sort=price"
        )
        assert not rules.allows("https://realty.example.com/homes-for-sale/flyer.pdf")
        assert not rules.allows("https://other.com/homes-for-sale/1")
